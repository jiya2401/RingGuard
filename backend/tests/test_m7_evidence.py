"""M7 tests: legitimate-sharing evidence, WHY-FLAGGED / WHY-NOT-FRAUD
renderers, and the hard-negative benchmark (spec §6, §7, §24, §25, §39).

Gate under test: the system must articulate *why not fraud* with the
same evidence the engine weighed, and must report its hard-negative
false-positive rate instead of hiding it.
"""

from __future__ import annotations

import pytest

from backend.data.config import demo_config, tiny_config
from backend.data.generator import build_ecosystem
from backend.data.model import ARCHETYPES
from backend.detection.rings import Ring, discover_rings
from backend.evaluation.hard_negatives import (
    DEFAULT_THRESHOLDS,
    benchmark_hard_negatives,
    false_positive_rate,
)
from backend.explanations.why import explain_ring, why_flagged, why_not_fraud
from backend.graph.builder import build_graph
from backend.risk.engine import score_rings
from backend.risk.legitimacy import collect_legitimate_evidence, ring_txn_times


@pytest.fixture(scope="module")
def tiny_scored():
    eco = build_ecosystem(tiny_config(), seed=7)
    G = build_graph(eco)
    rings = score_rings(discover_rings(G), G)
    return eco, G, rings


def _plant_rings(eco, rings, abuse: bool):
    """Best discovered ring per planted community of the requested kind."""
    out = []
    for p in eco.plants:
        if (p.archetype in ARCHETYPES) != abuse:
            continue
        hits = [r for r in rings if set(p.users) <= set(r.users)]
        if hits:
            out.append((p, max(hits, key=lambda r: r.risk_score)))
    return out


class TestWhyFlagged:
    def test_block_contract(self, tiny_scored):
        _, _, rings = tiny_scored
        block = why_flagged(rings[0])
        assert block["risk_score"] == rings[0].risk_score
        assert block["confidence"] == rings[0].confidence
        assert block["primary_pattern"] == rings[0].primary_pattern
        assert block["recommended_action"] == rings[0].recommended_action
        contribs = [d["contribution"] for d in block["primary_drivers"]]
        assert contribs == sorted(contribs, reverse=True)
        assert all(d["explanation"] for d in block["primary_drivers"])
        assert 1 <= len(block["evidence"]) <= 4
        for s in block["evidence"]:
            assert 0.0 <= s["value"] <= 1.0
            assert s["explanation"], s["signal"]

    def test_unscored_ring_rejected(self):
        with pytest.raises(ValueError, match="not been scored"):
            why_flagged(Ring(ring_id="R-X", users=["U1"], structural_score=0.5))

    def test_explain_ring_combines_both(self, tiny_scored):
        eco, G, rings = tiny_scored
        ring = rings[0]
        evidence = collect_legitimate_evidence(G, set(ring.users))
        both = explain_ring(ring, evidence)
        assert set(both) == {"why_flagged", "why_not_fraud"}
        assert both["why_flagged"]["ring_id"] == ring.ring_id


class TestWhyNotFraud:
    def test_household_gets_strong_counter_evidence(self, tiny_scored):
        eco, G, rings = tiny_scored
        hh = _plant_rings(eco, rings, abuse=False)
        assert hh, "no hard-negative community produced a discovered ring"
        for plant, ring in hh:
            evidence = collect_legitimate_evidence(G, set(ring.users))
            block = why_not_fraud(ring, evidence)
            signals = {f["signal"] for f in block["counter_evidence"]}
            assert block["verdict"] in {"STRONG", "MODERATE"}, plant.ring_id
            assert block["summary"].startswith(block["verdict"])
            assert block["what_was_checked"] == [
                f["signal"] for f in block["counter_evidence"]
            ]
            # Household sharing must be recognised as such somewhere.
            assert signals & {"shared_address_coverage", "account_age_stability"}, (
                f"{plant.ring_id}: no address/stability counter-evidence"
            )

    def test_counter_evidence_is_what_the_engine_weighed(self, tiny_scored):
        """Renderer must show the exact factors the score was deducted with."""
        eco, G, rings = tiny_scored
        for ring in rings:
            evidence = collect_legitimate_evidence(G, set(ring.users))
            assert ring.legitimate_signals == evidence["factors"], ring.ring_id

    def test_abuse_rings_have_weak_counter_evidence(self, tiny_scored):
        eco, G, rings = tiny_scored
        abuse = _plant_rings(eco, rings, abuse=True)
        assert abuse
        for plant, ring in abuse:
            evidence = collect_legitimate_evidence(G, set(ring.users))
            assert evidence["verdict"] in {"WEAK", "NONE"}, (
                f"abuse plant {plant.ring_id} carries {evidence['verdict']} "
                f"legitimate-sharing evidence"
            )

    def test_graph_free_fallback_matches_fresh_collection(self, tiny_scored):
        """Stored signals alone reproduce the fresh verdict (no graph needed)."""
        eco, G, rings = tiny_scored
        hh = _plant_rings(eco, rings, abuse=False)
        assert hh
        for plant, ring in hh:
            users = set(ring.users)
            fresh = collect_legitimate_evidence(
                G, users, n_txn=len(ring_txn_times(G, users))
            )
            fallback = why_not_fraud(ring)  # no evidence passed
            assert fallback["verdict"] == fresh["verdict"], plant.ring_id
            assert fallback["legitimacy_score"] == pytest.approx(
                fresh["score"], abs=0.01
            )
            assert fallback["counter_evidence"]
        both = explain_ring(hh[0][1])  # both blocks, graph-free
        assert {"why_flagged", "why_not_fraud"} <= set(both)


