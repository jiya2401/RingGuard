"""Legitimate-sharing evidence: the counter-evidence layer (spec §7, §25).

Shared infrastructure is NOT abuse by itself. This module inspects the
graph for *lawful reasons* a cluster might share devices, cards, IPs
and merchants — a household at one address, an office on one network,
old stable accounts, diverse shopping, relaxed timing.

It is the single source of the legitimacy aggregation used by the risk
engine (`backend/risk/engine.py`), which deducts
`LEGITIMATE_DEDUCTION * score` from raw risk; every renderer (WHY NOT
FRAUD, copilot, API) reads the same structured evidence, so the
narrative can never disagree with the numbers.

The shared temporal/merchant helpers used by the engine also live here
to keep a single implementation of each signal.
"""

from __future__ import annotations

from statistics import fmean
from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.detection.rings import Ring

from backend.features.graph_features import _hhi
from backend.graph.schema import (
    USER_LIVES_AT_ADDRESS,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
)

DAY_S = 86_400
STABLE_ACCOUNT_DAYS = 60.0           # mean age beyond this counts as stable

# score -> verdict (spec §7: explicit legitimate-sharing evidence levels)
VERDICT_TIERS: tuple[tuple[float, str], ...] = (
    (0.60, "STRONG"),
    (0.40, "MODERATE"),
    (0.20, "WEAK"),
    (0.00, "NONE"),
)

# Aggregation weights — single source for the engine deduction too.
W_ADDRESS = 0.35
W_STABILITY = 0.30
W_DIVERSITY = 0.20
W_LOW_SYNC = 0.15


def verdict_for_score(score: float) -> str:
    for threshold, verdict in VERDICT_TIERS:
        if score >= threshold:
            return verdict
    return "NONE"


def max_window_share(times: list[int], window_s: int) -> float:
    """Max fraction of `times` falling inside any sliding `window_s` window."""
    n = len(times)
    if n < 2:
        return 0.0
    best = 0
    for i in range(n):
        j = i
        while j < n and times[j] - times[i] <= window_s:
            j += 1
        best = max(best, j - i)
    return best / n


def max_window_count(times: list[int], window_s: int) -> int:
    """Max number of `times` inside any sliding `window_s` window."""
    best = 0
    for i in range(len(times)):
        j = i
        while j < len(times) and times[j] - times[i] <= window_s:
            j += 1
        best = max(best, j - i)
    return best


def ring_txn_times(G: nx.MultiDiGraph, users: set[str]) -> list[int]:
    """Timestamps of every payment/transfer made by `users` (ring activity)."""
    times: list[int] = []
    for u in users:
        if u not in G:
            continue
        for _v, _w, d in G.out_edges(u, data=True):
            if d.get("rel_type") in (USER_PAID_MERCHANT, USER_SENT_TO_USER):
                times.append(d.get("timestamp", 0))
    return sorted(times)


def created_times(G: nx.MultiDiGraph, users: set[str]) -> list[int]:
    return sorted(G.nodes[u].get("created_at", 0) for u in users if u in G)


def default_ref(G: nx.MultiDiGraph) -> int:
    return max((d.get("timestamp", 0) for _, _, d in G.edges(data=True)), default=0)


def synchronization(G: nx.MultiDiGraph, users: set[str], window_s: int = 3_600) -> float:
    """Max share of `users` active within the same `window_s` window.

    Counts *distinct users*, not transactions, so a ring whose members
    each also shop independently is not drowned by background activity:
    coordination shows up as many users acting inside one window.
    """
    events = sorted(
        (d.get("timestamp", 0), u)
        for u in users if u in G
        for _v, _w, d in G.out_edges(u, data=True)
        if d.get("rel_type") in (USER_PAID_MERCHANT, USER_SENT_TO_USER)
    )
    best = 0
    for i, (t, _u) in enumerate(events):
        j = i
        while j < len(events) and events[j][0] - t <= window_s:
            j += 1
        best = max(best, len({u for _t, u in events[i:j]}))
    return best / len(users) if users else 0.0


def ring_merchant_hhi(G: nx.MultiDiGraph, users: set[str]) -> float:
    """Herfindahl index over the merchants `users` pay (1 = one merchant)."""
    from collections import Counter

    merch: Counter = Counter()
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            if d.get("rel_type") == USER_PAID_MERCHANT:
                merch[w] += 1
    return _hhi(list(merch.values()))


