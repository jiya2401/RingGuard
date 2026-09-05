"""Ring discovery (spec §10).

Candidate rings are discovered from the *actual* heterogeneous graph via
structural reasoning, not from planted labels:

1. Project the graph onto the user layer (shared infra + money flow).
2. Take connected components, then keep clusters large/dense enough that
   genuine coordination survives while trivial ties do not.
3. For each candidate, assemble explainable structural signals and a
   transparent `structural_score` (the risk engine in M6+ adds temporal,
   behavioral and legitimate-sharing layers).

Detection is *causal*: pass a graph truncated with `as_of` and this module
only sees events up to that time (no future edges leak in).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from backend.data.model import USER
from backend.features.projection import project_users
from backend.graph.schema import (
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
    USER_USED_IP,
)


@dataclass
class Ring:
    """A discovered coordination candidate (mirrors spec §10 fields)."""

    ring_id: str
    users: list[str]
    structural_score: float
    risk_score: float | None = field(default=None)  # filled by the risk engine (M6)
    confidence: float | None = field(default=None)
    size: int = 0
    entity_types: list[str] = field(default_factory=list)
    primary_pattern: str = ""
    risk_signals: list[dict] = field(default_factory=list)
    legitimate_signals: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    estimated_simulated_exposure: float = 0.0
    affected_entities: dict[str, list[str]] = field(default_factory=dict)
    status: str = "NEW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ring_id": self.ring_id,
            "users": self.users,
            "structural_score": round(self.structural_score, 3),
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "size": self.size,
            "entity_types": self.entity_types,
            "primary_pattern": self.primary_pattern,
            "risk_signals": self.risk_signals,
            "legitimate_signals": self.legitimate_signals,
            "timeline": self.timeline,
            "estimated_simulated_exposure": self.estimated_simulated_exposure,
            "affected_entities": self.affected_entities,
            "status": self.status,
        }


def _component_entities(G: nx.MultiDiGraph, users: set[str]) -> dict[str, set[str]]:
    """All devices/cards/ips/merchants reachable from these users."""
    out = {"devices": set(), "cards": set(), "ips": set(), "merchants": set()}
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            rel = d.get("rel_type")
            if rel == USER_USED_DEVICE:
                out["devices"].add(w)
            elif rel == "USER_OWNS_CARD":
                out["cards"].add(w)
            elif rel == USER_USED_IP:
                out["ips"].add(w)
            elif rel == USER_PAID_MERCHANT:
                out["merchants"].add(w)
    return out


def _component_timeline(G: nx.MultiDiGraph, users: set[str]) -> list[dict]:
    """Chronological account-creation + activity events for the component."""
    events: list[dict] = []
    for u in users:
        if u not in G:
            continue
        events.append({"type": "account", "entity": u, "timestamp": G.nodes[u].get("created_at", 0)})
        for _v, w, d in G.out_edges(u, data=True):
            t = d.get("timestamp", 0)
            rel = d.get("rel_type")
            if rel == USER_PAID_MERCHANT:
                events.append({"type": "txn", "entity": u, "target": w, "timestamp": t})
            elif rel == USER_SENT_TO_USER:
                events.append({"type": "p2p", "entity": u, "target": w, "timestamp": t})
    events.sort(key=lambda e: e["timestamp"])
    return events


def _users_per_entity(count_users: int, entity_count: int) -> float:
    return round(count_users / entity_count, 2) if entity_count else 0.0


def _structural_score(
    n_users: int,
    n_devices: int,
    n_cards: int,
    n_edges: int,
    n_pairs: int,
    flow_edges: int,
    n_merchants: int,
) -> float:
    """Explainable structural risk proxy (0..1).

    Components: density (0.35), users-per-device (0.25), users-per-card (0.20),
    directed p2p flow presence (0.12), merchant narrowness (0.08).
    Not the final risk — the M6 risk engine adds temporal, behavioral, and
    legitimate-sharing layers.
    """
    density = n_edges / n_pairs if n_pairs else 0.0
    device_conc = min(1.0, _users_per_entity(n_users, n_devices) / 3.0) if n_devices else 0.0
    card_conc = min(1.0, _users_per_entity(n_users, n_cards) / 3.0) if n_cards else 0.0
    flow_sig = min(1.0, flow_edges / max(1, n_users)) if flow_edges else 0.0
    merchant_narrow = min(1.0, 1.0 - n_merchants / max(1, n_users * 2)) if n_merchants else 0.0
    score = (
        0.35 * density
        + 0.25 * device_conc
        + 0.20 * card_conc
        + 0.12 * flow_sig
        + 0.08 * merchant_narrow
    )
    return round(min(1.0, score), 3)


def _primary_pattern(devices: set, cards: set, flow_edges: int, ips: set) -> str:
    """Classify a candidate ring by its dominant structural flavour."""
    if flow_edges:
        return "money-flow ring (directed transfers)"
    device_bias = bool(devices) and len(devices) <= max(1, len(ips))
    card_bias = bool(cards) and len(cards) <= max(1, len(devices))
    if device_bias and card_bias:
        return "coordinated device + payment-instrument reuse"
    if device_bias:
        return "device reuse cluster"
    if card_bias:
        return "payment-instrument sharing cluster"
    return "shared-infrastructure cluster"


def discover_rings(
    G: nx.MultiDiGraph,
    min_users: int = 3,
    min_density: float = 0.15,
) -> list[Ring]:
    """Discover candidate rings from the graph snapshot `G`.

    Candidates are connected components of the user-coordination projection
    that are large enough and structurally significant.
    """
    P = project_users(G)
    S = nx.Graph(P.to_undirected())  # collapsed simple graph (component logic)

    rings: list[Ring] = []
    comp_index = 0
    for comp in nx.connected_components(S):
        comp_set = set(comp)
        if len(comp_set) < min_users:
            continue
        sub = S.subgraph(comp_set)
        n_edges = sub.number_of_edges()
        n_pairs = len(comp_set) * (len(comp_set) - 1) // 2
        density = n_edges / n_pairs if n_pairs else 0.0
        if density < min_density and n_edges == 0:
            continue

        entities = _component_entities(G, comp_set)
        devices, cards, ips, merchants = (
            entities["devices"], entities["cards"], entities["ips"], entities["merchants"],
        )
        flow_edges = sum(
            1
            for _u, _v, d in G.edges(data=True)
            if d.get("rel_type") == USER_SENT_TO_USER and _u in comp_set and _v in comp_set
        )
        # The set of devices genuinely shared among >=2 users of this component.
        device_users: dict[str, set] = {}
        for u in comp_set:
            for _v, w, d in G.out_edges(u, data=True):
                if d.get("rel_type") == USER_USED_DEVICE:
                    device_users.setdefault(w, set()).add(u)
        n_shared_devices = sum(1 for holders in device_users.values() if len(holders) >= 2)
        # The set of cards genuinely shared among >=2 users.
        card_users: dict[str, set] = {}
        for u in comp_set:
            for _v, w, d in G.out_edges(u, data=True):
                if d.get("rel_type") == "USER_OWNS_CARD":
                    card_users.setdefault(w, set()).add(u)
        n_shared_cards = sum(1 for holders in card_users.values() if len(holders) >= 2)

        score = _structural_score(
            len(comp_set), max(1, n_shared_devices) if devices else 0,
            max(1, n_shared_cards) if cards else 0, n_edges, n_pairs, flow_edges,
            len(merchants),
        )

        signals = [
            {"signal": "component_density", "value": round(density, 3),
             "interpretation": "how inter-connected this cluster is"},
            {"signal": "users_per_shared_device", "value": _users_per_entity(len(comp_set), n_shared_devices),
             "interpretation": "\"how unusually concentrated is activity across devices?\""},
            {"signal": "users_per_shared_card", "value": _users_per_entity(len(comp_set), n_shared_cards),
             "interpretation": "how concentrated is the cluster on shared payment instruments"},
            {"signal": "directed_money_flow_edges", "value": flow_edges,
             "interpretation": "user-to-user transfer count (mule signal)"},
        ]

        rings.append(
            Ring(
                ring_id=f"R-{comp_index + 1:03d}",
                users=sorted(comp_set),
                structural_score=score,
                size=len(comp_set),
                entity_types=["USER"],
                primary_pattern=_primary_pattern(devices, cards, flow_edges, ips),
                risk_signals=signals,
                estimated_simulated_exposure=0.0,
                affected_entities={k: sorted(v) for k, v in entities.items()},
                timeline=_component_timeline(G, comp_set),
                status="NEW",
            )
        )
        comp_index += 1

    rings.sort(key=lambda r: r.structural_score, reverse=True)
    return rings 