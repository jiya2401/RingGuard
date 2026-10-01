"""M11-M12: propagation, blast radius, counterfactuals, and Ring DNA."""

from __future__ import annotations

import networkx as nx

from backend.detection.rings import Ring
from backend.graph.schema import (
    USER_MADE_TRANSACTION,
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
)
from backend.risk.counterfactual import recompute_without
from backend.risk.dna import ring_dna
from backend.risk.emerging import score_at
from backend.risk.propagation import calculate_blast_radius, propagate_risk


def _graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["window_start"] = 0
    for user in ("U1", "U2", "U3", "U4"):
        graph.add_node(user, entity_type="USER", created_at=10)
    graph.add_node("D1", entity_type="DEVICE", created_at=0)
    graph.add_node("D2", entity_type="DEVICE", created_at=0)
    graph.add_node("C1", entity_type="CARD", created_at=0)
    graph.add_node("M1", entity_type="MERCHANT", created_at=0)
    for user in ("U1", "U2", "U3"):
        graph.add_edge(user, "D1", rel_type=USER_USED_DEVICE, timestamp=20, weight=1.0)
        graph.add_edge(user, "C1", rel_type=USER_OWNS_CARD, timestamp=21, weight=1.0)
        graph.add_edge(user, "M1", rel_type=USER_PAID_MERCHANT, timestamp=100, weight=1.0)
    graph.add_edge("U3", "D2", rel_type=USER_USED_DEVICE, timestamp=22, weight=1.0)
    graph.add_edge("U4", "D2", rel_type=USER_USED_DEVICE, timestamp=22, weight=1.0)
    graph.add_edge("U2", "U3", rel_type=USER_SENT_TO_USER, timestamp=110, weight=1.0)
    graph.add_node("TX1", entity_type="TRANSACTION", created_at=100, amount=250.0)
    graph.add_edge("U1", "TX1", rel_type=USER_MADE_TRANSACTION, timestamp=100, weight=1.0)
    return graph


class TestPropagation:
    def test_decay_and_paths_follow_real_projection(self):
        rows = propagate_risk(_graph(), {"U1": 80.0}, max_hops=2, decay=0.5)
        by_user = {row["user_id"]: row for row in rows}
        assert by_user["U1"]["risk"] == 80.0
        assert by_user["U2"]["risk"] == 40.0
        assert by_user["U4"]["risk"] == 20.0
        assert by_user["U4"]["path"][0] == "U1"

    def test_blast_radius_and_exposure_are_grounded(self):
        report = calculate_blast_radius(_graph(), ["U1"], max_hops=1)
        assert set(report["affected_users"]) == {"U1", "U2", "U3"}
        assert report["estimated_simulated_exposure"] == 250.0
        assert report["data_label"] == "SIMULATED DATA"
        assert "D1" in report["affected_entities"]["DEVICE"]


class TestCounterfactual:
    def test_recompute_matches_fresh_reduced_graph(self):
        graph = _graph()
        users = ["U1", "U2", "U3"]
        result = recompute_without(graph, users, remove_nodes=["D1"], as_of=120)
        reduced = graph.copy()
        reduced.remove_node("D1")
        expected = score_at(reduced, users, 120)
        assert result["after_risk"] == expected.risk_score
        assert result["removed"]["nodes"] == ["D1"]
        assert result["risk_delta"] == result["after_risk"] - result["before_risk"]

    def test_ring_dna_is_stable_and_evidence_derived(self):
        scored = score_at(_graph(), ["U1", "U2", "U3"], 120)
        scored.ring_id = "R-TEST"
        first = ring_dna(scored)
        second = ring_dna(scored)
        assert first == second
        assert len(first["fingerprint"]) == 16
        assert first["risk_score"] == scored.risk_score
