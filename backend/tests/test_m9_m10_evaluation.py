"""M9-M10: chronological evaluation, baselines, generalization, robustness."""

from __future__ import annotations

from backend.data.config import tiny_config
from backend.data.generator import build_ecosystem
from backend.evaluation.metrics import evaluate_ecosystem
from backend.evaluation.splits import build_transaction_frame, split_frames


def _ecosystem():
    return build_ecosystem(tiny_config(n_transactions=900), seed=7)


class TestLeakageFreeFrame:
    def test_split_is_forward_and_disjoint(self):
        frame = build_transaction_frame(_ecosystem())
        parts = split_frames(frame)
        assert set(parts["train"].transaction_id).isdisjoint(
            set(parts["validation"].transaction_id)
        )
        assert set(parts["train"].transaction_id).isdisjoint(
            set(parts["test"].transaction_id)
        )
        assert parts["train"].timestamp.max() < parts["validation"].timestamp.min()
        assert parts["validation"].timestamp.max() < parts["test"].timestamp.min()

    def test_current_event_does_not_leak_into_prior_counters(self):
        frame = build_transaction_frame(_ecosystem())
        first = frame.sort_values(["timestamp", "transaction_id"]).iloc[0]
        assert first["payer_prior_txns"] == 0
        assert first["device_prior_users"] == 0
        assert first["instrument_prior_users"] == 0
        assert first["ip_prior_users"] == 0

    def test_frame_is_deterministic(self):
        a = build_transaction_frame(_ecosystem())
        b = build_transaction_frame(_ecosystem())
        assert a.equals(b)


class TestModelComparison:
    def test_required_models_and_metrics(self):
        report = evaluate_ecosystem(
            _ecosystem(), include_ring_metrics=False, include_emerging=False
        )
        assert set(report["models"]) == {
            "baseline_logistic_regression",
            "baseline_random_forest",
            "graph_enhanced_logistic_regression",
            "graph_enhanced_random_forest",
        }
        for result in report["models"].values():
            metrics = result["test"]
            for name in (
                "precision",
                "recall",
                "f1",
                "roc_auc",
                "pr_auc",
                "false_positive_rate",
                "precision_at_k",
            ):
                assert 0.0 <= metrics[name] <= 1.0
            assert result["hard_negative_transaction_fpr"] >= 0.0

    def test_adversarial_results_are_measured_not_constants(self):
        report = evaluate_ecosystem(
            _ecosystem(), include_ring_metrics=False, include_emerging=False
        )
        assert set(report["adversarial"]) == {
            "original",
            "infrastructure_dilution_75pct",
            "timing_smear",
            "combined_evasion",
        }
        assert report["generalization"]["per_archetype_recall"]
        holdout = report["generalization"]["unseen_archetype_holdout"]
        assert holdout["held_out_archetype"] == "H"
        assert holdout["available"] is True
        assert holdout["training_rows_removed"] > 0
        assert 0.0 <= holdout["metrics"]["recall"] <= 1.0
        assert report == evaluate_ecosystem(
            _ecosystem(), include_ring_metrics=False, include_emerging=False
        )
