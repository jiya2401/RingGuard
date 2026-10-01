"""Transparent risk propagation and blast-radius analysis (M11)."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import networkx as nx

from backend.features.projection import project_users
from backend.graph.schema import USER_MADE_TRANSACTION


def propagate_risk(
    graph: nx.MultiDiGraph,
    seed_scores: dict[str, float],
    *,
    max_hops: int = 2,
    decay: float = 0.55,
) -> list[dict[str, Any]]:
    """Propagate the strongest seed score over real user links.

    A user receives at most the maximum decayed contribution of any seed.  This
    deliberately avoids additive feedback loops and keeps the explanation a
    simple shortest path that an investigator can inspect.
    """
    if max_hops < 0:
        raise ValueError("max_hops must be non-negative")
    if not 0.0 <= decay <= 1.0:
        raise ValueError("decay must be in [0, 1]")

    projection = nx.Graph(project_users(graph).to_undirected())
    best: dict[str, dict[str, Any]] = {}
    for seed in sorted(seed_scores):
        if seed not in projection:
            continue
        paths = nx.single_source_shortest_path(projection, seed, cutoff=max_hops)
        for user, path in paths.items():
            hops = len(path) - 1
            propagated = float(seed_scores[seed]) * (decay ** hops)
            candidate = {
                "user_id": user,
                "risk": round(propagated, 2),
                "source": seed,
                "hops": hops,
                "path": path,
            }
            current = best.get(user)
            if current is None or (candidate["risk"], seed) > (
                current["risk"],
                current["source"],
            ):
                best[user] = candidate
    return sorted(best.values(), key=lambda row: (-row["risk"], row["user_id"]))


def _transaction_exposure(graph: nx.MultiDiGraph, users: set[str]) -> float:
    """Sum actual simulated transaction amounts made by affected users."""
    transaction_ids: set[str] = set()
    for user in users:
        if user not in graph:
            continue
        for _u, target, data in graph.out_edges(user, data=True):
            if data.get("rel_type") == USER_MADE_TRANSACTION:
                transaction_ids.add(target)
    return round(
        sum(float(graph.nodes[txn].get("amount", 0.0)) for txn in transaction_ids),
        2,
    )


def calculate_blast_radius(
    graph: nx.MultiDiGraph,
    seed_users: list[str] | set[str],
    *,
    max_hops: int = 2,
) -> dict[str, Any]:
    """Enumerate user and entity impact around a seed cluster.

    User distance is measured on the coordination projection.  Every resource
    directly connected to an affected user is then included by entity type.
    Exposure is explicitly simulated and comes from transaction node amounts.
    """
    seeds = sorted(set(seed_users) & set(graph.nodes))
    projection = nx.Graph(project_users(graph).to_undirected())
    affected_users: set[str] = set(seeds)
    distance: dict[str, int] = {user: 0 for user in seeds}
    for seed in seeds:
        if seed not in projection:
            continue
        lengths = nx.single_source_shortest_path_length(
            projection, seed, cutoff=max_hops
        )
        for user, hops in lengths.items():
            affected_users.add(user)
            distance[user] = min(distance.get(user, hops), hops)

    entities: defaultdict[str, set[str]] = defaultdict(set)
    for user in sorted(affected_users):
        if user not in graph:
            continue
        for _u, target, _data in graph.out_edges(user, data=True):
            entity_type = graph.nodes[target].get("entity_type", "UNKNOWN")
            entities[entity_type].add(target)

    return {
        "seed_users": seeds,
        "max_hops": max_hops,
        "affected_users": sorted(affected_users),
        "user_distances": dict(sorted(distance.items())),
        "affected_entities": {
            entity_type: sorted(ids)
            for entity_type, ids in sorted(entities.items())
        },
        "counts": {
            "users": len(affected_users),
            **{
                entity_type.lower(): len(ids)
                for entity_type, ids in sorted(entities.items())
            },
        },
        "estimated_simulated_exposure": _transaction_exposure(
            graph, affected_users
        ),
        "currency": "INR",
        "data_label": "SIMULATED DATA",
    }
