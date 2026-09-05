"""Emerging-risk engine (spec §8, §16).

Risk is not a state, it is a trajectory. This module replays the graph
causally: for each checkpoint it truncates every edge and user creation
to `as_of`, scores the tracked accounts with the same M6 risk engine,
and diffs consecutive checkpoints to say exactly WHAT CHANGED
("+2 accounts", "+1 shared device", "synchronization 0.25 -> 0.75").
Nothing is invented — every delta is recomputed from the snapshots.

The dedicated emerging-risk layer (spec §16) then adjusts trajectory
risk by growth momentum: base risk x (1 + capped momentum), where
momentum is cumulative structural growth while watched (new accounts,
new shared instruments, new internal transfers). Recruiting rings climb
even when share-based signals dilute; static communities gain nothing.
The adjustment is auditable — every point keeps `base_risk` and
`momentum` alongside the adjusted `risk`.

Two entry points:

- `risk_history(G, users, checkpoints)` — trajectory of one tracked
  user set (investigation page, risk-history endpoint).
- `emerging_report(G, checkpoints)` — scans all finally-discovered
  rings across the checkpoint grid, reports escalating clusters and
  quantifies detection lead time: the first checkpoint where the
  sentinel's own discovery surfaced the cluster AND its risk crossed
  the escalation threshold, compared with the final state.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from backend.detection.rings import Ring, discover_rings
from backend.graph.schema import (
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
)
from backend.features.graph_features import compute_user_features
from backend.risk.engine import (
    WEIGHTS,
    score_ring,
)
from backend.risk.legitimacy import DAY_S, default_ref


def graph_t0(G: nx.MultiDiGraph) -> int:
    """Start of the observation window: the earliest *event* timestamp.

    Accounts created before any activity are pre-existing population
    (households, established customers) — the emerging-risk story starts
    when events start flowing. Pass `t0` explicitly to `risk_history` /
    `emerging_report` to analyse a specific window instead.
    """
    stamped = [d.get("timestamp", 0) for _, _, d in G.edges(data=True)]
    return min([t for t in stamped if t] or [0])


def snapshot_at(G: nx.MultiDiGraph, as_of: int) -> nx.MultiDiGraph:
    """Causal view of `G` at `as_of`.

    Drops payment/relationship edges stamped after `as_of` and USER
    nodes created after `as_of`. Non-user entities stay (an entity
    itself has no creation story; only its edges do).
    """
    H = nx.MultiDiGraph()
    for n, d in G.nodes(data=True):
        if d.get("entity_type") == "USER" and d.get("created_at", 0) > as_of:
            continue
        H.add_node(n, **d)
    for u, v, d in G.edges(data=True):
        # Endpoints dropped above (future users) must not be resurrected:
        # NetworkX would re-add them implicitly on add_edge.
        if u not in H or v not in H:
            continue
        if d.get("timestamp", 0) <= as_of:
            H.add_edge(u, v, **d)
    return H


def _coordination_counters(
    G: nx.MultiDiGraph, users: set[str], as_of: int, window_s: int = 7 * DAY_S
) -> dict[str, float]:
    """Raw coordination counters for the what-changed diff (spec §16).

    Absolute trailing-window counters (`recent_users`, `recent_events`)
    drive the momentum layer: unlike share metrics they cannot be
    diluted when quiet members join, and they only grow while the ring
    is actively recruiting/transacting.
    """
    known = users & set(G.nodes)
    dev_users: dict[str, set[str]] = {}
    card_users: dict[str, set[str]] = {}
    flow_edges = 0
    recent_users = 0
    recent_events = 0
    for u in known:
        if as_of - G.nodes[u].get("created_at", 0) <= window_s:
            recent_users += 1
        for _v, w, d in G.out_edges(u, data=True):
            rel = d.get("rel_type")
            if rel == USER_USED_DEVICE:
                dev_users.setdefault(w, set()).add(u)
            elif rel == USER_OWNS_CARD:
                card_users.setdefault(w, set()).add(u)
            elif rel == USER_SENT_TO_USER and w in users:
                flow_edges += 1
                if as_of - d.get("timestamp", 0) <= window_s:
                    recent_events += 1
            elif rel == USER_PAID_MERCHANT:
                if as_of - d.get("timestamp", 0) <= window_s:
                    recent_events += 1
    return {
        "known_users": len(known),
        "shared_devices": sum(1 for s in dev_users.values() if len(s) >= 2),
        "shared_cards": sum(1 for s in card_users.values() if len(s) >= 2),
        "internal_transfers": flow_edges,
        "recent_users": recent_users,
        "recent_events": recent_events,
    }


def _signal_map(ring: Ring) -> dict[str, float]:
    return {s["signal"]: s["value"] for s in ring.risk_signals}


def _structural_snapshot(H: nx.MultiDiGraph, known: list[str]) -> float:
    """M5's structural score, recomputed on a truncated graph.

    Uses the same `_structural_score` as discovery so trajectory points
    and final scores share one formula; the projection pairs are
    re-derived from the entities the known users actually share at the
    checkpoint.
    """
    from itertools import combinations

    from backend.detection.rings import _structural_score

    dev_users: dict[str, set[str]] = {}
    card_users: dict[str, set[str]] = {}
    merchants: set[str] = set()
    flow_edges = 0
    for u in known:
        for _v, w, d in H.out_edges(u, data=True):
            rel = d.get("rel_type")
            if rel == USER_USED_DEVICE:
                dev_users.setdefault(w, set()).add(u)
            elif rel == USER_OWNS_CARD:
                card_users.setdefault(w, set()).add(u)
            elif rel == USER_PAID_MERCHANT:
                merchants.add(w)
            elif rel == USER_SENT_TO_USER and w in known:
                flow_edges += 1
    pairs: set[tuple[str, str]] = set()
    for holders in list(dev_users.values()) + list(card_users.values()):
        ks = sorted(holders)
        pairs.update(combinations(ks, 2))
    n = len(known)
    return _structural_score(
        n,
        sum(1 for s in dev_users.values() if len(s) >= 2),
        sum(1 for s in card_users.values() if len(s) >= 2),
        len(pairs),
        n * (n - 1) // 2,
        flow_edges,
        len(merchants),
    )


def score_at(
    G: nx.MultiDiGraph,
    users: list[str],
    as_of: int,
    feats: pd.DataFrame | None = None,
) -> Ring:
    """Score the accounts of `users` that already exist at `as_of`.

    The candidate covers only accounts created by the checkpoint — an
    account cannot contribute risk before it exists. `G` may be the full
    graph or an already-truncated snapshot (truncation is idempotent).
    """
    H = snapshot_at(G, as_of)
    known = [u for u in users if u in H]
    candidate = Ring(
        ring_id="TRAJECTORY",
        users=known,
        structural_score=_structural_snapshot(H, known),
    )
    if feats is None:
        feats = compute_user_features(H, as_of=as_of, users=set(known), fast=True)
    return score_ring(candidate, H, as_of=as_of, feats=feats)


def _flatten(point_ring: Ring, as_of: int, t0: int) -> dict[str, Any]:
    by_layer = {d["layer"]: d["contribution"] for d in point_ring.drivers}
    return {
        "as_of": as_of,
        "day": round((as_of - t0) / DAY_S, 2),
        "risk": point_ring.risk_score,
        "confidence": point_ring.confidence,
        "layer_scores": {k: round(by_layer.get(k, 0.0) / WEIGHTS[k], 3) for k in WEIGHTS},
        "signals": _signal_map(point_ring),
        "drivers": point_ring.drivers,
        "recommended_action": point_ring.recommended_action,
    }


def risk_history(
    G: nx.MultiDiGraph,
    users: list[str],
    checkpoints: list[int],
    t0: int | None = None,
) -> list[dict[str, Any]]:
    """Causal risk trajectory of a fixed user set across `checkpoints`.

    Each point scores only what existed at that moment; `what_changed`
    diffs the raw counters and signals against the previous checkpoint
    (spec §16: "explain exactly what changed"). `t0` anchors the day
    axis; by default it is the tracked cluster's own story origin — the
    earliest activity among `users` — so pre-existing population does
    not stretch the axis.
    """
    if t0 is None:
        stamped = [
            d.get("timestamp", 0)
            for u in set(users) & set(G.nodes)
            for _v, _w, d in G.out_edges(u, data=True)
        ]
        t0 = min([s for s in stamped if s] or [graph_t0(G)])
    users = sorted(set(users))
    history: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    origin: dict[str, Any] | None = None
    for as_of in sorted(checkpoints):
        snap = snapshot_at(G, as_of)
        point = _flatten(score_at(snap, users, as_of), as_of, t0)
        point["counters"] = _coordination_counters(snap, set(users), as_of)
        _apply_momentum(point, origin)
        point["what_changed"] = _what_changed(prev, point) if prev else []
        history.append(point)
        prev = point
        origin = origin or point
    return history


# Emerging-risk layer (spec §16): trajectory risk = base risk x
# (1 + MOMENTUM_CAP * growth). Growth evidence is CUMULATIVE STRUCTURAL
# change while watched — new accounts, new shared instruments, new
# internal transfers. These counters are monotone by construction: they
# rise only while the ring is actively recruiting, cannot be diluted by
# quiet members, and cannot fluctuate with background activity noise —
# so an old quiet household gains nothing and a busy-but-static
# community gains nothing either. The base score still tracks current
# evidence; momentum only rewards demonstrated structural growth.
MOMENTUM_CAP = 0.6


def _momentum_growth(origin: dict[str, Any] | None, curr: dict[str, Any]) -> float:
    """Cumulative structural growth 0..1 since the trajectory origin."""
    if origin is None:
        return 0.0
    o, c = origin["counters"], curr["counters"]
    g_users = max(0, c["known_users"] - o["known_users"]) / 3
    g_instruments = max(
        0,
        (c["shared_devices"] + c["shared_cards"])
        - (o["shared_devices"] + o["shared_cards"]),
    ) / 2
    g_flow = max(0, c["internal_transfers"] - o["internal_transfers"]) / 3
    return max(min(1.0, g_users), min(1.0, g_instruments), min(1.0, g_flow))


def _apply_momentum(point: dict[str, Any], origin: dict[str, Any] | None) -> None:
    """Attach the growth-aware emerging risk to a trajectory point.

    Keeps `base_risk` (the M6 engine's score) and `momentum` on the
    point so the adjustment is always auditable, never hidden.
    """
    growth = _momentum_growth(origin, point)
    point["base_risk"] = point["risk"]
    point["momentum"] = round(growth, 3)
    point["risk"] = min(100, round(point["risk"] * (1 + MOMENTUM_CAP * growth)))


def _what_changed(prev: dict[str, Any], curr: dict[str, Any]) -> list[str]:
    """Human-readable delta between consecutive checkpoints, from counters."""
    changes: list[str] = []
    p, c = prev["counters"], curr["counters"]
    d_users = c["known_users"] - p["known_users"]
    if d_users:
        changes.append(f"+{d_users} account(s) ({c['known_users']} total)")
    d_dev = c["shared_devices"] - p["shared_devices"]
    if d_dev:
        changes.append(f"+{d_dev} shared device(s) ({c['shared_devices']} total)")
    d_card = c["shared_cards"] - p["shared_cards"]
    if d_card:
        changes.append(f"+{d_card} shared payment instrument(s) ({c['shared_cards']} total)")
    d_flow = c["internal_transfers"] - p["internal_transfers"]
    if d_flow:
        changes.append(f"+{d_flow} internal transfer(s) ({c['internal_transfers']} total)")
    for name, label in (
        ("user_synchronization", "user synchronization"),
        ("account_creation_velocity", "account-creation velocity"),
    ):
        a, b = prev["signals"].get(name, 0.0), curr["signals"].get(name, 0.0)
        if b > a:
            changes.append(f"{label} {a:.2f} -> {b:.2f}")
    if curr["risk"] != prev["risk"]:
        changes.append(f"risk {prev['risk']} -> {curr['risk']}")
    return changes


def emerging_report(
    G: nx.MultiDiGraph,
    checkpoints: list[int],
    escalate_at: int = 45,
    min_rise: int = 8,
    track_discovery: bool = True,
) -> dict[str, Any]:
    """Scan all finally-discovered rings across a causal checkpoint grid.

    For every ring: per-checkpoint risk (accounts scored only after they
    exist), what-changed deltas, whether the sentinel's own discovery
    contained the cluster at that point, and — for rings that crossed
    `escalate_at` — the detection lead: how many days before the final
    state the cluster was both discovered and above the threshold
    (spec §52/M8 gate: detection *before* the ring fully materialises).
    """
    checkpoints = sorted(checkpoints)
    final_rings = discover_rings(G)
    tracked = [(ring, sorted(ring.users)) for ring in final_rings]
    union = {u for _, users in tracked for u in users}
    t0 = graph_t0(G)

    histories: dict[int, list[dict[str, Any]]] = {id(r): [] for r, _ in tracked}

    for as_of in checkpoints:
        snap = snapshot_at(G, as_of)
        feats = compute_user_features(
            snap, as_of=as_of, users=union & set(snap.nodes), fast=True
        )
        communities = (
            [frozenset(r.users) for r in discover_rings(snap)]
            if track_discovery
            else []
        )
        for ring, users in tracked:
            known = set(users) & set(snap.nodes)
            if not known:
                histories[id(ring)].append(None)
                continue
            pt = _flatten(score_at(snap, users, as_of, feats=feats), as_of, t0)
            pt["counters"] = _coordination_counters(snap, set(users), as_of)
            pt["discovered"] = bool(known) and len(known) >= 3 and any(
                known <= comm for comm in communities
            )
            histories[id(ring)].append(pt)

    rings_out: list[dict[str, Any]] = []
    for ring, users in tracked:
        hist = histories[id(ring)]
        pts = [p for p in hist if p is not None]
        if not pts:
            continue
        origin: dict[str, Any] | None = None
        for i, pt in enumerate(pts):
            _apply_momentum(pt, origin)
            origin = origin or pt
            pt["what_changed"] = _what_changed(pts[i - 1], pt) if i else []
        first_risk = pts[0]["risk"]
        last = pts[-1]
        rise = last["risk"] - first_risk
        detected = next(
            (p for p in pts if p["discovered"] and p["risk"] >= escalate_at), None
        )
        rings_out.append(
            {
                "ring_id": ring.ring_id,
                "users": users,
                "primary_pattern": ring.primary_pattern,
                "first_risk": first_risk,
                "final_risk": last["risk"],
                "rise": rise,
                "escalating": rise >= min_rise,
                "crossed": last["risk"] >= escalate_at,
                "detected_day": detected["day"] if detected else None,
                "lead_days": round(last["day"] - detected["day"], 2)
                if detected
                else None,
                "history": pts,
            }
        )

    return {
        "checkpoints": checkpoints,
        "escalate_at": escalate_at,
        "n_tracked": len(rings_out),
        "emerging_ring_ids": [
            r["ring_id"] for r in rings_out if r["escalating"] and r["crossed"]
        ],
        "rings": rings_out,
    }

