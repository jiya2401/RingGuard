"""M4 feature tests (part 2): projection semantics + temporal burst + integration."""

from __future__ import annotations

import pytest

from backend.features.projection import project_users
from backend.tests.test_m4_features import _user_graph


class TestProjection:
    def test_projection_is_user_only(self, tiny_ecosystem):
        from backend.graph.builder import build_graph

        P = project_users(build_graph(tiny_ecosystem))
        for n, d in P.nodes(data=True):
            assert d["entity_type"] == "USER"

    def test_projection_preserves_money_flow_direction(self):
        G = _user_graph()
        G.add_edge("U1", "U2", rel_type="USER_SENT_TO_USER", timestamp=250, weight=1.0)
        P = project_users(G)
        assert P.has_edge("U1", "U2", key="flow")
        assert not P.has_edge("U2", "U1", key="flow")

    def test_ip_sharing_alone_does_not_link(self):
        """Shared IP alone must NOT create a projection edge (spec §6)."""
        G = _user_graph()
        G.add_node("IP1", entity_type="IP", created_at=50)
        G.add_edge("U1", "IP1", rel_type="USER_USED_IP", timestamp=200, weight=1.0)
        G.add_edge("U2", "IP1", rel_type="USER_USED_IP", timestamp=200, weight=1.0)
        # U1/U2 already share a device, so the projection already links them; add
        # an isolated IP pair (U3 + a new user) that must stay disconnected.
        G.add_node("U4", entity_type="USER", created_at=100)
        G.add_node("IP2", entity_type="IP", created_at=50)
        G.add_edge("U3", "IP2", rel_type="USER_USED_IP", timestamp=200, weight=1.0)
        G.add_edge("U4", "IP2", rel_type="USER_USED_IP", timestamp=200, weight=1.0)
        P = project_users(G)
        assert not P.has_edge("U3", "U4", key="shared"), "IP-only sharing created an edge"


class TestTemporalBurst:
    def _burst_graph(self, times_suffix=30):
        """Toy graph whose U1 has transactions close together in time."""
        from backend.tests.test_m4_features import _user_graph

        G = _user_graph()
        G.add_node("TX0", entity_type="TRANSACTION", payer="U1", created_at=200)
        G.add_edge("U1", "TX0", rel_type="USER_MADE_TRANSACTION", timestamp=200, weight=1.0)
        G.add_edge("TX0", "M1", rel_type="TRANSACTION_AT_MERCHANT", timestamp=200, weight=1.0)
        for i in range(1, 20):
            t = 200 + i * times_suffix
            G.add_node(f"TX{i}", entity_type="TRANSACTION", payer="U1", created_at=t)
            G.add_edge("U1", f"TX{i}", rel_type="USER_MADE_TRANSACTION", timestamp=t, weight=1.0)
            G.add_edge(f"TX{i}", "M1", rel_type="TRANSACTION_AT_MERCHANT", timestamp=t, weight=1.0)
        return G

    def test_bursty_user_high_score(self):
        from backend.features.graph_features import compute_user_features

        df = compute_user_features(self._burst_graph(times_suffix=30), as_of=1000)
        assert df.loc["U1", "temporal_burst_score"] >= 0.8

    def test_spread_user_low_score(self):
        from backend.features.graph_features import compute_user_features

        # Transactions 12h apart -> no burst.
        df = compute_user_features(self._burst_graph(times_suffix=43200), as_of=1_000_000)
        assert df.loc["U1", "temporal_burst_score"] <= 0.3


class TestCatalyst:
    """Abuse-ring members must show higher coordination features than isolated normals."""

    def test_abuse_rings_denser_than_isolated_normals(self, tiny_ecosystem):
        from backend.graph.builder import build_graph
        from backend.features.graph_features import compute_user_features

        G = build_graph(tiny_ecosystem)
        df = compute_user_features(G)
        abuse = {u for p in tiny_ecosystem.plants for u in p.users if p.archetype is not None}
        isolated = set(df[df.degree == 0].index)
        ring_users = abuse & set(df.index)
        assert ring_users, "expected some abuse users in feature frame"
        mean_deg_rings = df.loc[list(ring_users), "degree"].mean()
        mean_deg_isolated = df.loc[list(isolated), "degree"].mean() if len(isolated) else 0
        assert mean_deg_rings > mean_deg_isolated, "rings not denser than isolated normals"