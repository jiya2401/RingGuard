"""Project a heterogeneous graph onto the USER layer via shared infrastructure.

Two users are linked in the projection when they share a device, card,
UPI, bank account, address, or IP; plus a *directed* edge when one paid the
other. This coordination projection is the backbone of ring discovery:
the features in `graph_features.py` are mostly defined on this layer
because coordinated abuse is about *who is indirectly connected through
what* (spec §2, §9).

Shared-infrastructure edges are bidirectional (undirected coordination);
money-flow edges preserve direction (mule rings need direction).
"""

from __future__ import annotations

import networkx as nx

from backend.data.model import USER
from backend.graph.schema import USER_SENT_TO_USER, USER_USED_DEVICE, USER_USED_IP

# Relation types that, when shared, mean the two users share infrastructure.
# IP is deliberately weak (shared IP alone must NOT equal fraud, spec §6) and
# only *reinforces* stronger ties (handled below). UPI/address co-usage stays
# as a *feature* but does not create projection edges (it over-links via small pools).
SHARED_REL_TYPES = (
    USER_USED_DEVICE,            # strong: device reuse
    "USER_OWNS_CARD",            # strong: payment-instrument reuse
    "USER_OWNS_BANK_ACCOUNT",    # strong: shared account
)

SHARE_WEIGHTS = {
    USER_USED_DEVICE: 2.0,
    "USER_OWNS_CARD": 2.0,
    USER_USED_IP: 1.0,
    "USER_OWNS_BANK_ACCOUNT": 2.0,
    "USER_USED_UPI_ID": 1.5,
    "USER_LIVES_AT_ADDRESS": 1.0,
}


def user_devices(G: nx.MultiDiGraph) -> dict[str, set[str]]:
    """user -> set of devices used (static halo edges)."""
    out: dict[str, set[str]] = {}
    for u, d, data in G.edges(data=True):
        if data["rel_type"] == USER_USED_DEVICE:
            out.setdefault(u, set()).add(d)
    return out


def user_ips(G: nx.MultiDiGraph) -> dict[str, set[str]]:
    """user -> set of IPs used."""
    out: dict[str, set[str]] = {}
    for u, ip, data in G.edges(data=True):
        if data["rel_type"] == USER_USED_IP:
            out.setdefault(u, set()).add(ip)
    return out


def user_cards(G: nx.MultiDiGraph) -> dict[str, set[str]]:
    """user -> set of owned cards."""
    out: dict[str, set[str]] = {}
    for u, c, data in G.edges(data=True):
        if data["rel_type"] == "USER_OWNS_CARD":
            out.setdefault(u, set()).add(c)
    return out


def project_users(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """USER-only graph with shared-infrastructure (bi) and money-flow (directed) edges."""
    P = nx.MultiDiGraph()
    users = {n for n, d in G.nodes(data=True) if d["entity_type"] == USER}
    for u in users:
        P.add_node(u, entity_type=USER)

    def link(u: str, v: str, reason: str, weight: float, directed: bool = False) -> None:
        if u == v or u not in users or v not in users:
            return
        key = reason
        if P.has_edge(u, v, key=key):
            P[u][v][key]["weight"] += weight
        else:
            P.add_edge(u, v, key=key, weight=weight, reason=reason)
        if not directed:
            if P.has_edge(v, u, key=key):
                P[v][u][key]["weight"] += weight
            else:
                P.add_edge(v, u, key=key, weight=weight, reason=reason)

    # --- Shared infrastructure (strong relations) ---
    for rel_type in SHARED_REL_TYPES:
        value_to_users: dict[str, set[str]] = {}
        for u, w, d in G.edges(data=True):
            if d["rel_type"] == rel_type:
                value_to_users.setdefault(w, set()).add(u)
        for holders in value_to_users.values():
            if len(holders) < 2:
                continue
            for u in holders:
                for v in holders:
                    link(u, v, "shared", SHARE_WEIGHTS[rel_type])

    # --- Weak relation: shared IP only reinforces an existing strong/medium tie.
    # This keeps "shared IP alone" from creating false coordination (spec §6).
    ip_holders: dict[str, set[str]] = {}
    for u, w, d in G.edges(data=True):
        if d["rel_type"] == USER_USED_IP:
            ip_holders.setdefault(w, set()).add(u)
    for holders in ip_holders.values():
        if len(holders) < 2:
            continue
        for u in holders:
            for v in holders:
                if u == v or not P.has_edge(u, v, key="shared"):
                    continue
                link(u, v, "shared", SHARE_WEIGHTS[USER_USED_IP])

    # Directed money flow.
    for u, v, d in G.edges(data=True):
        if d["rel_type"] == USER_SENT_TO_USER:
            link(u, v, "flow", d.get("weight", 1.0), directed=True)

    return P