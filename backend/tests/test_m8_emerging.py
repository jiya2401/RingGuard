"""M8 tests: temporal + emerging-risk engine (spec §8, §16).

Verifies the M8 gate — the emerging ring is detected **before** it
fully materialises, with the lead time quantified — plus causal
snapshotting, trajectory monotonicity, grounded what-changed deltas,
and determinism.
"""

from __future__ import annotations

import networkx as nx
import pytest

from backend.data.config import demo_config
from backend.data.generator import build_ecosystem
from backend.graph.builder import build_graph
from backend.graph.schema import (
    USER_LIVES_AT_ADDRESS,
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_USED_DEVICE,
)
from backend.risk.emerging import (
    DAY_S,
    emerging_report,
    graph_t0,
    risk_history,
    snapshot_at,
)

T0 = 10 * DAY_S  # ecosystem origin used by the hand-built graphs


def _staged_ring_graph() -> nx.MultiDiGraph:
    """An abuse ring that grows over two weeks (spec §5.H).

    Day 0: 2 accounts, day 2: +1, day 4: +2, day 6: +3. Members share
    2 devices and 1 card and burst a few payments on joining. Plus a
    legitimate household (old, same address, family card, diverse
    shopping) that must NOT escalate.
    """
    G = nx.MultiDiGraph()
    G.graph["window_start"] = T0  # declared observation window (data-layer contract)
    for dev in ("DEV-1", "DEV-2", "DEV-H"):
        G.add_node(dev, entity_type="DEVICE")
    G.add_node("CARD-9", entity_type="CARD")
    G.add_node("CARD-H", entity_type="CARD")
    G.add_node("ADDR-H", entity_type="ADDRESS")
    for m in ("MER-1", "MER-2"):
        G.add_node(m, entity_type="MERCHANT")

    plan = {0: ["U1", "U2"], 2: ["U3"], 4: ["U4", "U5"], 6: ["U6", "U7", "U8"]}
    for day, users in plan.items():
        for u in users:
            created = T0 + day * DAY_S
            G.add_node(u, entity_type="USER", created_at=created)
            G.add_edge(u, "DEV-1", rel_type=USER_USED_DEVICE,
                       timestamp=created + 60, weight=1.0)
            G.add_edge(u, "DEV-2", rel_type=USER_USED_DEVICE,
                       timestamp=created + 120, weight=1.0)
            G.add_edge(u, "CARD-9", rel_type=USER_OWNS_CARD,
                       timestamp=created + 180, weight=1.0)
            for k in range(3):  # synchronized burst on the join day
                G.add_edge(u, f"MER-{k % 2 + 1}", rel_type=USER_PAID_MERCHANT,
                           timestamp=created + 300 + 40 * k, weight=1.0)

    # household: old accounts, shared address, family card, calm activity
    for i in (1, 2, 3):
        u = f"HH-{i}"
        G.add_node(u, entity_type="USER", created_at=T0 - 90 * DAY_S)
        G.add_edge(u, "DEV-H", rel_type=USER_USED_DEVICE,
                   timestamp=T0 - 89 * DAY_S, weight=1.0)
        G.add_edge(u, "ADDR-H", rel_type=USER_LIVES_AT_ADDRESS,
                   timestamp=T0 - 89 * DAY_S, weight=1.0)
        G.add_edge(u, "CARD-H", rel_type=USER_OWNS_CARD,
                   timestamp=T0 - 89 * DAY_S + i, weight=1.0)
    for day in range(0, 14):
        u = f"HH-{day % 3 + 1}"
        G.add_edge(u, f"MER-{day % 2 + 1}", rel_type=USER_PAID_MERCHANT,
                   timestamp=T0 + day * DAY_S + 3_600 * (day + 1), weight=1.0)
    return G


CHECKPOINTS = [T0 + d * DAY_S for d in (0.5, 2.5, 4.5, 6.5, 8.0)]