def collect_legitimate_evidence(
    G: nx.MultiDiGraph,
    users: set[str],
    ref: int | None = None,
    n_txn: int | None = None,
) -> dict[str, Any]:
    """Inspect `G` for lawful reasons `users` might share infrastructure.

    Returns `{"score": 0..1, "verdict": STRONG/MODERATE/WEAK/NONE,
    "factors": [{signal, value, interpretation}], "details": {...}}`.
    The engine deducts `LEGITIMATE_DEDUCTION * score` from raw risk and
    stores `factors` as the ring's legitimate signals (spec §7, §25).
    """
    users = set(users)
    if ref is None:
        ref = default_ref(G)

    addr_members: dict[str, set[str]] = {}
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            if d.get("rel_type") == USER_LIVES_AT_ADDRESS:
                addr_members.setdefault(w, set()).add(u)
    best_addr, addr_cov = max(
        ((a, len(m) / len(users)) for a, m in addr_members.items()),
        key=lambda kv: kv[1],
        default=(None, 0.0),
    )

    ages = [max(0, ref - c) / DAY_S for c in created_times(G, users)] or [0.0]
    mean_age = fmean(ages)
    oldest = max(ages)
    stability = min(1.0, mean_age / STABLE_ACCOUNT_DAYS)

    times = ring_txn_times(G, users)
    if n_txn is None:
        n_txn = len(times)
    raw_diversity = 1.0 - ring_merchant_hhi(G, users)
    # Diversity is only demonstrable with enough shopping history (a
    # cluster with no payments has shown no diversity).
    history_w = min(1.0, n_txn / max(1, 2 * len(users))) if users else 0.0
    diversity = raw_diversity * history_w

    sync = synchronization(G, users)
    low_sync = 1.0 - sync

    score = (
        W_ADDRESS * addr_cov
        + W_STABILITY * stability
        + W_DIVERSITY * diversity
        + W_LOW_SYNC * low_sync
    )
    factors = [
        {"signal": "shared_address_coverage", "value": round(addr_cov, 3),
         "interpretation": "largest fraction of the cluster living at one address "
         "(household signal)" + (f" ({best_addr})" if best_addr else "")},
        {"signal": "account_age_stability", "value": round(stability, 3),
         "interpretation": f"mean account age {round(mean_age)} days, oldest "
         f"{round(oldest)} days (stable relationships share infrastructure "
         f"legitimately)"},
        {"signal": "merchant_diversity", "value": round(diversity, 3),
         "interpretation": "1 - merchant HHI weighted by shopping history: normal "
         "households and offices shop across many merchants"},
        {"signal": "low_activity_synchronization", "value": round(low_sync, 3),
         "interpretation": "absence of tight timing coordination; legitimate "
         "sharers act independently in time"},
    ]
    return {
        "score": round(score, 3),
        "verdict": verdict_for_score(score),
        "factors": factors,
        "details": {
            "shared_address": best_addr,
            "mean_account_age_days": round(mean_age, 1),
            "oldest_account_days": round(oldest, 1),
            "merchant_diversity_raw": round(raw_diversity, 3),
            "activity_synchronization": round(sync, 3),
            "transactions_observed": int(n_txn),
        },
    }


# Signal name -> aggregation weight (kept in step with collect()).
FACTOR_WEIGHTS = {
    "shared_address_coverage": W_ADDRESS,
    "account_age_stability": W_STABILITY,
    "merchant_diversity": W_DIVERSITY,
    "low_activity_synchronization": W_LOW_SYNC,
}


def evidence_from_ring(ring: "Ring") -> dict[str, Any]:
    """Rebuild an evidence dict from a scored ring's stored signals.

    Lets stored rings (queue snapshots, API payloads) answer WHY NOT
    FRAUD without the graph. The aggregation matches
    `collect_legitimate_evidence` because both use the same weights;
    `details` is only populated by a fresh collection.
    """
    factors: list[dict[str, Any]] = []
    weighted = 0.0
    for s in ring.legitimate_signals:
        w = FACTOR_WEIGHTS.get(s["signal"], 0.0)
        weighted += w * s["value"]
        factors.append(
            {
                "signal": s["signal"],
                "value": s["value"],
                "weight": w,
                "interpretation": s["interpretation"],
            }
        )
    score = round(weighted, 3)
    return {
        "score": score,
        "verdict": verdict_for_score(score),
        "factors": factors,
        "details": {},
    }


def summarize_legitimacy(evidence: dict[str, Any]) -> str:
    """One-line human summary of an evidence dict (for UI / copilot)."""
    verdict = evidence.get("verdict", "NONE")
    d = evidence.get("details", {})
    bits: list[str] = []
    if d.get("shared_address"):
        bits.append(f"shared address {d['shared_address']}")
    if d.get("mean_account_age_days", 0) >= STABLE_ACCOUNT_DAYS:
        bits.append(f"old accounts (~{round(d['mean_account_age_days'])} days)")
    if d.get("merchant_diversity_raw", 0) >= 0.5:
        bits.append("diverse shopping")
    if d.get("activity_synchronization", 1) <= 0.4:
        bits.append("no tight timing coordination")
    body = "; ".join(bits) if bits else "no meaningful counter-evidence"
    return f"{verdict} legitimate-sharing evidence: {body}"

