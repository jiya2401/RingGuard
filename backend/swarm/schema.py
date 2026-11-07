"""Event schema for multi-agent logs (new work, Swarm Alignment Hackathon)."""

from __future__ import annotations

from dataclasses import dataclass

# What an event can be.
MESSAGE = "message"      # agent -> agent
USE_RESOURCE = "use"     # agent touches a shared resource (file, tool, board, host)

# Ground-truth labels for a scenario (known because we generate the data).
INDEPENDENT = "independent"
SANCTIONED = "sanctioned"   # legitimate team sharing a resource on purpose
COVERT = "covert"           # unapproved shared channel / collusion


@dataclass
class AgentEvent:
    event_id: str 
    ts: int                 # seconds
    agent: str              # raw agent name
    kind: str               # MESSAGE or USE_RESOURCE
    target: str             # recipient agent (MESSAGE) or resource id (USE_RESOURCE)
    label: str | None = None  # ground-truth group label, for evaluation only
    fp: str | None = None     # persistent fingerprint (e.g. gateway key / host); survives renaming