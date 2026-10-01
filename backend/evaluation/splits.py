"""Leakage-free transaction features and chronological data splits.

Every row is built immediately before the corresponding event is added to the
rolling state.  Graph-enhanced counters therefore describe only evidence that
existed strictly before the transaction being scored; labels are never used as
features.  The same immutable split labels feed every baseline comparison.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import log1p, pi, sin, cos

import pandas as pd

from backend.data.common import BASE_TS
from backend.data.model import ARCHETYPES, Ecosystem, PAYEE_USER

DAY_S = 86_400

BASELINE_FEATURES = (
    "log_amount",
    "hour_sin",
    "hour_cos",
    "is_p2p",
    "is_card",
    "is_bank",
    "is_upi",
    "account_age_days",
)

GRAPH_FEATURES = (
    "payer_prior_txns",
    "payer_prior_devices",
    "payer_prior_instruments",
    "payer_prior_recipients",
    "device_prior_users",
    "instrument_prior_users",
    "ip_prior_users",
    "seconds_since_previous_log",
)


@dataclass(frozen=True)
class SplitBoundaries:
    """Forward-only split boundaries measured in simulated days."""

    train_end_day: int = 21
    validation_end_day: int = 25
    horizon_end_day: int = 30

    def label(self, timestamp: int, window_start: int = BASE_TS) -> str:
        day = (timestamp - window_start) / DAY_S
        if day < self.train_end_day:
            return "train"
        if day < self.validation_end_day:
            return "validation"
        if day <= self.horizon_end_day + 1:
            return "test"
        return "outside"


def build_transaction_frame(
    ecosystem: Ecosystem,
    boundaries: SplitBoundaries | None = None,
) -> pd.DataFrame:
    """Create one deterministic, strictly causal row per transaction."""
    boundaries = boundaries or SplitBoundaries(
        horizon_end_day=int(ecosystem.profile.get("days", 30))
    )
    window_start = int(ecosystem.profile.get("window_start", BASE_TS))
    created = {
        e.entity_id: e.created_at
        for e in ecosystem.entities.get("USER", [])
    }

    payer_txns: defaultdict[str, int] = defaultdict(int)
    payer_devices: defaultdict[str, set[str]] = defaultdict(set)
    payer_instruments: defaultdict[str, set[str]] = defaultdict(set)
    payer_recipients: defaultdict[str, set[str]] = defaultdict(set)
    device_users: defaultdict[str, set[str]] = defaultdict(set)
    instrument_users: defaultdict[str, set[str]] = defaultdict(set)
    ip_users: defaultdict[str, set[str]] = defaultdict(set)
    last_seen: dict[str, int] = {}
    rows: list[dict] = []

    for payment in sorted(
        ecosystem.payments, key=lambda p: (p.timestamp, p.transaction_id)
    ):
        payer = payment.payer
        hour = (payment.timestamp // 3_600) % 24
        angle = 2 * pi * hour / 24
        previous = last_seen.get(payer)
        row = {
            "transaction_id": payment.transaction_id,
            "timestamp": payment.timestamp,
            "day": round((payment.timestamp - window_start) / DAY_S, 6),
            "split": boundaries.label(payment.timestamp, window_start),
            "label": int(payment.archetype in ARCHETYPES),
            "archetype": payment.archetype or "",
            "hard_negative": bool(payment.community),
            "log_amount": log1p(max(0.0, payment.amount)),
            "hour_sin": sin(angle),
            "hour_cos": cos(angle),
            "is_p2p": int(payment.payee_type == PAYEE_USER),
            "is_card": int(payment.instrument_type == "CARD"),
            "is_bank": int(payment.instrument_type == "BANK_ACCOUNT"),
            "is_upi": int(payment.instrument_type == "UPI_ID"),
            "account_age_days": max(
                0.0, (payment.timestamp - created.get(payer, payment.timestamp)) / DAY_S
            ),
            # Strictly-prior graph state. The current event is added below.
            "payer_prior_txns": payer_txns[payer],
            "payer_prior_devices": len(payer_devices[payer]),
            "payer_prior_instruments": len(payer_instruments[payer]),
            "payer_prior_recipients": len(payer_recipients[payer]),
            "device_prior_users": len(device_users[payment.device_id]),
            "instrument_prior_users": len(instrument_users[payment.instrument]),
            "ip_prior_users": len(ip_users[payment.ip_id]),
            "seconds_since_previous_log": log1p(
                max(0, payment.timestamp - previous) if previous is not None else 0
            ),
        }
        rows.append(row)

        payer_txns[payer] += 1
        payer_devices[payer].add(payment.device_id)
        payer_instruments[payer].add(payment.instrument)
        payer_recipients[payer].add(payment.payee)
        device_users[payment.device_id].add(payer)
        instrument_users[payment.instrument].add(payer)
        ip_users[payment.ip_id].add(payer)
        last_seen[payer] = payment.timestamp

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame[frame["split"] != "outside"].reset_index(drop=True)
    return frame


def validate_split(frame: pd.DataFrame) -> None:
    """Raise when split ordering, uniqueness, or coverage is invalid."""
    required = {"train", "validation", "test"}
    found = set(frame["split"].unique()) if not frame.empty else set()
    if not required <= found:
        raise ValueError(f"missing chronological split(s): {sorted(required - found)}")
    if frame["transaction_id"].duplicated().any():
        raise ValueError("transaction leaked into more than one row")
    maxima = frame.groupby("split")["timestamp"].agg(["min", "max"])
    if not (
        maxima.loc["train", "max"] < maxima.loc["validation", "min"]
        and maxima.loc["validation", "max"] < maxima.loc["test", "min"]
    ):
        raise ValueError("splits overlap or are not strictly forward in time")


def split_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return defensive copies of the three chronological partitions."""
    validate_split(frame)
    return {
        name: frame.loc[frame["split"] == name].copy()
        for name in ("train", "validation", "test")
    }
