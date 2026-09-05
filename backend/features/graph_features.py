"""Graph-native user feature engineering (spec §9).

Every feature has a real semantic meaning, documented in `FEATURE_CATALOG`.
Features are computed on the user-coordination projection `P` (shared
infrastructure + money flow) and on the full heterogeneous graph `G`
(entity-type diversity, concentration, recency, temporal burstiness).

Determinism: pure functions of `(G, as_of)`; no RNG inside (NetworkX's
betweenness sampling uses a fixed seed).
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
import numpy as np
import pandas as pd

from backend.features.projection import project_users
from backend.graph.schema import (
    TRANSACTION_USED_INSTRUMENT,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
    USER_USED_IP,
)

FEATURE_CATALOG = {
    "degree": "distinct users this user is connected to in the coordination projection",
    "weighted_degree": "sum of shared-infrastructure/money-flow edge weights (coordination strength)",
    "unique_neighbors": "distinct coordination neighbors (deduplicated across shared reasons)",
    "component_size": "size of the connected coordination component containing this user",
    "component_density": "edge density of the user's coordination component",
    "clustering": "how tightly this user's coordination neighbors connect to each other",
    "pagerank": "graph centrality of the user in the coordination projection",
    "betweenness": "how often this user sits on shortest coordination paths (hub/mule proxy)",
    "kcore": "deepest k-core shell the user belongs to",
    "neighbor_diversity": "entropy over the entity types this user touches in the full graph",
    "shared_device_count": "distinct devices this user shares with OTHER users",
    "shared_card_count": "distinct cards this user shares with OTHER users",
    "shared_ip_count": "distinct IPs this user shares with OTHER users",
    "merchant_concentration": "HHI over merchants paid (1=one merchant, ~0=diverse)",
    "payment_concentration": "HHI over payment instruments used",
    "coordinated_neighbor_ratio": "fraction of neighbors that are themselves strongly coordinated (structural, label-free)",
    "temporal_burst_score": "max share of this user's transactions in any 1-hour window",
    "edge_recency_s": "seconds since this user's most recent activity at reference time",
    "cross_entity_connectivity": "number of distinct entity types this user touches",
    "money_flow_in": "weighted volume of money this user received (directed)",
    "money_flow_out": "weighted volume of money this user sent (directed)",
}


def _hhi(values: list[float]) -> float:
    """Herfindahl-Hirschman index of concentration over `values`."""
    if not values:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    return float(sum((v / total) ** 2 for v in values))


def _pair_count(n: int) -> int:
    return n * (n - 1) // 2 if n > 1 else 1


def _entropy(values: Counter) -> float:
    total = sum(values.values())
    if total <= 0:
        return 0.0
    return float(-sum((c / total) * np.log2(c / total) for c in values.values()))


def _max_timestamp(G: nx.MultiDiGraph) -> int:
    ts = [d.get("timestamp", 0) for _, _, d in G.edges(data=True)]
    return max(ts) if ts else 0


def _burst_score(times: list[int], window_s: int = 3600) -> float:
    """Maximum fraction of a user's events in any sliding `window_s` window."""
    n = len(times)
    if n < 3:
        return 0.0
    best = 0
    for i in range(n):
        lo = times[i]
        j = i
        while j < n and times[j] - lo <= window_s:
            j += 1
        best = max(best, j - i)
    return best / n


def _shared_entity_count(per_user: dict[str, set], uid: str, user_set: set[str]) -> set[str]:
    """Entities shared with at least one OTHER user."""
    mine = per_user.get(uid, set())
    others: set[str] = set()
    for other, entities in per_user.items():
        if other != uid and other in user_set:
            others |= entities
    return mine & others


