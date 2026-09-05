"""M4 tests: graph-native feature semantics on controlled graphs."""

from __future__ import annotations

import networkx as nx
import pytest

from backend.features.graph_features import FEATURE_CATALOG, compute_user_features
from backend.features.projection import project_users


def _user_graph() -> nx.MultiDiGraph:
    """Hand-crafted minimal graph: 2 users share a device; U3 isolated; U1 has a card."""
    G = nx.MultiDiGraph()
    G.add_node("U1", entity_type="USER", created_at=100)
    G.add_node("U2", entity_type="USER", created_at=100)
    G.add_node("U3", entity_type="USER", created_at=100)
    G.add_node("D1", entity_type="DEVICE", created_at=50)
    G.add_node("D2", entity_type="DEVICE", created_at=50)
    G.add_node("C1", entity_type="CARD", created_at=50)
    G.add_node("M1", entity_type="MERCHANT", created_at=50)

    for u, d in (("U1", "D1"), ("U2", "D1"), ("U3", "D2")):
        G.add_edge(u, d, rel_type="USER_USED_DEVICE", timestamp=200, weight=1.0)
    G.add_edge("U1", "C1", rel_type="USER_OWNS_CARD", timestamp=200, weight=1.0)
    for t in (210, 220, 230):
        G.add_edge("U1", "M1", rel_type="USER_PAID_MERCHANT", timestamp=t, weight=1.0)
    return G


class TestFeatureFrame:
    def test_all_catalog_features_present(self, tiny_ecosystem):
        from backend.graph.builder import build_graph

        df = compute_user_features(build_graph(tiny_ecosystem))
        assert set(FEATURE_CATALOG) <= set(df.columns), set(FEATURE_CATALOG) - set(df.columns)

    def test_frame_indexed_by_users_no_nan(self, tiny_ecosystem):
        from backend.graph.builder import build_graph

        df = compute_user_features(build_graph(tiny_ecosystem))
        assert df.index.name == "user_id"
        assert not df.isna().any().any(), "NaN leaked into features"

    def test_values_nonnegative(self, tiny_ecosystem):
        from backend.graph.builder import build_graph

        df = compute_user_features(build_graph(tiny_ecosystem))
        numeric = df.select_dtypes("number")
        assert (numeric >= 0).all().all()

    def test_deterministic(self, tiny_ecosystem):
        from backend.graph.builder import build_graph

        G = build_graph(tiny_ecosystem)
        assert compute_user_features(G).equals(compute_user_features(G))


class TestFeatureSemantics:
    def test_shared_device_detection(self):
        """Sharing a device must show up for exactly the sharers."""
        df = compute_user_features(_user_graph(), as_of=300)
        assert df.loc["U1", "shared_device_count"] >= 1
        assert df.loc["U2", "shared_device_count"] >= 1
        assert df.loc["U3", "shared_device_count"] == 0
        assert df.loc["U3", "degree"] == 0
        assert df.loc["U1", "degree"] >= 1

    def test_shared_card_count(self):
        G = _user_graph()
        G.add_edge("U2", "C1", rel_type="USER_OWNS_CARD", timestamp=200, weight=1.0)
        df = compute_user_features(G, as_of=300)
        assert df.loc["U1", "shared_card_count"] >= 1
        assert df.loc["U2", "shared_card_count"] >= 1

    def test_weighted_degree_monotonic_in_shares(self):
        G = _user_graph()
        df_before = compute_user_features(G, as_of=300)
        G.add_node("D3", entity_type="DEVICE", created_at=50)
        G.add_edge("U1", "D3", rel_type="USER_USED_DEVICE", timestamp=200, weight=1.0)
        G.add_edge("U2", "D3", rel_type="USER_USED_DEVICE", timestamp=200, weight=1.0)
        df_after = compute_user_features(G, as_of=300)
        assert df_after.loc["U1", "weighted_degree"] > df_before.loc["U1", "weighted_degree"]

    def test_merchant_concentration_hhi(self):
        df = compute_user_features(_user_graph(), as_of=300)
        assert df.loc["U1", "merchant_concentration"] == pytest.approx(1.0)
        assert df.loc["U2", "merchant_concentration"] == 0.0

    def test_isolated_users_zero_coordination(self):
        df = compute_user_features(_user_graph(), as_of=300)
        assert df.loc["U3", "degree"] == 0
        assert df.loc["U3", "weighted_degree"] == 0
        assert df.loc["U3", "clustering"] == 0
        assert df.loc["U3", "betweenness"] == 0

    def test_money_flow_features(self):
        G = _user_graph()
        G.add_edge("U1", "U2", rel_type="USER_SENT_TO_USER", timestamp=250, weight=3.0)
        G.add_edge("U2", "U3", rel_type="USER_SENT_TO_USER", timestamp=251, weight=5.0)
        df = compute_user_features(G, as_of=300)
        assert df.loc["U1", "money_flow_out"] == 3.0
        assert df.loc["U2", "money_flow_in"] == 3.0
        assert df.loc["U2", "money_flow_out"] == 5.0
        assert df.loc["U3", "money_flow_in"] == 5.0

    def test_component_size_tracks_shared_infra(self):
        df = compute_user_features(_user_graph(), as_of=300)
        assert df.loc["U1", "component_size"] >= 2
        assert df.loc["U2", "component_size"] >= 2
        assert df.loc["U3", "component_size"] == 1