class TestHardNegativeBenchmark:
    """Spec §6/§39: the FPR must be measured and reported, not hidden."""

    def test_benchmark_contract(self, tiny_scored):
        eco, G, rings = tiny_scored
        report = benchmark_hard_negatives(eco, G, rings)
        assert report["abuse_plants"] and report["hard_negative_plants"]
        assert set(report["per_threshold"]) == set(DEFAULT_THRESHOLDS)
        assert report["abuse_risk_scores"] and report["hard_negative_risk_scores"]

    def test_rates_monotone_in_threshold(self, tiny_scored):
        eco, G, rings = tiny_scored
        report = benchmark_hard_negatives(eco, G, rings)
        per = report["per_threshold"]
        ts = sorted(per, reverse=True)
        for a, b in zip(ts, ts[1:]):
            assert per[a]["hard_negative_fpr"] <= per[b]["hard_negative_fpr"]
            assert per[a]["abuse_detection_rate"] <= per[b]["abuse_detection_rate"]

    def test_zero_fpr_threshold_exists(self, tiny_scored):
        """Somewhere on the curve the queue is clean of hard negatives."""
        eco, G, rings = tiny_scored
        report = benchmark_hard_negatives(eco, G, rings)
        assert any(v["hard_negative_fpr"] == 0.0 for v in report["per_threshold"].values())

    def test_detection_beats_fpr_on_the_curve(self, tiny_scored):
        eco, G, rings = tiny_scored
        report = benchmark_hard_negatives(eco, G, rings)
        assert report["separation"] > 0
        best = max(
            report["per_threshold"].values(),
            key=lambda v: v["abuse_detection_rate"] - v["hard_negative_fpr"],
        )
        assert best["abuse_detection_rate"] > best["hard_negative_fpr"]

    def test_false_positive_rate_helper(self, tiny_scored):
        _, _, rings = tiny_scored
        fpr = false_positive_rate(rings, threshold=65)
        assert 0.0 <= fpr <= 1.0
        assert fpr == false_positive_rate(rings, threshold=65)  # deterministic
        assert false_positive_rate([], threshold=45) == 0.0


@pytest.fixture(scope="module")
def demo_scored():
    eco = build_ecosystem(demo_config(), seed=42)
    G = build_graph(eco)
    return eco, G, score_rings(discover_rings(G), G)


class TestDemoScale:
    """Hard-negative claims must also hold at §46 demo scale."""

    def test_benchmark_separation(self, demo_scored):
        eco, G, rings = demo_scored
        report = benchmark_hard_negatives(eco, G, rings)
        assert report["mean_abuse_risk"] > report["mean_hard_negative_risk"]
        # Households specifically: the canonical §6 hard negative.
        hh = [p for p in report["hard_negative_plants"] if p["archetype"] == "household"]
        assert hh and all((p["risk_score"] or 0) < 25 for p in hh), (
            "a household community reached MONITOR or above"
        )

    def test_queue_noise_is_measured(self, demo_scored):
        _, _, rings = demo_scored
        assert 0.0 <= false_positive_rate(rings, threshold=45) < 1.0

