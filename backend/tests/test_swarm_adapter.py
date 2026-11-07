"""Toy test: 3 colluding agents sharing a hidden board are found as one ring."""

from __future__ import annotations

from backend.detection.rings import discover_rings
from backend.graph.builder import build_graph
from backend.swarm.adapter import events_to_ecosystem
from backend.swarm.schema import MESSAGE, USE_RESOURCE, AgentEvent


def _toy_events():
    ev, n = [], 0

    def add(ts, agent, kind, target):
        nonlocal n
        n += 1
        ev.append(AgentEvent(f"e{n}", ts, agent, kind, target))

    # Three agents secretly share a hidden board and message each other.
    for i, a in enumerate(["c1", "c2", "c3"]):
        for k in range(4):
            add(1000 + i * 10 + k, a, USE_RESOURCE, "hidden_board")
    for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "c1")]:
        add(1100, a, MESSAGE, b)
    # Two independent agents each use their own private resource.
    for k in range(4):
        add(1000 + k, "i1", USE_RESOURCE, "scratch_i1")
        add(1000 + k, "i2", USE_RESOURCE, "scratch_i2")
    return ev


def test_colluding_trio_is_one_ring_and_independents_are_not():
    eco = events_to_ecosystem(_toy_events(), seed=0)
    G = build_graph(eco)
    rings = discover_rings(G, min_users=3)
    flagged = [set(r.users) for r in rings]
    assert {"c1", "c2", "c3"} in flagged
    assert not any({"i1", "i2"} & s for s in flagged) 