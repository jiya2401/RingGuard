"""M6 tests: multi-layer risk engine (spec §11).

Verifies the M6 acceptance gate — household rings score below abuse
rings, risk is deterministic and feature-derived — plus the scoring
contract (drivers / signals / recommendation), recommendation tiers,
and causal `as_of` scoring on a hand-built ring.
"""

from __future__ import annotations

import networkx as nx
import pytest

from backend.data.config import demo_config, tiny_config
from backend.data.generator import build_ecosystem
from backend.data.model import ARCHETYPES
from backend.detection.rings import Ring, discover_rings
from backend.graph.builder import build_graph
from backend.graph.schema import (
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
)
from backend.risk.engine import (
    RECOMMENDATION_TIERS,
    WEIGHTS,
    _recommendation,
    score_rings,
)

ACTIONS = {action for _, action in RECOMMENDATION_TIERS}


@pytest.fixture(scope="module")
def scored_tiny():
    eco = build_ecosystem(tiny_config(), seed=7)
    G = build_graph(eco)
    return eco, G, score_rings(discover_rings(G), G)


class TestScoringContract:
    """Every scored ring carries the full interpretable evidence contract."""

    def test_score_confidence_ranges(self, scored_tiny):
        _, _, rings = scored_tiny
        assert rings
        for r in rings:
            assert isinstance(r.risk_score, int)
            assert 0 <= r.risk_score <= 100, r.ring_id
            assert 0 <= r.confidence <= 100, r.ring_id

    def test_recommendation_valid_and_consistent(self, scored_tiny):
        _, _, rings = scored_tiny
        for r in rings:
            assert r.recommended_action in ACTIONS, r.ring_id
            assert r.recommended_action == _recommendation(r.risk_score)

    def test_drivers_present_and_sorted(self, scored_tiny):
        _, _, rings = scored_tiny
        for r in rings:
            assert r.drivers, f"WHY-FLAGGED drivers missing for {r.ring_id}"
            contribs = [d["contribution"] for d in r.drivers]
            assert contribs == sorted(contribs, reverse=True)
            assert {d["layer"] for d in r.drivers} == set(WEIGHTS)
            assert all(d["detail"] for d in r.drivers)

    def test_signals_have_semantics(self, scored_tiny):
        _, _, rings = scored_tiny
        for r in rings:
            assert r.risk_signals and r.legitimate_signals, r.ring_id
            for sig in r.risk_signals + r.legitimate_signals:
                assert set(sig) == {"signal", "value", "interpretation"}
                assert 0.0 <= sig["value"] <= 1.0
                assert sig["interpretation"], sig["signal"]

    def test_to_dict_exposes_new_fields(self, scored_tiny):
        _, _, rings = scored_tiny
        d = rings[0].to_dict()
        assert {"drivers", "recommended_action"} <= set(d)


class TestDeterminism:
    def test_same_graph_same_scores(self, scored_tiny):
        eco, G, rings = scored_tiny
        again = score_rings(discover_rings(build_graph(eco)), build_graph(eco))
        assert [(r.ring_id, r.risk_score, r.confidence, r.recommended_action,
                 r.drivers) for r in rings] == [
            (r.ring_id, r.risk_score, r.confidence, r.recommended_action, r.drivers)
            for r in again
        ]


