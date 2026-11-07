"""Multi-seed evaluation of covert-vs-sanctioned detection (new work)."""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from backend.detection.rings import discover_rings
from backend.graph.builder import build_graph
from backend.risk.engine import score_rings
from backend.swarm.adapter import events_to_ecosystem
from backend.swarm.features import FEATURES, ring_features
from backend.swarm.scenarios import Scenario

MIN_COVER = 0.6   # a planted group counts as found if one ring holds >=60% of its agents


@dataclass
class Row:
    seed: int
    kind: str            # covert | sanctioned
    found: bool
    feats: dict
    rg_risk: float       # unmodified RingGuard risk score (0 when not found)


def _true(a: str, to_true: dict[str, str]) -> str:
    return to_true.get(a, a)


def group_rows(events, scenario: Scenario, to_true: dict[str, str] | None = None, seed: int = 0) -> list[Row]:
    """Run discovery + scoring and return one row per planted group."""
    to_true = to_true or {}
    eco = events_to_ecosystem(events, seed=seed)
    G = build_graph(eco)
    rings = score_rings(discover_rings(G, min_users=3), G)
    planted: dict[tuple[str, int], set[str]] = {}
    for a, (k, g) in scenario.truth.items():
        if k != "independent":
            planted.setdefault((k, g), set()).add(a)
    rows = []
    for (kind, g), agents in sorted(planted.items()):
        best, best_cov = None, 0.0
        for r in rings:
            cov = len(agents & {_true(u, to_true) for u in r.users}) / len(agents)
            if cov > best_cov:
                best, best_cov = r, cov
        if best is not None and best_cov >= MIN_COVER:
            feats = ring_features(events, set(best.users), scenario.sanctioned)
            rows.append(Row(seed, kind, True, feats, float(best.risk_score or 0)))
        else:
            rows.append(Row(seed, kind, False, {f: 0.0 for f in FEATURES}, 0.0))
    return rows


def _x(rows):
    return np.array([[r.feats[f] for f in FEATURES] for r in rows])


def _threshold(scores: np.ndarray, y: np.ndarray) -> float:
    """Balanced-accuracy-optimal threshold; the middle of the best range, not its edge.

    Picking the edge overfits when training data separate perfectly, so a small
    shift in the test scores flips every decision.
    """
    uniq = sorted(set(scores.tolist()))
    if len(uniq) == 1:
        return uniq[0]
    cands = [uniq[0] - 1e-9] + [(a + b) / 2 for a, b in zip(uniq, uniq[1:])]
    bals = []
    for t in cands:
        pred = scores >= t
        bals.append(0.5 * (pred[y == 1].mean() + (~pred[y == 0]).mean()))
    best = max(bals)
    good = [t for t, b in zip(cands, bals) if abs(b - best) < 1e-12]
    return float(good[len(good) // 2])


def fit_models(train: list[Row]) -> dict:
    y = np.array([1 if r.kind == "covert" else 0 for r in train])
    X = _x(train)
    lr = LogisticRegression(max_iter=1000, class_weight="balanced").fit(X, y)
    cols = {f: i for i, f in enumerate(FEATURES)}
    scorers = {
        "ringguard_unmodified": lambda rows: np.array([r.rg_risk for r in rows]),
        "event_volume_baseline": lambda rows: np.array([r.feats["events_per_agent"] for r in rows]),
        "any_shared_resource": lambda rows: np.array([1.0 if r.found else 0.0 for r in rows]),
        "policy_only(unsanctioned_share)": lambda rows: np.array([r.feats["unsanc_share"] for r in rows]),
        "swarm_logreg": lambda rows: lr.predict_proba(_x(rows))[:, 1] * np.array([1.0 if r.found else 0.0 for r in rows]),
    }
    thr = {n: _threshold(f(train), y) for n, f in scorers.items()}
    return {"scorers": scorers, "thr": thr, "lr": lr, "cols": cols}


def _metrics(scores, y, thr):
    pred = scores >= thr
    auc = roc_auc_score(y, scores) if len(set(y)) == 2 else float("nan")
    return auc, pred[y == 1].mean(), pred[y == 0].mean()


def evaluate(models: dict, test: list[Row], n_boot: int = 300, seed: int = 0) -> dict:
    """Metrics with bootstrap CIs, resampling whole seeds."""
    seeds = sorted({r.seed for r in test})
    by_seed = {s: [r for r in test if r.seed == s] for s in seeds}
    rng = random.Random(seed)
    out = {}
    for name, f in models["scorers"].items():
        thr = models["thr"][name]
        vals = {"auroc": [], "covert_tpr": [], "sanctioned_fpr": []}
        for b in range(n_boot):
            rows = [r for s in (rng.choice(seeds) for _ in seeds) for r in by_seed[s]]
            y = np.array([1 if r.kind == "covert" else 0 for r in rows])
            a, t, p = _metrics(f(rows), y, thr)
            vals["auroc"].append(a); vals["covert_tpr"].append(t); vals["sanctioned_fpr"].append(p)
        y = np.array([1 if r.kind == "covert" else 0 for r in test])
        a, t, p = _metrics(f(test), y, thr)
        pt = {"auroc": a, "covert_tpr": t, "sanctioned_fpr": p}
        out[name] = {k: {"value": round(float(pt[k]), 3),
                         "ci95": [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]}
                     for k, v in vals.items()}
    out["_n_groups_found_pct"] = round(100 * float(np.mean([r.found for r in test])), 1)
    out["_n_test_groups"] = len(test)
    return out 