class TestSnapshotCausality:
    def test_future_edges_and_users_excluded(self):
        G = _staged_ring_graph()
        early = snapshot_at(G, T0 + 1 * DAY_S)
        assert "U3" not in early.nodes            # created day 2
        assert "U1" in early.nodes                # created day 0
        early_users = {n for n, d in early.nodes(data=True)
                       if d.get("entity_type") == "USER"}
        assert {u for u in early_users if u.startswith("U")} == {"U1", "U2"}

    def test_future_user_not_resurrected_by_edges(self):
        """A stale edge pointing at a dropped user must not re-add them."""
        G = nx.MultiDiGraph()
        G.add_node("U-old", entity_type="USER", created_at=0)
        G.add_node("U-new", entity_type="USER", created_at=10_000)
        G.add_edge("U-old", "U-new", rel_type=USER_PAID_MERCHANT,
                   timestamp=100, weight=1.0)
        snap = snapshot_at(G, 5_000)
        assert "U-new" not in snap.nodes
        assert snap.number_of_edges() == 0

    def test_truncation_is_idempotent(self):
        G = _staged_ring_graph()
        once = snapshot_at(G, T0 + 3 * DAY_S)
        twice = snapshot_at(once, T0 + 3 * DAY_S)
        assert set(twice.nodes) == set(once.nodes)
        assert twice.number_of_edges() == once.number_of_edges()

    def test_snapshot_preserves_observation_window_metadata(self):
        G = _staged_ring_graph()
        G.graph["window_end"] = T0 + 30 * DAY_S
        snap = snapshot_at(G, T0 + 3 * DAY_S)
        assert snap.graph["window_start"] == T0
        assert snap.graph["window_end"] == T0 + 30 * DAY_S
        assert snap.graph["snapshot_as_of"] == T0 + 3 * DAY_S
        assert graph_t0(snap) == T0

    def test_graph_t0_prefers_declared_window(self):
        """t0 is the declared observation window when the data layer stamps one.

        Household accounts exist long before the window; their pre-window
        ownership edges must not drag the observation window. Graphs
        without a stamp fall back to the earliest *activity* event —
        creation alone never starts the story.
        """
        G = _staged_ring_graph()  # fixture stamps window_start = T0
        assert graph_t0(G) == T0
        bare = nx.MultiDiGraph()
        bare.add_node("U1", entity_type="USER", created_at=0)
        bare.add_edge("U1", "M1", rel_type=USER_PAID_MERCHANT,
                      timestamp=500, weight=1.0)
        bare.add_edge("U1", "M1", rel_type=USER_PAID_MERCHANT,
                      timestamp=100, weight=1.0)
        assert graph_t0(bare) == 100  # earliest activity, not creation


class TestRiskHistory:
    def test_monotone_growth_and_counters(self):
        G = _staged_ring_graph()
        users = ["U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8"]
        hist = risk_history(G, users, CHECKPOINTS)
        risks = [p["risk"] for p in hist]
        known = [p["counters"]["known_users"] for p in hist]
        assert known == sorted(known) and known[-1] == 8
        # THE M8 TRAJECTORY CONTRACT: growth must never be masked. At
        # every checkpoint where the ring gained members, risk must not
        # drop. Over quiet checkpoints the base score may honestly ease
        # (join-day bursts age out), so strict global monotonicity is
        # deliberately not claimed.
        for i in range(1, len(risks)):
            if known[i] > known[i - 1]:
                assert risks[i] >= risks[i - 1], (
                    f"risk dropped {risks[i - 1]} -> {risks[i]} "
                    f"while membership grew {known[i - 1]} -> {known[i]}"
                )
        assert risks[-1] - risks[0] >= 15, "staged growth must move the score"
        devs = [p["counters"]["shared_devices"] for p in hist]
        assert devs[-1] == 2 and devs == sorted(devs)

    def test_what_changed_is_grounded(self):
        G = _staged_ring_graph()
        hist = risk_history(G, ["U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8"],
                            CHECKPOINTS)
        assert hist[0]["what_changed"] == []
        # between cp day-2.5 and cp day-4.5 exactly U4, U5 join (day 4)
        joined = (hist[2]["counters"]["known_users"]
                  - hist[1]["counters"]["known_users"])
        assert joined == 2
        assert any("+2 account(s)" in c for c in hist[2]["what_changed"])
        assert any(c.startswith("risk ") for c in hist[2]["what_changed"])

    def test_day_field_is_relative_to_t0(self):
        G = _staged_ring_graph()
        hist = risk_history(G, ["U1", "U2"], CHECKPOINTS[:2], t0=T0)
        assert hist[0]["day"] == pytest.approx(0.5)
        assert hist[1]["day"] == pytest.approx(2.5)

    def test_deterministic(self):
        G = _staged_ring_graph()
        a = risk_history(G, ["U1", "U2", "U3"], CHECKPOINTS)
        b = risk_history(G, ["U1", "U2", "U3"], CHECKPOINTS)
        assert a == b

