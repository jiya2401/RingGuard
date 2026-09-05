"""Multi-layer risk engine (spec §11).

For each discovered ring candidate the engine composes interpretable
layers, all computed from the actual graph:

    FINAL RISK ~  w_s*STRUCTURAL  +  w_t*TEMPORAL
                +  w_b*BEHAVIORAL +  w_f*MONEY_FLOW
                -  w_l*LEGITIMATE_SHARING

Every layer returns its score plus named signals (`{signal, value,
interpretation}`) whose values are the real computed quantities — the
"WHY FLAGGED" evidence (spec §24). The legitimate-sharing layer is the
counter-evidence ("WHY NOT FRAUD", spec §25): stable addresses, old
accounts and diverse shopping lower the final risk instead of being
ignored. Risk is a deterministic pure function of `(ring, G, as_of)`.
"""

from __future__ import annotations

from collections import Counter
from statistics import fmean, pstdev
from typing import Any

import networkx as nx
import pandas as pd

from backend.detection.rings import Ring
from backend.features.graph_features import compute_user_features, _hhi
from backend.graph.schema import (
    USER_LIVES_AT_ADDRESS,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
)

DAY_S = 86_400
YOUNG_ACCOUNT_S = 7 * DAY_S          # accounts younger than this are "new"
STABLE_ACCOUNT_DAYS = 60.0           # mean age beyond this counts as stable

# Layer weights (documented in IMPLEMENTATION_PLAN.md §M6).
WEIGHTS = {
    "structural": 0.35,
    "temporal": 0.30,
    "behavioral": 0.15,
    "money_flow": 0.20,
}
LEGITIMATE_DEDUCTION = 0.30          # subtracted share for full legitimate evidence

# Risk score -> recommended action tiers (spec §26).
RECOMMENDATION_TIERS: tuple[tuple[int, str], ...] = (
    (80, "ESCALATE"),
    (65, "INVESTIGATE"),
    (45, "REVIEW"),
    (25, "MONITOR"),
    (0, "DISMISS"),
)


def _signal(name: str, value: Any, interpretation: str) -> dict:
    return {"signal": name, "value": value, "interpretation": interpretation}


def _max_window_share(times: list[int], window_s: int) -> float:
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


def _ring_txn_times(G: nx.MultiDiGraph, users: set[str]) -> list[int]:
    """Timestamps of every payment/transfer made by `users` (ring activity)."""
    times: list[int] = []
    for u in users:
        if u not in G:
            continue
        for _v, _w, d in G.out_edges(u, data=True):
            if d.get("rel_type") in (USER_PAID_MERCHANT, USER_SENT_TO_USER):
                times.append(d.get("timestamp", 0))
    return sorted(times)


def _created_times(G: nx.MultiDiGraph, users: set[str]) -> list[int]:
    return sorted(G.nodes[u].get("created_at", 0) for u in users if u in G)


def _default_ref(G: nx.MultiDiGraph) -> int:
    return max((d.get("timestamp", 0) for _, _, d in G.edges(data=True)), default=0)


def _max_window_count(times: list[int], window_s: int) -> int:
    """Max number of `times` inside any sliding `window_s` window."""
    best = 0
    n = len(times)
    for i in range(n):
        j = i
        while j < n and times[j] - times[i] <= window_s:
            j += 1
        best = max(best, j - i)
    return best


