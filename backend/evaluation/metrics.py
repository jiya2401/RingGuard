"""Reproducible baseline-vs-graph evaluation and robustness probes."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.data.model import ARCHETYPES, Ecosystem
from backend.detection.rings import discover_rings
from backend.evaluation.hard_negatives import benchmark_hard_negatives
from backend.evaluation.splits import (
    BASELINE_FEATURES,
    GRAPH_FEATURES,
    build_transaction_frame,
    split_frames,
)
from backend.graph.builder import build_graph
from backend.models.baselines import FittedModel, fit_comparison_models
from backend.risk.emerging import DAY_S, emerging_report, graph_t0
from backend.risk.engine import score_rings


def choose_threshold(y_true: pd.Series, probabilities: np.ndarray) -> float:
    """Select a threshold on validation data only, maximizing F1 deterministically."""
    candidates = sorted({0.05, 0.95, *np.round(probabilities, 4).tolist()})
    best = (float("-inf"), float("-inf"), 0.5)
    for threshold in candidates:
        predicted = probabilities >= threshold
        f1 = f1_score(y_true, predicted, zero_division=0)
        precision = precision_score(y_true, predicted, zero_division=0)
        candidate = (float(f1), float(precision), float(threshold))
        if candidate > best:
            best = candidate
    return round(best[2], 4)


def classification_metrics(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    precision_k: int = 100,
) -> dict[str, float | int]:
    """Required binary metrics from real labels/probabilities."""
    y = np.asarray(y_true, dtype=int)
    predicted = probabilities >= threshold
    negatives = y == 0
    false_positives = int(np.sum(predicted & negatives))
    k = min(max(1, precision_k), len(y)) if len(y) else 0
    top = np.argsort(-probabilities, kind="stable")[:k] if k else np.array([], dtype=int)
    return {
        "threshold": float(threshold),
        "precision": round(float(precision_score(y, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y, predicted, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, probabilities)), 4)
        if len(np.unique(y)) == 2
        else 0.0,
        "pr_auc": round(float(average_precision_score(y, probabilities)), 4)
        if np.any(y)
        else 0.0,
        "false_positive_rate": round(
            false_positives / int(np.sum(negatives)), 4
        )
        if np.any(negatives)
        else 0.0,
        "precision_at_k": round(float(np.mean(y[top])), 4) if k else 0.0,
        "k": k,
        "support": int(len(y)),
        "positive_support": int(np.sum(y)),
    }


def _hard_negative_transaction_fpr(
    frame: pd.DataFrame, probabilities: np.ndarray, threshold: float
) -> float:
    mask = frame["hard_negative"].to_numpy(dtype=bool)
    if not np.any(mask):
        return 0.0
    return round(float(np.mean(probabilities[mask] >= threshold)), 4)


def _per_archetype_recall(
    test: pd.DataFrame, probabilities: np.ndarray, threshold: float
) -> dict[str, dict[str, float | int]]:
    predicted = probabilities >= threshold
    out: dict[str, dict[str, float | int]] = {}
    for archetype in sorted(set(test.loc[test["label"] == 1, "archetype"])):
        mask = test["archetype"].to_numpy() == archetype
        out[archetype] = {
            "support": int(np.sum(mask)),
            "recall": round(float(np.mean(predicted[mask])), 4),
        }
    return out


def adversarial_report(
    model: FittedModel,
    test: pd.DataFrame,
    threshold: float,
) -> dict[str, Any]:
    """Measure fixed-model degradation under three deterministic evasions."""
    scenarios: dict[str, pd.DataFrame] = {"original": test.copy()}

    diluted = test.copy()
    for name in (
        "device_prior_users",
        "instrument_prior_users",
        "ip_prior_users",
        "payer_prior_devices",
        "payer_prior_instruments",
    ):
        if name in diluted:
            diluted[name] *= 0.25
    scenarios["infrastructure_dilution_75pct"] = diluted

    smeared = test.copy()
    smeared["hour_sin"] = 0.0
    smeared["hour_cos"] = 0.0
    smeared["seconds_since_previous_log"] = smeared[
        "seconds_since_previous_log"
    ].max()
    scenarios["timing_smear"] = smeared

    combined = diluted.copy()
    combined["hour_sin"] = 0.0
    combined["hour_cos"] = 0.0
    combined["seconds_since_previous_log"] = smeared[
        "seconds_since_previous_log"
    ]
    scenarios["combined_evasion"] = combined

    results = {}
    for name, frame in scenarios.items():
        probs = model.probabilities(frame)
        results[name] = classification_metrics(frame["label"], probs, threshold)
    original_recall = float(results["original"]["recall"])
    for result in results.values():
        result["recall_delta_vs_original"] = round(
            float(result["recall"]) - original_recall, 4
        )
    return results


def _unseen_archetype_report(
    parts: dict[str, pd.DataFrame],
    *,
    holdout: str,
    seed: int,
) -> dict[str, Any]:
    """Fit without one archetype and evaluate it against test negatives."""
    train = parts["train"].loc[parts["train"]["archetype"] != holdout].copy()
    validation = parts["validation"].loc[
        parts["validation"]["archetype"] != holdout
    ].copy()
    test = parts["test"].loc[
        (parts["test"]["label"] == 0) | (parts["test"]["archetype"] == holdout)
    ].copy()
    if (
        train["label"].nunique() < 2
        or validation["label"].nunique() < 2
        or not (test["archetype"] == holdout).any()
    ):
        return {
            "held_out_archetype": holdout,
            "available": False,
            "reason": "insufficient positive/negative support in chronological splits",
        }
    model = fit_comparison_models(train, seed=seed)[
        "graph_enhanced_logistic_regression"
    ]
    threshold = choose_threshold(
        validation["label"], model.probabilities(validation)
    )
    probabilities = model.probabilities(test)
    return {
        "held_out_archetype": holdout,
        "available": True,
        "training_rows_removed": int(
            len(parts["train"]) - len(train)
        ),
        "test_positive_support": int(
            (test["archetype"] == holdout).sum()
        ),
        "metrics": classification_metrics(
            test["label"], probabilities, threshold
        ),
    }


def _ring_metrics(ecosystem: Ecosystem, include_emerging: bool) -> dict[str, Any]:
    graph = build_graph(ecosystem)
    rings = score_rings(discover_rings(graph), graph)
    abuse = [p for p in ecosystem.plants if p.archetype in ARCHETYPES]
    detected = [
        p for p in abuse if any(set(p.users) <= set(r.users) for r in rings)
    ]
    hard_negative = benchmark_hard_negatives(ecosystem, graph, rings)
    out: dict[str, Any] = {
        "ring_detection_recall": round(len(detected) / len(abuse), 4)
        if abuse
        else 0.0,
        "rings_detected": len(detected),
        "rings_planted": len(abuse),
        "hard_negative_false_positive_rate": hard_negative["per_threshold"],
    }
    if include_emerging:
        start = graph_t0(graph)
        report = emerging_report(
            graph, [start + day * DAY_S for day in range(2, 31, 2)]
        )
        planted = [p for p in ecosystem.plants if p.archetype == "H"]
        latencies = []
        for plant in planted:
            match = next(
                (
                    row
                    for row in report["rings"]
                    if set(plant.users) <= set(row["users"])
                ),
                None,
            )
            if match:
                latencies.append(
                    {
                        "plant_id": plant.ring_id,
                        "detected_day": match["detected_day"],
                        "lead_days": match["lead_days"],
                        "final_risk": match["final_risk"],
                    }
                )
        out["emerging_ring_detection"] = latencies
    return out


def evaluate_ecosystem(
    ecosystem: Ecosystem,
    *,
    include_ring_metrics: bool = True,
    include_emerging: bool = True,
) -> dict[str, Any]:
    """Run the complete reproducible M9-M10 comparison."""
    frame = build_transaction_frame(ecosystem)
    parts = split_frames(frame)
    models = fit_comparison_models(parts["train"], seed=ecosystem.seed)
    model_results: dict[str, Any] = {}
    for name, model in models.items():
        val_prob = model.probabilities(parts["validation"])
        threshold = choose_threshold(parts["validation"]["label"], val_prob)
        test_prob = model.probabilities(parts["test"])
        model_results[name] = {
            "validation_threshold": threshold,
            "test": classification_metrics(
                parts["test"]["label"], test_prob, threshold
            ),
            "hard_negative_transaction_fpr": _hard_negative_transaction_fpr(
                parts["test"], test_prob, threshold
            ),
            "per_archetype_recall": _per_archetype_recall(
                parts["test"], test_prob, threshold
            ),
        }

    graph_candidates = {
        name: result
        for name, result in model_results.items()
        if name.startswith("graph_enhanced")
    }
    best_name = max(
        graph_candidates,
        key=lambda name: (
            graph_candidates[name]["test"]["f1"],
            graph_candidates[name]["test"]["pr_auc"],
            name,
        ),
    )
    best_model = models[best_name]
    best_threshold = model_results[best_name]["validation_threshold"]

    report: dict[str, Any] = {
        "seed": ecosystem.seed,
        "ecosystem_digest": ecosystem.digest(),
        "synthetic_data_only": True,
        "split_counts": {name: len(part) for name, part in parts.items()},
        "split_ranges": {
            name: {
                "first_timestamp": int(part["timestamp"].min()),
                "last_timestamp": int(part["timestamp"].max()),
            }
            for name, part in parts.items()
        },
        "baseline_features": list(BASELINE_FEATURES),
        "graph_features": list(GRAPH_FEATURES),
        "models": model_results,
        "selected_graph_model": best_name,
        "generalization": {
            "test_archetypes_unseen_as_labels_during_fitting": sorted(
                set(parts["test"].loc[parts["test"]["label"] == 1, "archetype"])
                - set(parts["train"].loc[parts["train"]["label"] == 1, "archetype"])
            ),
            "per_archetype_recall": model_results[best_name][
                "per_archetype_recall"
            ],
            "unseen_archetype_holdout": _unseen_archetype_report(
                parts, holdout="H", seed=ecosystem.seed
            ),
        },
        "adversarial": adversarial_report(
            best_model, parts["test"], best_threshold
        ),
    }
    if include_ring_metrics:
        report["graph_detection"] = _ring_metrics(ecosystem, include_emerging)
    return report