class TestEmergingReport:
    def test_staged_ring_detected_with_lead(self):
        G = _staged_ring_graph()
        rep = emerging_report(G, CHECKPOINTS)
        assert rep["n_tracked"] >= 1
        staged = next(r for r in rep["rings"]
                      if {"U1", "U8"} <= set(r["users"]))
        assert staged["escalating"] and staged["crossed"]
        assert staged["ring_id"] in rep["emerging_ring_ids"]
        # THE M8 GATE: detected strictly before the ring fully materialised
        assert staged["detected_day"] is not None
        assert staged["lead_days"] > 0, (
            "sentinel must fire before the final state, not at it"
        )
        # trajectory shows a real rise with grounded deltas
        assert staged["rise"] >= 15
        assert any(c for p in staged["history"] for c in p["what_changed"])

    def test_household_not_flagged(self):
        G = _staged_ring_graph()
        rep = emerging_report(G, CHECKPOINTS)
        hh = next((r for r in rep["rings"]
                   if {"HH-1", "HH-2", "HH-3"} <= set(r["users"])), None)
        if hh is not None:  # household may be too quiet to even track
            assert not hh["escalating"] or not hh["crossed"]
            assert hh["ring_id"] not in rep["emerging_ring_ids"]

    def test_track_discovery_off_still_scores(self):
        G = _staged_ring_graph()
        rep = emerging_report(G, CHECKPOINTS, track_discovery=False)
        staged = next(r for r in rep["rings"] if {"U1", "U8"} <= set(r["users"]))
        assert staged["detected_day"] is None  # no discovery tracking
        assert staged["final_risk"] > staged["first_risk"]


@pytest.fixture(scope="module")
def demo_report():
    eco = build_ecosystem(demo_config(), seed=42)
    G = build_graph(eco)
    t0 = graph_t0(G)
    cps = [t0 + d * DAY_S for d in range(2, 31, 2)]
    return eco, emerging_report(G, cps)


class TestDemoScale:
    """M8 gate at spec §46 demo scale, against the planted emerging ring."""

    def test_planted_emerging_ring_has_quantified_lead(self, demo_report):
        eco, rep = demo_report
        h_plants = [p for p in eco.plants if p.archetype == "H"]
        assert h_plants, "demo config must plant an emerging ring"
        h_users = set(h_plants[0].users)
        hr = next(r for r in rep["rings"] if h_users <= set(r["users"]))
        assert hr["final_risk"] >= rep["escalate_at"], (
            "planted emerging ring must eventually cross the threshold"
        )
        assert hr["detected_day"] is not None
        assert hr["lead_days"] > 0, (
            "the planted emerging ring must be detected before the final checkpoint"
        )
        known = [p["counters"]["known_users"] for p in hr["history"]]
        risks = [p["risk"] for p in hr["history"]]
        for i in range(1, len(risks)):
            if known[i] > known[i - 1]:
                assert risks[i] >= risks[i - 1], (
                    "newly accumulated membership evidence must not present as "
                    "a risk reversal"
                )
        assert hr["ring_id"] in rep["emerging_ring_ids"]

    def test_emerging_ids_are_planted_not_noise(self, demo_report):
        eco, rep = demo_report
        for rid in rep["emerging_ring_ids"]:
            ring = next(r for r in rep["rings"] if r["ring_id"] == rid)
            users = set(ring["users"])
            assert any(set(p.users) <= users for p in eco.plants), (
                f"{rid} escalated without any planted structure"
            )


