"""M3 relation-semantics tests: projected graphs and edge semantics."""

from __future__ import annotations

from backend.data.model import PAYEE_MERCHANT
from backend.graph.builder import build_graph
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
    USER_USED_DEVICE,
    USER_USED_IP,
)


class TestRelationSemantics:
    def test_transaction_edges_exist(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        for p in tiny_ecosystem.payments[:20]:
            assert G.has_edge(p.payer, p.transaction_id, USER_MADE_TRANSACTION)
            assert G.has_edge(p.transaction_id, p.instrument, TRANSACTION_USED_INSTRUMENT)
            assert G.has_edge(p.transaction_id, p.ip_id, TRANSACTION_USED_IP)
            assert G.has_edge(p.transaction_id, p.device_id, TRANSACTION_USED_DEVICE)
            if p.payee_type == PAYEE_MERCHANT:
                assert G.has_edge(p.transaction_id, p.payee, TRANSACTION_AT_MERCHANT)
                assert G.has_edge(p.payer, p.payee, USER_PAID_MERCHANT)

    def test_session_edges_exist(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        sessions = tiny_ecosystem.entities["SESSION"]
        if not sessions:
            return
        sample = sessions[0]
        attrs = sample.attributes
        assert G.has_edge(attrs["user"], sample.entity_id, USER_CREATED_SESSION)
        if attrs.get("device"):
            assert G.has_edge(sample.entity_id, attrs["device"], SESSION_USED_DEVICE)
            assert G.has_edge(attrs["user"], attrs["device"], USER_USED_DEVICE)
        if attrs.get("ip"):
            assert G.has_edge(sample.entity_id, attrs["ip"], SESSION_USED_IP)
            assert G.has_edge(attrs["user"], attrs["ip"], USER_USED_IP)

    def test_user_used_ip_has_timestamps(self, tiny_ecosystem):
        G = build_graph(tiny_ecosystem)
        ip_edges = [d for _, _, d in G.edges(data=True) if d["rel_type"] == USER_USED_IP]
        assert ip_edges
        assert all(d["timestamp"] > 0 for d in ip_edges)

    def test_graph_can_be_pruned_to_user_layer(self, tiny_ecosystem):
        """The graph supports projection to any entity layer for analysis."""
        G = build_graph(tiny_ecosystem)
        users = {e.entity_id for e in tiny_ecosystem.entities["USER"]}
        device_edges = [
            (u, d) for u, d, data in G.edges(data=True)
            if u in users and data["rel_type"] == USER_USED_DEVICE
        ]
        assert device_edges, "projected user-device layer should not be empty"
        # Every shared device must connect to at least two users to form coordination chains.
        shared = {}
        for u, d in device_edges:
            shared.setdefault(d, set()).add(u)
        assert any(len(v) >= 2 for v in shared.values()), "expected at least one shared device"