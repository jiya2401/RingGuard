"""Construct the heterogeneous payment-ecosystem graph from an Ecosystem.

The builder is deliberately NetworkX-implementation-local: the rest of the
backend talks to the graph through `graph.metrics` and the risk engine, so
swapping in a graph database later does not cascade changes.

Time model: every edge carries an integer `timestamp`. Passing `as_of`
returns a *strictly causal snapshot* (no nodes/edges with timestamps after
`as_of`), which is the foundation of leakage-free evaluation (spec §13).

Edges are keyed by their relationship type, so there is at most one edge
per (source, target, rel_type) — the multiplicity of events lives in the
edge `weight` and in temporal features computed in later layers.
"""

from __future__ import annotations

import networkx as nx

from backend.data.model import (
    MANDATE,
    PAYEE_MERCHANT,
    PAYEE_USER,
    SESSION,
    USER,
    Ecosystem,
)
from backend.graph.schema import (
    SESSION_USED_DEVICE,
    SESSION_USED_IP,
    TRANSACTION_AT_MERCHANT,
    TRANSACTION_USED_DEVICE,
    TRANSACTION_USED_INSTRUMENT,
    TRANSACTION_USED_IP,
    USER_CREATED_SESSION,
    USER_HAS_MANDATE,
    USER_HAS_PHONE,
    USER_LIVES_AT_ADDRESS,
    USER_MADE_TRANSACTION,
    USER_OWNS_BANK_ACCOUNT,
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
    USER_USED_IP,
    USER_USED_UPI_ID,
)


def _add(G: nx.MultiDiGraph, u: str, v: str, rel_type: str, timestamp: int, weight: float = 1.0, txn_id=None) -> None:
    """Add (u,v,rel_type) once; keep the earliest timestamp."""
    key = rel_type
    if G.has_edge(u, v, key=key):
        existing = G[u][v][key]
        existing["timestamp"] = min(existing["timestamp"], timestamp)
        existing["weight"] += weight
        if txn_id and not existing.get("transaction_id"):
            existing["transaction_id"] = txn_id
        return
    attrs = {"rel_type": rel_type, "timestamp": timestamp, "weight": weight}
    if txn_id:
        attrs["transaction_id"] = txn_id
    G.add_edge(u, v, key=key, **attrs)


def build_graph(ecosystem: Ecosystem, as_of: int | None = None) -> nx.MultiDiGraph:
    """Build the heterogeneous graph, optionally truncated to `as_of`."""
    G = nx.MultiDiGraph()

    def include(e) -> bool:
        return as_of is None or e.created_at <= as_of

    # --- nodes ----------------------------------------------------
    _RESERVED_NODE_ATTRS = {"entity_type", "created_at", "archetype", "community", "reason"}
    for etype, entities in ecosystem.entities.items():
        for e in entities:
            if not include(e):
                continue
            attrs = {k: v for k, v in e.attributes.items() if k not in _RESERVED_NODE_ATTRS}
            G.add_node(
                e.entity_id,
                entity_type=e.entity_type,
                created_at=e.created_at,
                archetype=e.archetype,
                community=e.community,
                reason=e.reason,
                **attrs,
            )

    # --- user ownership / halo edges (timestamped at creation) ----
    for e in ecosystem.entities.get(USER, []):
        if not include(e):
            continue
        a = e.attributes
        t = e.created_at
        for attr, rel in (
            (a.get("card"), USER_OWNS_CARD),
            (a.get("bank"), USER_OWNS_BANK_ACCOUNT),
            (a.get("upi"), USER_USED_UPI_ID),
            (a.get("phone"), USER_HAS_PHONE),
            (a.get("address"), USER_LIVES_AT_ADDRESS),
        ):
            if attr:
                _add(G, e.entity_id, attr, rel, t)
        for d in a.get("devices", []):
            _add(G, e.entity_id, d, USER_USED_DEVICE, t)

    # --- session links (dynamic device/IP usage) ------------------
    for sess in ecosystem.entities.get(SESSION, []):
        if not include(sess):
            continue
        a = sess.attributes
        t = sess.created_at
        user = a.get("user")
        device = a.get("device")
        ip = a.get("ip")
        if not user:
            continue
        _add(G, user, sess.entity_id, USER_CREATED_SESSION, t)
        if device:
            _add(G, user, device, USER_USED_DEVICE, t)
            _add(G, sess.entity_id, device, SESSION_USED_DEVICE, t)
        if ip:
            _add(G, user, ip, USER_USED_IP, t)
            _add(G, sess.entity_id, ip, SESSION_USED_IP, t)

    # --- mandate links ----------------------------------------------
    for m in ecosystem.entities.get(MANDATE, []):
        if not include(m):
            continue
        a = m.attributes
        if a.get("user"):
            _add(G, a["user"], m.entity_id, USER_HAS_MANDATE, m.created_at)

    # --- payment edges ------------------------------------------------
    for p in ecosystem.payments:
        if as_of is not None and p.timestamp > as_of:
            continue
        t = p.timestamp
        py = p.payer
        _add(G, py, p.transaction_id, USER_MADE_TRANSACTION, t)
        if p.payee_type == PAYEE_MERCHANT:
            _add(G, p.transaction_id, p.payee, TRANSACTION_AT_MERCHANT, t)
            _add(G, py, p.payee, USER_PAID_MERCHANT, t, txn_id=p.transaction_id)
        elif p.payee_type == PAYEE_USER:
            _add(G, py, p.payee, USER_SENT_TO_USER, t, txn_id=p.transaction_id)
        _add(G, p.transaction_id, p.instrument, TRANSACTION_USED_INSTRUMENT, t)
        _add(G, p.transaction_id, p.ip_id, TRANSACTION_USED_IP, t)
        _add(G, p.transaction_id, p.device_id, TRANSACTION_USED_DEVICE, t)

    return G


def graph_stats(G: nx.MultiDiGraph) -> dict:
    """Compact stats about the built graph."""
    from collections import Counter

    node_types = Counter(d.get("entity_type") for _, d in G.nodes(data=True))
    rel_types = Counter(d.get("rel_type") for _, _, d in G.edges(data=True))
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_types": dict(node_types),
        "rel_types": dict(rel_types),
    }


def edges_between(G: nx.MultiDiGraph, u: str, v: str, rel_type: str | None = None) -> list[dict]:
    """All edges between u and v (optionally filtered by relation type)."""
    if G.has_edge(u, v):
        keyed = G[u][v]
        matches = [keyed[k] for k in keyed if rel_type is None or keyed[k]["rel_type"] == rel_type]
        return sorted(matches, key=lambda d: d["timestamp"])
    return []