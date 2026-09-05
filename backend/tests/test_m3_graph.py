"""M3 tests: heterogeneous graph construction, integrity, causality."""

from __future__ import annotations

from backend.data.model import PAYEE_MERCHANT
from backend.graph.builder import build_graph, edges_between, graph_stats
from backend.graph.schema import (
    SESSION_USED_DEVICE,
    SESSION_USED_IP,
    TRANSACTION_AT_MERCHANT,
    TRANSACTION_USED_DEVICE,
    TRANSACTION_USED_INSTRUMENT,
    TRANSACTION_USED_IP,
    USER_CREATED_SESSION,
    USER_MADE_TRANSACTION,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
    USER_USED_IP,
)


class TestGraphIntegrity:
    def test_all_entities_are_nodes(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        for es in tiny_ecosystem.entities.values():
            for e in es:
                assert G.has_node(e.entity_id), f"missing node {e.entity_id}"

    def test_node_attribute_kind(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        for n, data in G.nodes(data=True):
            assert data["entity_type"] in {
                "USER", "DEVICE", "CARD", "BANK_ACCOUNT", "UPI_ID", "IP",
                "MERCHANT", "PHONE", "ADDRESS", "MANDATE", "SESSION", "TRANSACTION",
            }
            assert "created_at" in data

    def test_required_edge_attributes(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        for _u, _v, data in G.edges(data=True):
            assert data.get("rel_type"), f"{_u}-{_v} missing rel_type"
            assert data.get("timestamp") is not None
            assert data.get("weight", 0) > 0

    def test_money_flow_edges_reference_known_entities(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        user_set = {e.entity_id for e in tiny_ecosystem.entities["USER"]}
        for _u, v, data in G.edges(data=True):
            if data["rel_type"] in (USER_PAID_MERCHANT, USER_SENT_TO_USER):
                assert _u in user_set, f"money-flow source {_u} not a user"
                assert v in G.nodes()

    def test_mule_rings_have_directed_flows(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        mule_plants = [p for p in tiny_ecosystem.plants if p.archetype == "F"]
        if not mule_plants:
            return
        members = set(mule_plants[0].users)
        sent = [
            (_u, v)
            for _u, v, d in G.edges(data=True)
            if d["rel_type"] == USER_SENT_TO_USER and _u in members
        ]
        assert len(sent) >= 5, "directed p2p edges missing for mule ring"


class TestCausality:
    def test_as_of_truncation_is_causal(self, tiny_ecosystem):
        cutoff = tiny_ecosystem.payments[len(tiny_ecosystem.payments) // 2].timestamp
        G = build_graph(tiny_ecosystem, as_of=cutoff)
        max_edge_ts = max(d["timestamp"] for _, _, d in G.edges(data=True))
        max_node_ts = max(d["created_at"] for _, d in G.nodes(data=True))
        assert max_edge_ts <= cutoff, "future edges leaked into as_of graph"
        assert max_node_ts <= cutoff, "future nodes leaked into as_of graph"

    def test_as_of_monotonic_growth(self, tiny_ecosystem):
        cutoffs = (
            tiny_ecosystem.payments[0].timestamp,
            tiny_ecosystem.payments[len(tiny_ecosystem.payments) // 3].timestamp,
            tiny_ecosystem.payments[-1].timestamp,
        )
        sizes = [build_graph(tiny_ecosystem, as_of=c).number_of_edges() for c in cutoffs]
        assert sizes[0] <= sizes[1] <= sizes[2]

    def test_as_of_does_not_include_future_payments(self, tiny_ecosystem):
        cutoff = tiny_ecosystem.payments[10].timestamp
        G = build_graph(tiny_ecosystem, as_of=cutoff)
        txn_nodes = {n for n, d in G.nodes(data=True) if d["entity_type"] == "TRANSACTION"}
        future_txns = {p.transaction_id for p in tiny_ecosystem.payments if p.timestamp > cutoff}
        assert not (txn_nodes & future_txns), "future transactions present"


class TestDeterminism:
    def test_same_ecosystem_same_graph(self, tiny_ecosystem):
        def signature(G):
            return (
                G.number_of_nodes(),
                G.number_of_edges(),
                tuple(sorted((u, v, k, d["rel_type"]) for u, v, k, d in G.edges(keys=True, data=True))),
            )
        assert signature(build_graph(tiny_ecosystem)) == signature(build_graph(tiny_ecosystem))

    def test_different_ecosystems_differ(self):
        from backend.data.config import tiny_config
        from backend.data.generator import build_ecosystem

        eco_a = build_ecosystem(tiny_config(), seed=1)
        eco_b = build_ecosystem(tiny_config(), seed=2)
        sig = lambda G: (G.number_of_edges(), sorted((u, v, d["rel_type"]) for u, v, d in G.edges(data=True)))
        assert sig(build_graph(eco_a)) != sig(build_graph(eco_b))