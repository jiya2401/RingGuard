"""Counterfactual evidence removal with full graph/risk recomputation (M12)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import networkx as nx

from backend.risk.emerging import score_at
from backend.risk.legitimacy import default_ref


def _copy_without(
    graph: nx.MultiDiGraph,
    remove_nodes: Iterable[str],
    remove_relations: Iterable[str],
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    reduced = graph.copy()
    nodes = sorted(set(remove_nodes) & set(reduced.nodes))
    reduced.remove_nodes_from(nodes)
    relation_set = set(remove_relations)
    edges = [
        (u, v, key)
        for u, v, key, data in reduced.edges(keys=True, data=True)
        if data.get("rel_type") in relation_set
    ]
    reduced.remove_edges_from(edges)
    return reduced, {
        "nodes": nodes,
        "relations": sorted(relation_set),
        "edge_count": len(edges),
    }


def recompute_without(
    graph: nx.MultiDiGraph,
    users: list[str],
    *,
    remove_nodes: Iterable[str] = (),
    remove_relations: Iterable[str] = (),
    as_of: int | None = None,
) -> dict[str, Any]:
    """Remove named evidence and recompute both structure and final risk."""
    ref = int(as_of if as_of is not None else default_ref(graph))
    before = score_at(graph, users, ref)
    reduced, removed = _copy_without(graph, remove_nodes, remove_relations)
    after = score_at(reduced, users, ref)

    before_layers = {row["layer"]: row["contribution"] for row in before.drivers}
    after_layers = {row["layer"]: row["contribution"] for row in after.drivers}
    return {
        "as_of": ref,
        "users": sorted(set(users)),
        "removed": removed,
        "before_risk": before.risk_score,
        "after_risk": after.risk_score,
        "risk_delta": after.risk_score - before.risk_score,
        "before_action": before.recommended_action,
        "after_action": after.recommended_action,
        "layer_deltas": {
            name: round(after_layers.get(name, 0.0) - before_layers.get(name, 0.0), 3)
            for name in sorted(set(before_layers) | set(after_layers))
        },
    }


def shared_evidence_counterfactuals(
    graph: nx.MultiDiGraph,
    users: list[str],
    as_of: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Recompute one counterfactual per actually shared non-user entity."""
    member_set = set(users)
    holders: defaultdict[str, set[str]] = defaultdict(set)
    for user in member_set:
        if user not in graph:
            continue
        for _u, target, data in graph.out_edges(user, data=True):
            if data.get("rel_type") in {
                "USER_USED_DEVICE",
                "USER_OWNS_CARD",
                "USER_OWNS_BANK_ACCOUNT",
                "USER_USED_IP",
            }:
                holders[target].add(user)
    candidates = sorted(
        (
            (entity, member_ids)
            for entity, member_ids in holders.items()
            if len(member_ids) >= 2
        ),
        key=lambda item: (-len(item[1]), item[0]),
    )
    if limit is not None:
        candidates = candidates[:limit]
    return [
        {
            "evidence_id": entity,
            "entity_type": graph.nodes[entity].get("entity_type", "UNKNOWN"),
            **recompute_without(
                graph, users, remove_nodes=[entity], as_of=as_of
            ),
        }
        for entity, _member_ids in candidates
    ]
