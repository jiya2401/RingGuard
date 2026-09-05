"""Multi-layer risk engine (spec §11).

For each discovered ring candidate the engine composes interpretable
layers, all computed from the actual graph:

    FINAL RISK ~  w_s*STRUCTURAL  +  w_t*TEMPORAL
                +  w_b*BEHAVIORAL +  w_f*MONEY_FLOW
                -  LEGITIMATE_DEDUCTION*LEGITIMATE_SHARING

Every layer returns its score plus named signals (`{signal, value,
interpretation}`) whose values are the real computed quantities — the
"WHY FLAGGED" evidence (spec §24). The legitimate-sharing layer is the
counter-evidence ("WHY NOT FRAUD", spec §25): shared addresses, old
stable accounts, diverse shopping and relaxed timing lower the final
risk instead of being ignored. Its aggregation lives in
`backend/risk/legitimacy.py` and is shared with every renderer, so the
narrative can never disagree with the numbers. Risk is a deterministic
pure function of `(ring, G, as_of)`.
"""

from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any

import networkx as nx
import pandas as pd

from backend.detection.rings import Ring
from backend.features.graph_features import compute_user_features
from backend.graph.schema import USER_SENT_TO_USER
from backend.risk.legitimacy import (
    DAY_S,
    collect_legitimate_evidence,
    created_times as _created_times,
    default_ref as _default_ref,
    max_window_count as _max_window_count,
    max_window_share as _max_window_share,
    ring_merchant_hhi as _ring_merchant_hhi,
    ring_txn_times as _ring_txn_times,
    synchronization as _synchronization,
)

YOUNG_ACCOUNT_S = 7 * DAY_S          # accounts younger than this are "new"

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
    legit = collect_legitimate_evidence(G, users, ref=ref)
    legit_s = legit["score"]

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
    ring.legitimate_signals = legit["factors"]

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



