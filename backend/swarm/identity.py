"""Alias resolution from a persistent fingerprint (new work).

Agents can rename themselves, but a gateway can often still see something that
does not change with the name (API key, host, process id). `coverage` is the
share of events for which that fingerprint is actually observed. Names that
share an observed fingerprint are merged; names never seen with one stay apart.
"""

from __future__ import annotations

import random
from dataclasses import replace

from backend.swarm.schema import AgentEvent


def resolve_by_fingerprint(events: list[AgentEvent], coverage: float, seed: int) -> dict[str, str]:
    r = random.Random(seed)
    names = sorted({e.agent for e in events} | {e.target for e in events})
    parent = {n: n for n in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first_name_for_fp: dict[str, str] = {}
    for e in events:
        if e.fp is None or r.random() >= coverage:
            continue
        if e.fp in first_name_for_fp:
            parent[find(e.agent)] = find(first_name_for_fp[e.fp])
        else:
            first_name_for_fp[e.fp] = e.agent
    return {n: find(n) for n in names}


def apply_aliases(events: list[AgentEvent], mapping: dict[str, str]) -> list[AgentEvent]:
    return [replace(e, agent=mapping.get(e.agent, e.agent), target=mapping.get(e.target, e.target)) for e in events] 