def _synchronization(G: nx.MultiDiGraph, users: set[str], window_s: int = 3_600) -> float:
    """Max share of ring users active within the same `window_s` window.

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


def _temporal_layer(
    G: nx.MultiDiGraph, users: set[str], ref: int
) -> tuple[float, list[dict], int]:
    """Coordination over time (spec §8): multi-user synchronization,
    account-creation velocity, account youth.

    Deliberately counts *distinct users per window* rather than raw
    transaction concentration: per-user background shopping dilutes
    transaction-share measures, while genuine coordination shows up as
    many members acting inside one window.
    """
    times = _ring_txn_times(G, users)
    created = _created_times(G, users)
    sync = _synchronization(G, users)
    creation_velocity = _max_window_share(created, DAY_S)
    youth = (
        fmean(1.0 if ref - c < YOUNG_ACCOUNT_S else 0.0 for c in created)
        if created
        else 0.0
    )
    score = 0.45 * sync + 0.30 * creation_velocity + 0.25 * youth

    peak_window = _max_window_count(times, 3_600) if times else 0
    signals = [
        _signal(
            "user_synchronization",
            round(sync, 3),
            f"{round(sync * len(users))} of {len(users)} ring users transacted within "
            f"the same 1-hour window (peak {peak_window} ring transactions)",
        ),
        _signal(
            "account_creation_velocity",
            round(creation_velocity, 3),
            f"{round(creation_velocity * len(created))} of {len(created)} accounts were "
            f"created within one 24-hour window",
        ),
        _signal(
            "new_account_share",
            round(youth, 3),
            "share of ring accounts younger than 7 days at reference time",
        ),
    ]
    return score, signals, len(times)


def _ring_merchant_hhi(G: nx.MultiDiGraph, users: set[str]) -> float:
    merch: Counter = Counter()
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            if d.get("rel_type") == USER_PAID_MERCHANT:
                merch[w] += 1
    return _hhi(list(merch.values()))


def _behavioral_layer(
    G: nx.MultiDiGraph, users: set[str], feats: pd.DataFrame
) -> tuple[float, list[dict]]:
    """Concentration + burstiness of ring behavior (features from M4)."""
    hhi = _ring_merchant_hhi(G, users)
    sub = feats.loc[sorted(users & set(feats.index))]
    pay_conc = float(sub["payment_concentration"].mean()) if len(sub) else 0.0
    burst = float(sub["temporal_burst_score"].mean()) if len(sub) else 0.0
    score = 0.40 * hhi + 0.30 * pay_conc + 0.30 * burst
    signals = [
        _signal(
            "merchant_concentration",
            round(hhi, 3),
            "share of ring payments absorbed by the single most-used merchant "
            "(1 = one merchant only)",
        ),
        _signal(
            "payment_instrument_concentration",
            round(pay_conc, 3),
            "mean per-user HHI over payment instruments (1 = one instrument)",
        ),
        _signal(
            "mean_user_burstiness",
            round(burst, 3),
            "mean per-user max share of own transactions in any 1-hour window",
        ),
    ]
    return score, signals


def _flow_layer(G: nx.MultiDiGraph, users: set[str]) -> tuple[float, list[dict], int]:
    """Directed user-to-user transfers inside the ring (mule signal)."""
    senders: set[str] = set()
    n_edges = 0
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            if d.get("rel_type") == USER_SENT_TO_USER and w in users:
                senders.add(u)
                n_edges += 1
    participation = len(senders) / len(users) if users else 0.0
    score = min(1.0, participation * 1.25)
    signals = [
        _signal(
            "internal_transfer_participation",
            round(participation, 3),
            f"{len(senders)} of {len(users)} ring users sent money to another ring "
            f"user ({n_edges} internal transfers)",
        ),
    ]
    return score, signals, n_edges


def _legitimate_layer(
    G: nx.MultiDiGraph,
    users: set[str],
    ref: int,
    merchant_diversity: float,
    n_txn: int,
) -> tuple[float, list[dict]]:
    """Counter-evidence: lawful reasons to share infrastructure (spec §7, §25)."""
    addresses: dict[str, set[str]] = {}
    for u in users:
        if u not in G:
            continue
        for _v, w, d in G.out_edges(u, data=True):
            if d.get("rel_type") == USER_LIVES_AT_ADDRESS:
                addresses.setdefault(w, set()).add(u)
    addr_cov = max((len(s) / len(users) for s in addresses.values()), default=0.0)
    created = _created_times(G, users)
    mean_age_days = fmean((ref - c) / DAY_S for c in created) if created else 0.0
    stability = min(1.0, mean_age_days / STABLE_ACCOUNT_DAYS)
    # Diverse shopping only counts as counter-evidence when there is enough
    # shopping history to observe it (a ring with no payments has no
    # demonstrated diversity).
    evidence_w = min(1.0, n_txn / max(1, 2 * len(users)))
    diversity = merchant_diversity * evidence_w
    score = 0.40 * addr_cov + 0.35 * stability + 0.25 * diversity
    signals = [
        _signal(
            "shared_address_coverage",
            round(addr_cov, 3),
            "largest fraction of the ring living at one address (household signal)",
        ),
        _signal(
            "account_age_stability",
            round(stability, 3),
            f"mean account age {round(mean_age_days)} days "
            f"(stable relationships share infrastructure legitimately)",
        ),
        _signal(
            "merchant_diversity",
            round(diversity, 3),
            "1 - merchant HHI, weighted by shopping history: normal households "
            "shop across many merchants",
        ),
    ]
    return score, signals


def _recommendation(risk_score: float) -> str:
    for threshold, action in RECOMMENDATION_TIERS:
        if risk_score >= threshold:
            return action
    return "DISMISS"


def score_ring(
    ring: Ring,
    G: nx.MultiDiGraph,
    as_of: int | None = None,
    feats: pd.DataFrame | None = None,
) -> Ring:
    """Fill `ring` with risk/confidence/drivers/signals (mutates, returns it).

    `feats` may carry a precomputed `compute_user_features` frame; it is
    computed for the ring's users when omitted. `as_of` fixes the reference
    time (defaults to the graph's latest activity) — passing a truncated
    graph with the matching `as_of` keeps scoring causal (M9 evaluation).
    """
    users = set(ring.users)
    ref = as_of if as_of is not None else _default_ref(G)
    if feats is None:
        feats = compute_user_features(G, as_of=ref, users=users, fast=True)

    temporal_s, temporal_sig, n_txn = _temporal_layer(G, users, ref)
    behavioral_s, behavioral_sig = _behavioral_layer(G, users, feats)
    flow_s, flow_sig, _n_flow = _flow_layer(G, users)
    merchant_hhi = _ring_merchant_hhi(G, users)
    legit_s, legit_sig = _legitimate_layer(
        G, users, ref, 1.0 - merchant_hhi, n_txn
    )

    layers = {
        "structural": ring.structural_score,
        "temporal": temporal_s,
        "behavioral": behavioral_s,
        "money_flow": flow_s,
    }
    raw = sum(WEIGHTS[k] * v for k, v in layers.items())
    risk01 = max(0.0, min(1.0, raw - LEGITIMATE_DEDUCTION * legit_s))

    # Confidence: enough evidence + layers agreeing + cluster big enough
    # to be a coordinated structure at all.
    evidence = min(1.0, n_txn / 12)
    agreement = 1.0 - min(1.0, pstdev(layers.values()) / 0.5)
    size_factor = min(1.0, len(users) / 4)
    ring.confidence = round(100 * (0.40 * evidence + 0.35 * agreement + 0.25 * size_factor))

    ring.risk_score = round(100 * risk01)
    ring.risk_signals = temporal_sig + behavioral_sig + flow_sig
    ring.legitimate_signals = legit_sig

    # WHY FLAGGED: each layer's weighted contribution, largest first (§24).
    detail = {
        "structural": "shared devices/payment instruments link the accounts",
        "temporal": temporal_sig[0]["interpretation"],
        "behavioral": behavioral_sig[0]["interpretation"],
        "money_flow": flow_sig[0]["interpretation"],
    }
    ring.drivers = sorted(
        (
            {"layer": k, "contribution": round(WEIGHTS[k] * v, 3), "detail": detail[k]}
            for k, v in layers.items()
        ),
        key=lambda c: c["contribution"],
        reverse=True,
    )
    ring.recommended_action = _recommendation(ring.risk_score)
    return ring


def score_rings(
    rings: list[Ring],
    G: nx.MultiDiGraph,
    as_of: int | None = None,
    feats: pd.DataFrame | None = None,
) -> list[Ring]:
    """Score every ring; features are computed once for all ring users."""
    if feats is None:
        all_users: set[str] = set()
        for r in rings:
            all_users |= set(r.users)
        feats = compute_user_features(G, as_of=as_of, users=all_users, fast=True)
    return [score_ring(r, G, as_of=as_of, feats=feats) for r in rings]



