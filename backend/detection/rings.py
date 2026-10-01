"""Ring discovery (spec §10).

Candidate rings are discovered from the *actual* heterogeneous graph via
structural reasoning, not from planted labels:

1. Project the graph onto the user layer (shared infra + money flow).
2. Partition it with Louvain modularity (deterministic `seed`): dense
   coordination subgraphs separate from sparse background chains, so a
   market-wide pool of lightly-shared devices does not merge every user
   into one meaningless mega-component.
3. Keep communities large enough that genuine coordination survives,
   then assemble explainable structural signals and a transparent
   `structural_score` (the risk engine in M6+ adds temporal, behavioral
   and legitimate-sharing layers).

Detection is *causal*: pass a graph truncated with `as_of` and this module
only sees events up to that time (no future edges leak in).
"""

from __future__ import annotations

import math
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
    # Filled by the M6 risk engine (spec §11, §26).
    drivers: list[dict] = field(default_factory=list)
    recommended_action: str = ""
    # Structured legitimate-sharing evidence (M7; backend/risk/legitimacy.py).
    legitimacy: dict = field(default_factory=dict)

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
            "drivers": self.drivers,
            "recommended_action": self.recommended_action,
            "legitimacy": self.legitimacy,
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


def _primary_pattern(device_coverage: float, card_coverage: float, flow_coverage: float) -> str:
    """Classify a candidate ring by its dominant structural flavour.

    Coverage = fraction of ring users participating in a resource that is
    shared by >=2 members. Coverage — not raw entity counts — decides the
    flavour: a device farm where every member rides the farm device is
    device-driven even if members also keep personal devices, and a farm
    device shared by 8 users is *more* device-biased than a single shared IP.
    """
    if flow_coverage >= 0.5:
        return "money-flow ring (directed transfers)"
    if device_coverage >= 0.5 and card_coverage >= 0.5:
        return "coordinated device + payment-instrument reuse"
    if device_coverage >= 0.5:
        return "device reuse cluster"
    if card_coverage >= 0.5:
        return "payment-instrument sharing cluster"
    return "shared-infrastructure cluster"


# Two-pass discovery bounds (see `discover_rings`): a base community is
# re-partitioned at escalating resolution only when it is larger than
# max(BLOB_SPLIT_MIN, BLOB_POP_FRACTION * graph users). Genuine small
# clusters never reach the splitter; oversized background blobs do.
# 0.10 keeps the M5 gate (no demo community > 20 users) at the demo's
# 188 projection users (120 background + 68 planted members): 0.10*188
# = 19, while 0.15 would let a 27-user blob survive.
BLOB_SPLIT_MIN = 14
BLOB_POP_FRACTION = 0.10
BLOB_RESOLUTIONS = (1.6, 2.6, 4.0)


def _partition_blob(
    S: nx.Graph,
    blob: set[str],
    depth: int,
    max_blob: int,
    seed: int,
    finals: list[set[str]],
) -> None:
    """Recursively split an oversized community at escalating resolution."""
    if len(blob) <= max_blob or depth >= len(BLOB_RESOLUTIONS):
        finals.append(blob)
        return
    sub = S.subgraph(blob)
    parts = nx.community.louvain_communities(
        sub, weight="weight", resolution=BLOB_RESOLUTIONS[depth], seed=seed
    )
    if len(parts) <= 1:
        finals.append(blob)
        return
    for part in sorted(parts, key=min):
        _partition_blob(S, set(part), depth + 1, max_blob, seed, finals)


def _simple_weighted(P: nx.MultiDiGraph) -> nx.Graph:
    """Collapse the (multi-)projection into a simple graph, summing weights.

    Nodes and edges are added in canonical (sorted) order: Louvain's
    exploration follows adjacency insertion order, so without this the
    partition would depend on the process string-hash seed (spec §42
    reproducibility).
    """
    S = nx.Graph()
    S.add_nodes_from(sorted(P.nodes(data=True), key=lambda item: item[0]))
    summed: dict[tuple[str, str], float] = {}
    for u, v, d in P.edges(data=True):
        key = (u, v) if u <= v else (v, u)
        summed[key] = summed.get(key, 0.0) + d.get("weight", 1.0)
    for (u, v), w in sorted(summed.items()):
        S.add_edge(u, v, weight=w)
    return S


def discover_rings(
    G: nx.MultiDiGraph,
    min_users: int = 3,
    min_density: float = 0.15,
    resolution: float = 1.0,
    seed: int = 0,
) -> list[Ring]:
    """Discover candidate rings from the graph snapshot `G`.

    Two-pass Louvain on the weighted user-coordination projection
    (deterministic: canonical edge order + fixed `seed`):

    1. Base pass at standard `resolution` 1.0 — high base resolution
       shatters small genuine clusters (an 8-account ring clique splits
       into singletons at 1.5; the M8 growth replay needs early 2-3 user
       clusters to survive), but at 1.0 background infrastructure can
       merge into one oversized blob.
    2. Only blobs larger than `max_blob` are split recursively at
       escalating resolution (1.6 -> 2.6 -> 4.0). Splitting inside an
       oversized blob is where high resolution helps; genuine small
       clusters are never touched because they are below `max_blob`.
    """
    P = project_users(G)
    S = _simple_weighted(P)
    n_users = S.number_of_nodes()
    max_blob = max(BLOB_SPLIT_MIN, math.ceil(BLOB_POP_FRACTION * n_users))

    finals: list[set[str]] = []
    for comp in sorted(
        nx.community.louvain_communities(S, weight="weight", resolution=resolution, seed=seed),
        key=min,
    ):
        _partition_blob(S, set(comp), 0, max_blob, seed, finals)

    rings: list[Ring] = []
    comp_index = 0
    for comp_set in sorted(finals, key=min):
        comp_set = set(comp_set)
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
        shared_devices = {w for w, holders in device_users.items() if len(holders) >= 2}
        n_shared_devices = len(shared_devices)
        # The set of cards genuinely shared among >=2 users.
        card_users: dict[str, set] = {}
        for u in comp_set:
            for _v, w, d in G.out_edges(u, data=True):
                if d.get("rel_type") == "USER_OWNS_CARD":
                    card_users.setdefault(w, set()).add(u)
        shared_cards = {w for w, holders in card_users.items() if len(holders) >= 2}
        n_shared_cards = len(shared_cards)

        # Coverage: fraction of ring users on resources shared by >=2 members.
        # This (not raw counts) drives pattern classification.
        users_on_shared_dev = set().union(
            *(h for h in device_users.values() if len(h) >= 2)
        )
        users_on_shared_card = set().union(
            *(h for h in card_users.values() if len(h) >= 2)
        )
        dev_cov = len(users_on_shared_dev) / len(comp_set)
        card_cov = len(users_on_shared_card) / len(comp_set)
        flow_cov = min(1.0, flow_edges / len(comp_set))

        score = _structural_score(
            len(comp_set), n_shared_devices, n_shared_cards,
            n_edges, n_pairs, flow_edges, len(merchants),
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
                primary_pattern=_primary_pattern(dev_cov, card_cov, flow_cov),
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