"""Swarm-specific ring features computed from agent events (new work).

Replaces the payment-specific signals (merchant concentration, account youth)
that carry no meaning for agents.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from backend.swarm.schema import MESSAGE, USE_RESOURCE, AgentEvent

FEATURES = ("unsanc_share", "sanc_share", "sync", "reciprocity", "hub_share", "density", "events_per_agent")


def ring_features(
    events: list[AgentEvent], members: set[str], sanctioned: set[str], window_s: int = 3600
) -> dict[str, float]:
    n = max(1, len(members))
    mine = [e for e in events if e.agent in members]
    holders: dict[str, set[str]] = defaultdict(set)
    for e in mine:
        if e.kind == USE_RESOURCE:
            holders[e.target].add(e.agent)
    shared = {r: h for r, h in holders.items() if len(h) >= 2}
    unsanc = set().union(*[h for r, h in shared.items() if r not in sanctioned]) if shared else set()
    sanc = set().union(*[h for r, h in shared.items() if r in sanctioned]) if shared else set()

    # sync: largest fraction of members active inside one window
    best = 0
    times = sorted((e.ts, e.agent) for e in mine)
    j = 0
    for i in range(len(times)):
        while times[i][0] - times[j][0] > window_s:
            j += 1
        best = max(best, len({a for _, a in times[j:i + 1]}))

    msgs = [(e.agent, e.target) for e in mine if e.kind == MESSAGE and e.target in members]
    pairs = set(msgs)
    recip = sum(1 for a, b in pairs if (b, a) in pairs) / len(pairs) if pairs else 0.0
    out_deg = Counter(a for a, _ in pairs)
    hub = max(out_deg.values()) / max(1, len(members) - 1) if out_deg else 0.0
    possible = n * (n - 1)
    return {
        "unsanc_share": len(unsanc & members) / n,
        "sanc_share": len(sanc & members) / n,
        "sync": best / n,
        "reciprocity": recip,
        "hub_share": min(1.0, hub),
        "density": len(pairs) / possible if possible else 0.0,
        "events_per_agent": min(1.0, len(mine) / n / 20),
    } 