class TestRecommendationTiers:
    @pytest.mark.parametrize(
        "score,expected",
        [(100, "ESCALATE"), (80, "ESCALATE"), (79, "INVESTIGATE"),
         (65, "INVESTIGATE"), (64, "REVIEW"), (45, "REVIEW"),
         (44, "MONITOR"), (25, "MONITOR"), (24, "DISMISS"), (0, "DISMISS")],
    )
    def test_boundaries(self, score, expected):
        assert _recommendation(score) == expected

    def test_tiers_sorted_descending(self):
        thresholds = [t for t, _ in RECOMMENDATION_TIERS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


class TestSeparation:
    """M6 gate: household hard negatives must not out-score abuse rings."""

    def _plants(self, eco, rings):
        abuse, household = [], None
        for p in eco.plants:
            hits = [r for r in rings if set(p.users) <= set(r.users)]
            if not hits:
                continue
            if p.archetype in ARCHETYPES:
                abuse.append(max(hits, key=lambda r: r.risk_score))
            else:
                household = max(hits, key=lambda r: r.risk_score)
        return abuse, household

    def test_household_below_abuse(self, scored_tiny):
        eco, _, rings = scored_tiny
        abuse, household = self._plants(eco, rings)
        assert abuse and household is not None
        assert household.risk_score < max(r.risk_score for r in abuse)
        assert household.risk_score < sum(r.risk_score for r in abuse) / len(abuse)

    def test_household_rings_get_counter_evidence(self, scored_tiny):
        """Households must carry non-trivial legitimate-sharing evidence."""
        eco, G, rings = scored_tiny
        hh_plants = [p for p in eco.plants if p.archetype not in ARCHETYPES]
        assert hh_plants
        for p in hh_plants:
            for r in rings:
                if set(p.users) <= set(r.users):
                    legit = {s["signal"]: s["value"] for s in r.legitimate_signals}
                    top = max(legit.values(), default=0.0)
                    assert top > 0.0, (
                        f"{r.ring_id} covering {p.archetype} shows no "
                        f"legitimate-sharing evidence"
                    )
                    break


class TestCausalScoring:
    """Risk must grow with the evidence actually present at `as_of`."""

    @staticmethod
    def _ring_graph() -> nx.MultiDiGraph:
        """4 accounts, 2 shared devices, 1 shared card; burst + mule flow late."""
        G = nx.MultiDiGraph()
        for i in range(1, 5):
            G.add_node(f"U{i}", entity_type="USER", created_at=1_000 + i)
        G.add_node("D1", entity_type="DEVICE")
        G.add_node("D2", entity_type="DEVICE")
        G.add_node("C1", entity_type="CARD")
        G.add_node("M1", entity_type="MERCHANT")
        for u in ("U1", "U2", "U3", "U4"):
            G.add_edge(u, "D1", rel_type=USER_USED_DEVICE, timestamp=1_100, weight=1.0)
            G.add_edge(u, "D2", rel_type=USER_USED_DEVICE, timestamp=1_105, weight=1.0)
            G.add_edge(u, "C1", rel_type=USER_OWNS_CARD, timestamp=1_120, weight=1.0)
        t0 = 100_000
        for k in range(8):  # 8 payments inside one hour
            G.add_edge(f"U{(k % 4) + 1}", "M1", rel_type=USER_PAID_MERCHANT,
                       timestamp=t0 + 30 * k, weight=1.0)
        G.add_edge("U1", "U2", rel_type=USER_SENT_TO_USER, timestamp=t0 + 400, weight=500)
        G.add_edge("U2", "U3", rel_type=USER_SENT_TO_USER, timestamp=t0 + 450, weight=480)
        G.add_edge("U3", "U4", rel_type=USER_SENT_TO_USER, timestamp=t0 + 500, weight=470)
        return G

    @staticmethod
    def _truncate(G: nx.MultiDiGraph, as_of: int) -> nx.MultiDiGraph:
        H = nx.MultiDiGraph()
        H.add_nodes_from((n, dict(d)) for n, d in G.nodes(data=True))
        for u, v, d in G.edges(data=True):
            if d.get("timestamp", 0) <= as_of:
                H.add_edge(u, v, **d)
        return H

    @staticmethod
    def _candidate() -> Ring:
        return Ring(ring_id="R-TEST", users=["U1", "U2", "U3", "U4"],
                    structural_score=0.7)

    def test_risk_grows_with_evidence(self):
        G_full = self._ring_graph()
        G_early = self._truncate(G_full, 2_000)  # only creation + device/card edges
        early = score_rings([self._candidate()], G_early, as_of=2_000)[0]
        full = score_rings([self._candidate()], G_full, as_of=100_600)[0]

        assert 0 <= early.risk_score < full.risk_score <= 100
        assert full.risk_score - early.risk_score >= 20, (
            "burst + mule flow must move the score materially"
        )
        assert full.confidence > early.confidence
        assert full.recommended_action in {"INVESTIGATE", "ESCALATE"}
        assert early.recommended_action in {"MONITOR", "REVIEW", "DISMISS"}

    def test_early_drivers_reflect_early_evidence(self):
        G_full = self._ring_graph()
        early = score_rings([self._candidate()], self._truncate(G_full, 2_000),
                            as_of=2_000)[0]
        by_layer = {d["layer"]: d["contribution"] for d in early.drivers}
        assert by_layer["money_flow"] == 0.0, "no internal transfers exist at as_of"
        assert by_layer["structural"] > by_layer["temporal"]


@pytest.fixture(scope="module")
def scored_demo():
    eco = build_ecosystem(demo_config(), seed=42)
    G = build_graph(eco)
    return eco, score_rings(discover_rings(G), G)


class TestDemoScale:
    """Bugs that only appear at spec §46 demo scale (regression guard)."""

    def test_contract_holds_at_demo_scale(self, scored_demo):
        _, rings = scored_demo
        assert rings
        for r in rings:
            assert 0 <= r.risk_score <= 100
            assert r.recommended_action in ACTIONS
            assert r.drivers

    def test_abuse_outranks_hard_negatives_at_demo_scale(self, scored_demo):
        eco, rings = scored_demo
        hn = {u for p in eco.plants if p.archetype not in ARCHETYPES for u in p.users}
        abuse_scores = [
            r.risk_score for r in rings
            if any(p.archetype in ARCHETYPES and set(p.users) <= set(r.users)
                   for p in eco.plants)
        ]
        hn_scores = [r.risk_score for r in rings
                     if set(r.users) & hn and not any(
                         p.archetype in ARCHETYPES and set(p.users) <= set(r.users)
                         for p in eco.plants)]
        assert abuse_scores and hn_scores
        assert max(abuse_scores) > max(hn_scores), (
            "some hard-negative community out-scores every abuse ring"
        )

