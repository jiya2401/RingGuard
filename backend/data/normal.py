"""'Normal' side of the synthetic ecosystem: market infrastructure and
organic user transactions.

These users exhibit realistic spending: lognormal amounts, favorite
merchants, daytime activity weighting, mild device/IP/card reuse, and
natural instrument proportions. They are the pool that should NEVER be
flagged as coordinated abuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.data.common import (
    append,
    choice,
    next_id,
    next_txn_id,
    normal_hour,
    organic_amount,
    pick,
    ts,
)
from backend.data.config import GeneratorConfig
from backend.data.model import (
    ADDRESS,
    BANK_ACCOUNT,
    CARD,
    DEVICE,
    Entity,
    IP,
    MANDATE,
    MERCHANT,
    PAYEE_MERCHANT,
    Payment,
    PHONE,
    SESSION,
    TRANSACTION,
    UPI_ID,
    USER,
)

MARKET_CATEGORIES = [
    "groceries", "food_delivery", "transport", "utilities", "digital_services",
    "retail", "entertainment", "travel", "health", "education",
]

IP_KINDS = ["residential", "residential", "residential", "mobile", "datacenter"]


@dataclass
class Market:
    """Id pools the rest of the generator draws from."""

    merchants: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)
    upi_ids: list[str] = field(default_factory=list)
    bank_ids: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)


def generate_marketplace(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict[str, list[Entity]]
) -> Market:
    """Create the shared market infrastructure (merchants, IPs, devices, instruments)."""

    def make(eid: str, etype: str, created: int, attrs: dict[str, Any], reason: str) -> None:
        append(entities, Entity(eid, etype, created, attrs, reason=reason))

    market = Market()

    for _ in range(cfg.n_merchants):
        mid = next_id(entities, MERCHANT)
        market.merchants.append(mid)
        make(mid, MERCHANT, ts(-cfg.max_account_age_days),
             {"category": choice(rng, MARKET_CATEGORIES), "name": f"Merchant {mid}",
              "avg_ticket": round(float(rng.lognormal(4.2, 0.8)), 2)},
             "market merchant serving normal and business traffic")

    for _ in range(cfg.n_ips):
        iid = next_id(entities, IP)
        market.ips.append(iid)
        make(iid, IP, ts(-cfg.max_account_age_days),
             {"kind": choice(rng, IP_KINDS), "cidr": f"203.0.{113}.{int(rng.integers(1, 255))}"},
             "shared network pool (residential/mobile/datacenter)")

    for _ in range(cfg.n_devices):
        did = next_id(entities, DEVICE)
        market.devices.append(did)
        make(did, DEVICE, ts(-cfg.max_account_age_days),
             {"kind": choice(rng, ["mobile", "mobile", "desktop", "tablet"]),
              "os": choice(rng, ["android", "ios", "windows", "macos"])},
             "device in the shared ecosystem pool")

    for _ in range(cfg.n_cards):
        cid = next_id(entities, CARD)
        market.cards.append(cid)
        make(cid, CARD, ts(-cfg.max_account_age_days),
             {"issuer": choice(rng, ["VISA", "MC", "RUPAY"]), "last4": f"{int(rng.integers(0, 10000)):04d}"},
             "payment card in the shared ecosystem pool")

    for _ in range(cfg.n_bank_accounts):
        bid = next_id(entities, BANK_ACCOUNT)
        market.bank_ids.append(bid)
        make(bid, BANK_ACCOUNT, ts(-cfg.max_account_age_days),
             {"bank": choice(rng, ["HDFC", "ICICI", "SBI", "Kotak"])},
             "bank account in the shared ecosystem pool")

    for _ in range(cfg.n_upi_ids):
        uid = next_id(entities, UPI_ID)
        market.upi_ids.append(uid)
        make(uid, UPI_ID, ts(0, int(rng.integers(0, 24)), int(rng.integers(0, 60))),
             {"handle": choice(rng, ["@okicici", "@okhdfcbank", "@ybl", "@paytm"])},
             "UPI id in the shared ecosystem pool")

    for _ in range(cfg.n_phones):
        pid = next_id(entities, PHONE)
        market.phones.append(pid)
        make(pid, PHONE, ts(-cfg.max_account_age_days),
             {"number": f"+91-9{int(rng.integers(10_000_000, 99_999_999))}"},
             "phone number in the shared ecosystem pool")

    for _ in range(cfg.n_addresses):
        aid = next_id(entities, ADDRESS)
        market.addresses.append(aid)
        make(aid, ADDRESS, ts(-cfg.max_account_age_days),
             {"city": choice(rng, ["Bengaluru", "Mumbai", "Delhi", "Pune", "Hyderabad"])},
             "address in the shared ecosystem pool")

    return market


def _allocate_counts(rng: np.random.Generator, n_users: int, total: int) -> list[int]:
    """Split `total` into n_users non-negative integers as evenly as possible."""
    if total <= 0:
        return [0] * n_users
    base, rem = divmod(total, n_users)
    extra = set(int(i) for i in rng.choice(n_users, size=rem, replace=False))
    return [base + (1 if i in extra else 0) for i in range(n_users)]


def generate_normal_users(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
    total_txns: int,
) -> list[str]:
    """Create normal users and exactly `total_txns` organic transactions."""
    user_ids: list[str] = []

    for i in range(cfg.n_users):
        uid = next_id(entities, USER)
        user_ids.append(uid)
        home_ip = choice(rng, market.ips)
        primary_device = choice(rng, market.devices)
        secondary_pool = [d for d in market.devices if d != primary_device]
        secondary_device = choice(rng, secondary_pool) if secondary_pool else primary_device
        card = choice(rng, market.cards)
        upi = choice(rng, market.upi_ids)
        bank = choice(rng, market.bank_ids)
        addr = choice(rng, market.addresses)
        phone = choice(rng, market.phones)
        favorites = pick(rng, market.merchants, min(3, len(market.merchants)))

        if rng.uniform() < 0.8:
            age_days = int(rng.integers(5, cfg.max_account_age_days))
            created_at = ts(-age_days, int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        else:
            created_at = ts(int(rng.integers(0, cfg.days)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))

        append(
            entities,
            Entity(
                uid,
                USER,
                created_at,
                {
                    "user_type": "normal",
                    "card": card,
                    "upi": upi,
                    "bank": bank,
                    "phone": phone,
                    "address": addr,
                    "devices": [primary_device, secondary_device],
                    "home_ip": home_ip,
                    "favorites": favorites,
                    "spend_mu": float(rng.uniform(3.4, 4.8)),
                    "spend_sigma": float(rng.uniform(0.7, 1.1)),
                },
                reason="normal user with organic spending behavior",
            ),
        )

        if rng.uniform() < 0.25:
            mid = next_id(entities, MANDATE)
            append(
                entities,
                Entity(
                    mid,
                    MANDATE,
                    created_at + 86_400,
                    {"user": uid, "instrument": card if rng.uniform() < 0.5 else bank},
                    reason="normal recurring-payment mandate",
                ),
            )

    per_user = _allocate_counts(rng, cfg.n_users, total_txns)

    for i, uid in enumerate(user_ids):
        sessions: dict[int, str] = {}
        user_entity = next(e for e in entities[USER] if e.entity_id == uid)
        attr = user_entity.attributes
        # A user cannot transact before their own account creation.

        earliest_day = max(0, int((user_entity.created_at - ts(0)) // 86_400))

        for _ in range(per_user[i]):
            day = int(rng.integers(earliest_day, cfg.days))
            hour = normal_hour(rng)
            when = ts(day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))

            merchant = choice(rng, attr["favorites"])
            if rng.uniform() < 0.25:
                merchant = choice(rng, market.merchants)

            amount = organic_amount(rng, attr["spend_mu"], attr["spend_sigma"])
            device = attr["devices"][0] if rng.uniform() < 0.85 else attr["devices"][1]
            ip = attr["home_ip"] if rng.uniform() >= 0.20 else choice(rng, market.ips)

            roll = rng.uniform()
            if roll < 0.80:
                instr_type, instrument = CARD, attr["card"]
            elif roll < 0.95:
                instr_type, instrument = UPI_ID, attr["upi"]
            else:
                instr_type, instrument = BANK_ACCOUNT, attr["bank"]

            session_id = sessions.get(day)
            if session_id is None:
                session_id = _ensure_session(entities, uid, day, when, device, ip, sessions)
            sessions[day] = session_id

            txn_id = next_txn_id(entities)
            append(
                entities,
                Entity(
                    txn_id,
                    TRANSACTION,
                    when,
                    {"amount": amount, "status": "success", "payer": uid, "payee": merchant},
                    reason=f"normal purchase at {merchant}",
                ),
            )
            payments.append(
                Payment(
                    transaction_id=txn_id,
                    payer=uid,
                    payee_type=PAYEE_MERCHANT,
                    payee=merchant,
                    amount=amount,
                    instrument_type=instr_type,
                    instrument=instrument,
                    ip_id=ip,
                    device_id=device,
                    merchant=merchant,
                    session=session_id,
                    timestamp=when,
                    reason=f"normal purchase at {merchant}",
                )
            )

    return user_ids


def _ensure_session(
    entities: dict[str, list[Entity]],
    user: str,
    day: int,
    when: int,
    device: str,
    ip: str,
    sessions: dict[int, str],
) -> str:
    """Create (or reuse for the day) a login session entity for a user."""
    existing = sessions.get(day)
    if existing is not None:
        return existing
    sid = next_id(entities, SESSION)
    sessions[day] = sid
    append(
        entities,
        Entity(
            sid,
            SESSION,
            when,
            {"user": user, "device": device, "ip": ip, "day": day},
            reason="login session for a normal user",
        ),
    )
    return sid