"""Hard negatives (spec §6): legitimate communities that LOOK like abuse.

Household, office, campus, business, and family-card groups share
infrastructure (IP, devices, addresses, payment instruments) but behave
normally: low synchronization, organic amounts, merchant diversity,
older accounts, and stable relationships.

The risk engine MUST learn that shared infrastructure != coordinated abuse.
"""

from __future__ import annotations

from typing import Callable

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
    BANK_ACCOUNT,
    CARD,
    Entity,
    PAYEE_MERCHANT,
    Payment,
    RingPlant,
    TRANSACTION,
    UPI_ID,
    USER,
)
from backend.data.normal import Market, _ensure_session


def _legit_community(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
    community_type: str,
    n_members: int,
    shared: dict,
    activity_rate: float,
    hour_fn: Callable[[np.random.Generator], int],
    instrument_policy: str,
    account_age_range: tuple[int, int],
    pattern: str,
    spend_mu: float = 4.2,
) -> RingPlant:
    """Generic legitimate-sharing community builder (low synchronization)."""
    ring_id = f"HN-{community_type.upper()}-{len([p for p in entities.get(USER, []) if p.community == community_type]) + 1:02d}"
    users: list[str] = []
    merchants: list[str] = []
    shared_devices = shared.get("devices", [])
    shared_card = shared.get("card")

    for m in range(n_members):
        uid = next_id(entities, USER)
        users.append(uid)
        age_days = int(rng.integers(account_age_range[0], account_age_range[1]))
        created_at = ts(-age_days, int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        own_card = choice(rng, market.cards)
        own_upi = choice(rng, market.upi_ids)
        favorites = pick(rng, market.merchants, min(4, len(market.merchants)))
        merchants.extend(favorites)

        append(
            entities,
            Entity(
                uid,
                USER,
                created_at,
                {
                    "user_type": "legitimate_sharing",
                    "community": community_type,
                    "card": own_card,
                    "upi": own_upi,
                    "shared_card": shared_card,
                    "home_ip": shared.get("ip"),
                    "address": shared.get("address"),
                    "devices": shared_devices,
                    "favorites": favorites,
                    "spend_mu": spend_mu,
                    "spend_sigma": 1.0,
                    "legitimate_sharing": True,
                },
                reason=f"{community_type} member legitimately shares {', '.join(shared.keys())}",
                community=community_type,
            ),
        )

    _transactions_for_members(
        rng, cfg, entities, payments, market, users, activity_rate, hour_fn,
        instrument_policy,
    )

    return RingPlant(
        ring_id=ring_id,
        archetype=community_type,
        pattern=pattern,
        users=users,
        devices=shared_devices,
        cards=[shared_card] if shared_card else [],
        ips=[shared.get("ip")] if shared.get("ip") else [],
        addresses=[shared.get("address")] if shared.get("address") else [],
        merchants=sorted(set(merchants)),
    )


def _transactions_for_members(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
    users: list[str],
    activity_rate: float,
    hour_fn: Callable[[np.random.Generator], int],
    instrument_policy: str,
) -> None:
    """Independent, low-synchronization transactions for legit members."""
    for uid in users:
        sessions: dict[int, str] = {}
        user_entity = next(e for e in entities[USER] if e.entity_id == uid)
        attr = user_entity.attributes
        n_days_active = int(rng.integers(8, cfg.days))
        active_days = sorted(int(d) for d in rng.choice(cfg.days, size=n_days_active, replace=False))

        for day in active_days:
            n_txns = int(rng.integers(1, 4)) if rng.uniform() < activity_rate else 0
            for _ in range(n_txns):
                hour = hour_fn(rng)
                when = ts(day, hour, int(rng.integers(0, 60)), int(rng.integers(0, 60)))
                merchant = choice(rng, attr["favorites"])
                if rng.uniform() < 0.3:
                    merchant = choice(rng, market.merchants)
                amount = organic_amount(rng, attr["spend_mu"], attr["spend_sigma"])
                device = choice(rng, attr["devices"]) if attr["devices"] else choice(rng, market.devices)

                roll = rng.uniform()
                if instrument_policy == "shared_card" and attr.get("shared_card") and roll < 0.8:
                    instr_type, instrument = CARD, attr["shared_card"]
                elif instrument_policy == "shared_card":
                    instr_type, instrument = CARD, attr["card"]
                elif roll < 0.8:
                    instr_type, instrument = CARD, attr["card"]
                elif roll < 0.95:
                    instr_type, instrument = UPI_ID, attr["upi"]
                else:
                    instr_type, instrument = BANK_ACCOUNT, choice(rng, market.bank_ids)

                ip = attr["home_ip"] if rng.uniform() < 0.75 else choice(rng, market.ips)
                session_id = _ensure_session(entities, uid, day, when, device, ip, sessions)

                txn_id = next_txn_id(entities)
                append(
                    entities,
                    Entity(
                        txn_id,
                        TRANSACTION,
                        when,
                        {"amount": amount, "status": "success", "payer": uid, "payee": merchant},
                        reason=f"{community_type_of(attr)} member purchase at {merchant}",
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
                        reason=f"{community_type_of(attr)} member purchase at {merchant}",
                        community=attr.get("community"),
                    ),
                )


def community_type_of(attr: dict) -> str:
    return attr.get("community", "legitimate_sharing")


def _work_hours(rng: np.random.Generator) -> int:
    return int(rng.integers(9, 19))


def build_household(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> RingPlant:
    """Family members sharing home IP, home device, address and a family card."""
    shared = {
        "address": choice(rng, market.addresses),
        "ip": choice(rng, market.ips),
        "devices": [choice(rng, market.devices) for _ in range(2)],
        "card": choice(rng, market.cards),
    }
    return _legit_community(
        rng, cfg, entities, payments, market, "household", cfg.household_size, shared,
        activity_rate=0.55, hour_fn=normal_hour, instrument_policy="mixed",
        account_age_range=(90, 500),
        pattern="stable household: shared home IP/device/address/family card with organic purchasing",
    )


def build_office(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> RingPlant:
    """Employees sharing office IP and company devices, weekday work hours."""
    shared = {
        "ip": choice(rng, market.ips),
        "devices": [choice(rng, market.devices) for _ in range(2)],
    }
    return _legit_community(
        rng, cfg, entities, payments, market, "office", cfg.office_size, shared,
        activity_rate=0.6, hour_fn=_work_hours, instrument_policy="own",
        account_age_range=(60, 300),
        pattern="office: employees share office IP/company devices during work hours",
        spend_mu=4.0,
    )


def build_campus(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> RingPlant:
    """Students sharing campus network and lab devices, irregular hours."""
    shared = {
        "ip": choice(rng, market.ips),
        "devices": [choice(rng, market.devices) for _ in range(3)],
    }
    return _legit_community(
        rng, cfg, entities, payments, market, "campus", cfg.campus_size, shared,
        activity_rate=0.5, hour_fn=normal_hour, instrument_policy="own",
        account_age_range=(30, 200),
        pattern="campus: students share campus IP and lab devices with organic spending",
        spend_mu=3.6,
    )


def build_business(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> RingPlant:
    """Organizational users sharing company infrastructure and bank accounts."""
    shared = {
        "ip": choice(rng, market.ips),
        "devices": [choice(rng, market.devices) for _ in range(2)],
        "bank": choice(rng, market.bank_ids),
    }
    return _legit_community(
        rng, cfg, entities, payments, market, "business", cfg.business_size, shared,
        activity_rate=0.65, hour_fn=_work_hours, instrument_policy="own",
        account_age_range=(100, 700),
        pattern="business: organizational accounts share company infrastructure with normal cadence",
        spend_mu=5.0,
    )


def build_family_card(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> RingPlant:
    """Multiple legit users transacting on one shared card (policy 'shared_card')."""
    shared = {
        "card": choice(rng, market.cards),
        "address": choice(rng, market.addresses),
    }
    return _legit_community(
        rng, cfg, entities, payments, market, "family_card", cfg.family_card_size, shared,
        activity_rate=0.5, hour_fn=normal_hour, instrument_policy="shared_card",
        account_age_range=(100, 600),
        pattern="family card: several users share one payment card with spread, organic usage",
    )


BUILDERS = {
    "household": build_household,
    "office": build_office,
    "campus": build_campus,
    "business": build_business,
    "family_card": build_family_card,
}


def generate_hard_negatives(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict[str, list[Entity]],
    payments: list[Payment],
    market: Market,
) -> list[RingPlant]:
    """Generate every enabled hard-negative community."""
    plants: list[RingPlant] = []
    for community in sorted(cfg.hard_negatives):
        builder = BUILDERS[community]
        if community == "household":
            count = cfg.n_households
        elif community == "office":
            count = cfg.n_offices
        elif community == "campus":
            count = cfg.n_campuses
        elif community == "family_card":
            count = cfg.n_family_cards
        else:
            count = cfg.n_businesses
        for _ in range(count):
            plants.append(builder(rng, cfg, entities, payments, market))
    return plants