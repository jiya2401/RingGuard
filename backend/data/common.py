"""Shared deterministic helpers for the synthetic generator.

Determinism contract: every stochastic draw flows through a
`numpy.random.Generator` derived from the global seed plus a per-component
salt via sha256. No module-level ambient randomness is allowed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import numpy as np

# Simulated epoch zero: 2025-01-01T00:00:00Z (all times synthetic).
BASE_TS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())

# Entity id prefixes (readable, collision-free).
ID_PREFIX = {
    "USER": "U",
    "DEVICE": "DEV",
    "CARD": "CARD",
    "BANK_ACCOUNT": "BANK",
    "UPI_ID": "UPI",
    "IP": "IP",
    "MERCHANT": "MER",
    "PHONE": "PH",
    "ADDRESS": "ADDR",
    "MANDATE": "MID",
    "SESSION": "SES",
    "TRANSACTION": "TX",
}

# Human-readable archetype names for reasons/patterns.
ARCHETYPE_NAMES = {
    "A": "device farm",
    "B": "payment-instrument sharing",
    "C": "infrastructure abuse",
    "D": "referral/incentive abuse",
    "E": "synthetic identity cluster",
    "F": "mule/money-flow ring",
    "G": "coordinated burst",
    "H": "emerging ring",
}


def component_rng(seed: int, salt: str) -> np.random.Generator:
    """Deterministic RNG for a named component of the generator."""
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).digest()
    int_seed = int.from_bytes(digest[:8], "little")
    return np.random.default_rng(int_seed)


def entity_id(entity_type: str, n: int) -> str:
    return f"{ID_PREFIX[entity_type]}-{n:04d}"


def ts(day: int, hour: int = 0, minute: int = 0, second: int = 0, base: int = BASE_TS) -> int:
    """Simulated epoch seconds for a given day/hour/minute/second."""
    return base + day * 86_400 + hour * 3_600 + minute * 60 + second


def day_of(ts_value: int, base: int = BASE_TS) -> int:
    return max(0, int((ts_value - base) // 86_400))


def weighted_choice(rng: np.random.Generator, items: Sequence[Any], weights: Sequence[float]) -> Any:
    return items[int(rng.choice(len(items), p=np.asarray(weights, dtype=float) / sum(weights)))]


def choice(rng: np.random.Generator, items: Sequence[Any]) -> Any:
    return items[int(rng.integers(0, len(items)))]


def round_amount(rng: np.random.Generator, base: float = 500.0, spread: float = 0.3) -> float:
    """Round, mule-like amounts (multiples of base)."""
    mult = int(rng.integers(1, 6))
    jitter = 1 + rng.uniform(-spread, spread)
    return round(base * mult * jitter, 2)


def organic_amount(rng: np.random.Generator, mu: float = 4.0, sigma: float = 0.9) -> float:
    """Lognormal 'organic' spend amount, clipped to a sane range."""
    return round(float(np.clip(rng.lognormal(mu, sigma), 5.0, 250_000.0)), 2)


def normal_hour(rng: np.random.Generator) -> int:
    """Hour-of-day for normal users (daytime-weighted)."""
    hours = np.arange(24)
    w = np.array(
        [0.6, 0.3, 0.2, 0.15, 0.15, 0.3, 0.8, 1.6, 2.6, 3.2, 3.0, 3.4, 3.4, 3.0, 2.8, 3.0, 3.4, 3.8, 3.6, 2.6, 1.8, 1.4, 1.0, 0.8],
        dtype=float,
    )
    return int(rng.choice(hours, p=w / w.sum()))


def abuse_hour(rng: np.random.Generator) -> int:
    """Hour-of-day for abuse activity (evening/night weighted)."""
    hours = np.arange(24)
    w = np.array(
        [1.6, 1.2, 1.0, 0.9, 0.8, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2, 2.4, 2.3, 2.1, 1.9, 1.7],
        dtype=float,
    )
    return int(rng.choice(hours, p=w / w.sum()))


def burst_window(
    rng: np.random.Generator, day: int, intensity: float, max_minutes: int = 60
) -> tuple[int, int]:
    """A tight [start, end] window within `day`; tightness scales with intensity."""
    start_hour = int(rng.integers(0, 23))
    start_min = int(rng.integers(0, 60))
    span_min = max(2, int(max_minutes / max(0.5, intensity)))
    start = ts(day, start_hour, start_min)
    return start, start + span_min * 60


def pick(rng: np.random.Generator, pool: Sequence[str], k: int) -> list[str]:
    """Sample k distinct items (k may exceed pool length → repeats allowed)."""
    if k <= len(pool):
        idx = rng.choice(len(pool), size=k, replace=False)
        return [pool[i] for i in idx]
    return [choice(rng, pool) for _ in range(k)]


def iter_entities(ecosystem_entities: dict[str, list[Any]], entity_type: str) -> list[Any]:
    return ecosystem_entities.get(entity_type, [])


def append(ecosystem_entities: dict[str, list[Any]], entity: Any) -> None:
    ecosystem_entities.setdefault(entity.entity_type, []).append(entity)


def next_id(ecosystem_entities: dict[str, list[Any]], entity_type: str) -> str:
    return entity_id(entity_type, len(ecosystem_entities.get(entity_type, [])) + 1)


def next_txn_id(ecosystem_entities: dict[str, list[Any]]) -> str:
    return entity_id("TRANSACTION", len(ecosystem_entities.get("TRANSACTION", [])) + 1)


def merge_dicts(*dicts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for d in dicts:
        out.update(d)
    return out