def compute_user_features(
    G: nx.MultiDiGraph,
    as_of: int | None = None,
    users: set[str] | None = None,
    fast: bool = False,
) -> pd.DataFrame:
    """Compute the full user-level feature frame.

    `as_of` is the reference time for recency. `fast=True` skips
    betweenness (useful on large graphs).
    """
    now = as_of if as_of is not None else _max_timestamp(G)

    P = project_users(G)
    user_set = users or {n for n, d in G.nodes(data=True) if d["entity_type"] == "USER"}
    Pu = P.to_undirected()
    Ps = nx.Graph(Pu)  # collapsed simple graph for algorithms that reject multigraphs

    # Component / density bookkeeping on the undirected projection.
    comps: dict[str, int] = {}
    comp_sizes: dict[int, int] = {}
    comp_density: dict[int, float] = {}
    for i, comp in enumerate(nx.connected_components(Ps)):
        n = len(comp)
        for u in comp:
            comps[u] = i
        comp_sizes[i] = n
        sub = Pu.subgraph(comp)
        comp_density[i] = sub.number_of_edges() / _pair_count(n) if n > 1 else 0.0

    try:
        pagerank = nx.pagerank(Ps, alpha=0.85, tol=1e-8, max_iter=200)
    except nx.PowerIterationFailedConvergence:
        pagerank = {u: 1.0 / max(1, len(Ps)) for u in user_set}
    kcore = nx.core_number(Ps)
    cluster = nx.clustering(Ps)
    if fast or len(Ps) < 2:
        betweenness = {u: 0.0 for u in user_set}
    else:
        sample = min(25, len(Ps) - 1)
        betweenness = nx.betweenness_centrality(Ps, normalized=True, seed=1, k=sample)

    # ---- full-graph per-user aggregates --------------------------------
    user_merchants: dict[str, Counter] = {}
    user_instruments: dict[str, Counter] = {}
    user_last_seen: dict[str, int] = {}
    user_entity_types: dict[str, set] = {}
    user_devices: dict[str, set] = {}
    user_ips: dict[str, set] = {}
    user_cards: dict[str, set] = {}
    user_sent: Counter = Counter()
    user_received: Counter = Counter()
    user_txn_times: dict[str, list[int]] = {}

    for n, d in G.nodes(data=True):
        if d["entity_type"] == "USER":
            user_last_seen[n] = d.get("created_at", 0)
        elif d["entity_type"] == "TRANSACTION":
            payer = d.get("payer")
            if payer and payer in user_set:
                user_txn_times.setdefault(payer, []).append(d.get("created_at", 0))

    for u, v, data in G.edges(data=True):
        rel = data["rel_type"]
        t = data.get("timestamp", 0)
        if G.nodes[u].get("entity_type") == "USER":
            user_entity_types.setdefault(u, set()).add(G.nodes[v].get("entity_type"))
            user_last_seen[u] = max(user_last_seen.get(u, 0), t)

        if rel == USER_PAID_MERCHANT:
            user_merchants.setdefault(u, Counter())[v] += data.get("weight", 1.0)
        elif rel == USER_SENT_TO_USER:
            user_sent[u] += data.get("weight", 1.0)
            user_received[v] += data.get("weight", 1.0)
        elif rel == TRANSACTION_USED_INSTRUMENT:
            payer = G.nodes[u].get("payer")
            if payer in user_set:
                user_instruments.setdefault(payer, Counter())[v] += 1
        elif rel == "USER_OWNS_CARD":
            user_cards.setdefault(u, set()).add(v)
        elif rel == USER_USED_DEVICE:
            user_devices.setdefault(u, set()).add(v)
        elif rel == USER_USED_IP:
            user_ips.setdefault(u, set()).add(v)

    # ---- assemble rows --------------------------------------------------
    rows: dict[str, dict] = {}
    for uid in sorted(user_set):
        neighbors = set(Pu.neighbors(uid)) if Pu.has_node(uid) else set()
        times = sorted(user_txn_times.get(uid, []))
        rows[uid] = {
            "degree": int(Pu.degree(uid)) if Pu.has_node(uid) else 0,
            "weighted_degree": float(Pu.degree(uid, weight="weight")) if Pu.has_node(uid) else 0.0,
            "unique_neighbors": len(neighbors),
            "component_size": comp_sizes.get(comps.get(uid, -1), 1),
            "component_density": comp_density.get(comps.get(uid, -1), 0.0),
            "clustering": cluster.get(uid, 0.0),
            "pagerank": pagerank.get(uid, 0.0),
            "betweenness": betweenness.get(uid, 0.0),
            "kcore": kcore.get(uid, 0),
            "neighbor_diversity": _entropy(Counter({et: 1 for et in user_entity_types.get(uid, set())})),
            "shared_device_count": len(_shared_entity_count(user_devices, uid, user_set)),
            "shared_card_count": len(_shared_entity_count(user_cards, uid, user_set)),
            "shared_ip_count": len(_shared_entity_count(user_ips, uid, user_set)),
            "merchant_concentration": _hhi(list(user_merchants.get(uid, Counter()).values())),
            "payment_concentration": _hhi(list(user_instruments.get(uid, Counter()).values())),
            "coordinated_neighbor_ratio": (
                len(_coordinated_neighbors(Pu, uid)) / len(neighbors) if neighbors else 0.0
            ),
            "temporal_burst_score": _burst_score(times),
            "edge_recency_s": max(0, now - user_last_seen.get(uid, 0)),
            "cross_entity_connectivity": len(user_entity_types.get(uid, set())),
            "money_flow_in": user_received[uid],
            "money_flow_out": user_sent[uid],
        }

    frame = pd.DataFrame.from_dict(rows, orient="index")
    frame.index.name = "user_id"
    return frame


def _coordinated_neighbors(Pu: nx.Graph, uid: str) -> set:
    """Neighbors that themselves connect to >= 2 coordination users (label-free proxy)."""
    return {nb for nb in Pu.neighbors(uid) if Pu.degree(nb) >= 2}