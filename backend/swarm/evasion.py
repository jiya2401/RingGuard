"""Event-level evasions, grounded in the Hugging Face incident (new work).

Unlike a feature-scaling test, these change the *logs* and the whole pipeline
is re-run afterwards. Parameters taken from the incident reports: ~7.9k names
for ~1.2k agents (about 6.6 names per agent) and ~7% transcript tampering.
"""

from __future__ import annotations

import random
from dataclasses import replace

from backend.swarm.schema import MESSAGE, AgentEvent


def drop_events(events: list[AgentEvent], keep_fraction: float, seed: int) -> list[AgentEvent]:
    """Partial observability: the monitor only sees a random fraction of events."""
    r = random.Random(seed)
    return [e for e in events if r.random() < keep_fraction]


def tamper_agents(events: list[AgentEvent], fraction: float, seed: int) -> list[AgentEvent]:
    """Log tampering: all events of a random fraction of agents are deleted."""
    r = random.Random(seed)
    agents = sorted({e.agent for e in events})
    gone = {a for a in agents if r.random() < fraction}
    return [e for e in events if e.agent not in gone]


def rename_agents(
    events: list[AgentEvent], names_per_agent: float, seed: int
) -> tuple[list[AgentEvent], dict[str, str]]:
    """Identity churn: each agent changes name over time.

    Returns (events, alias->true_agent). `names_per_agent` of 1 means no renaming.
    Message recipients are renamed too, using the recipient's name at that time.
    """
    r = random.Random(seed)
    info: dict[str, tuple[int, int, int]] = {}   # agent -> (lo, span, k)
    alias_of: dict[str, str] = {}
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for e in events:
        first[e.agent] = min(first.get(e.agent, e.ts), e.ts)
        last[e.agent] = max(last.get(e.agent, e.ts), e.ts)
    for a in sorted(first):
        k = max(1, round(names_per_agent + r.uniform(-0.5, 0.5)))
        info[a] = (first[a], max(1, last[a] - first[a] + 1), k)
        for i in range(k):
            alias_of[a if i == 0 else f"{a}~{i}"] = a

    def name(a: str, ts: int) -> str:
        if a not in info:
            return a
        lo, span, k = info[a]
        slot = max(0, min(k - 1, int((ts - lo) * k / span)))
        return a if slot == 0 else f"{a}~{slot}"

    out = [
        replace(e, agent=name(e.agent, e.ts),
                target=name(e.target, e.ts) if e.kind == MESSAGE else e.target)
        for e in events
    ]
    return out, alias_of 