"""Abuse archetypes (spec §5): A device farm, B payment sharing,
C infrastructure abuse, D referral abuse, E synthetic identity,
F mule/money-flow ring, G coordinated burst, H emerging ring.

Each archetype produces a `RingPlant` ground-truth description so tests
and the emerging-risk engine can measure detection without hiding what
was planted.

Design choices that make this HARD (per spec §38, §15):
- Abuse rings use LEGITIMATE-LOOKING merchants (from the normal market)
  so merchants do not trivially separate abuse from normal traffic.
- `noise_level` injects some normal-looking activity into abuse users.
- `attack_intensity` scales how tight synchronized windows are.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from backend.data.common import (
    append,
    choice,
    next_id,
    next_txn_id,
    organic_amount,
    pick,
    round_amount,
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
    PAYEE_MERCHANT,
    PAYEE_USER,
    Payment,
    PHONE,
    RingPlant,
    SESSION,
    TRANSACTION,
    UPI_ID,
    USER,
)
from backend.data.normal import Market, _ensure_session


def _mk_device(entities: dict, rng: np.random.Generator, reason: str) -> str:
    did = next_id(entities, DEVICE)
    append(entities, Entity(did, DEVICE, ts(-5, int(rng.integers(0, 24))),
                            {"kind": choice(rng, ["mobile", "desktop"])}, reason=reason))
    return did


def _mk_card(entities: dict, rng: np.random.Generator, reason: str) -> str:
    cid = next_id(entities, CARD)
    append(entities, Entity(cid, CARD, ts(-4, int(rng.integers(0, 24))),
                            {"issuer": choice(rng, ["VISA", "MC", "RUPAY"]),
                             "last4": f"{int(rng.integers(0, 10000)):04d}"}, reason=reason))
    return cid


def _mk_ip(entities: dict, rng: np.random.Generator, reason: str) -> str:
    iid = next_id(entities, IP)
    append(entities, Entity(iid, IP, ts(-5, int(rng.integers(0, 24))),
                            {"kind": choice(rng, ["mobile", "datacenter", "residential"])}, reason=reason))
    return iid


def _mk_phone(entities: dict, rng: np.random.Generator, reason: str) -> str:
    pid = next_id(entities, PHONE)
    append(entities, Entity(pid, PHONE, ts(-5, int(rng.integers(0, 24))),
                            {"number": f"+91-9{int(rng.integers(10_000_000, 99_999_999))}"}, reason=reason))
    return pid


def _mk_address(entities: dict, rng: np.random.Generator, reason: str) -> str:
    aid = next_id(entities, ADDRESS)
    append(entities, Entity(aid, ADDRESS, ts(-5, int(rng.integers(0, 24))),
                            {"city": choice(rng, ["Mumbai", "Delhi", "Bengaluru"])}, reason=reason))
    return aid


def _abuse_user(
    entities: dict,
    rng: np.random.Generator,
    archetype: str,
    created_at: int,
    attrs: dict,
    reason: str,
) -> str:
    uid = next_id(entities, USER)
    merged = {"user_type": "abuse", "archetype": archetype}
    merged.update(attrs)
    append(entities, Entity(uid, USER, created_at, merged, reason=reason, archetype=archetype))
    return uid


def _make_session(entities: dict, uid: str, day: int, when: int, device: str, ip: str) -> str:
    sid = next_id(entities, SESSION)
    append(entities, Entity(sid, SESSION, when, {"user": uid, "device": device, "ip": ip, "day": day},
                            reason="abuse-activity session"))
    return sid


def build_device_farm(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """A: many accounts on a couple of shared devices; high sync; small merchant set."""
    arch = "A"
    rid = f"R-A-{ring_index:02d}"
    shared_devs = [_mk_device(entities, rng, f"device-farm shared device ({rid})") for _ in range(2)]
    shared_card = _mk_card(entities, rng, f"device-farm shared card ({rid})")
    shared_ip = _mk_ip(entities, rng, f"device-farm shared ip ({rid})")
    merchants = pick(rng, market.merchants, 3)
    users: list[str] = []
    for _ in range(cfg.ring_size):
        created = ts(int(rng.integers(4, 8)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": shared_card, "devices": shared_devs, "home_ip": shared_ip,
                                  "favorites": merchants}, f"device-farm account ({rid})"))
    for day in (9, 12, 15, 18, 21, 24):
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                           {"devices": shared_devs, "cards": [shared_card], "ips": [shared_ip]},
                           day, n_each=3, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                           merchants=merchants, window_min=60)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="device farm: many accounts on few shared devices with synchronized bursts",
                     users=users, devices=shared_devs, cards=[shared_card], ips=[shared_ip],
                     merchants=merchants)


def _sync_members_txns(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict,
    payments: list[Payment],
    market: Market,
    archetype: str,
    users: list[str],
    shared: dict,
    day: int,
    n_each: int,
    amount_fn: Callable[[np.random.Generator], float],
    merchants: list[str] | None = None,
    p2p_dest: list[str] | None = None,
    window_min: int = 120,
    intensity: float | None = None,
) -> None:
    """All members transact in one tight window on `day` (temporal coordination)."""
    intensity = intensity if intensity is not None else cfg.attack_intensity
    start_h = int(rng.integers(0, 23))
    start_m = int(rng.integers(0, 60))
    span_s = int(max(60, (window_min * 60) / max(0.5, intensity)))
    t0 = ts(day, start_h, start_m)
    merchant_pool = merchants or market.merchants

    for uid in users:
        device = choice(rng, shared["devices"]) if shared["devices"] else choice(rng, market.devices)
        ip = choice(rng, shared["ips"]) if shared["ips"] else choice(rng, market.ips)
        card = choice(rng, shared["cards"]) if shared["cards"] else None
        for _ in range(n_each):
            when = t0 + int(rng.integers(0, span_s))
            mch = None
            if p2p_dest:
                payee_type, payee = PAYEE_USER, choice(rng, p2p_dest)
            else:
                payee_type, payee = PAYEE_MERCHANT, choice(rng, merchant_pool)
                mch = payee
            amount = amount_fn(rng)

            if rng.uniform() < cfg.noise_level:  # inject normal-looking signal
                device = choice(rng, market.devices)
                ip = choice(rng, market.ips)

            if card and rng.uniform() < 0.85:
                instr_type, instrument = CARD, card
            elif rng.uniform() < 0.5:
                instr_type, instrument = BANK_ACCOUNT, choice(rng, market.bank_ids)
            else:
                instr_type, instrument = UPI_ID, choice(rng, market.upi_ids)

            session = _make_session(entities, uid, day, when, device, ip)
            txn_id = next_txn_id(entities)
            append(
                entities,
                Entity(txn_id, TRANSACTION, when, {"amount": amount, "status": "success", "payer": uid,
                                                   "payee": payee}, reason=f"archetype {archetype} activity"),
            )
            payments.append(
                Payment(transaction_id=txn_id, payer=uid, payee_type=payee_type, payee=payee,
                        amount=amount, instrument_type=instr_type, instrument=instrument,
                        ip_id=ip, device_id=device, merchant=mch, session=session, timestamp=when,
                        reason=f"archetype {archetype} activity", archetype=archetype),
            )


def build_payment_sharing(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """B: accounts reuse the same payment instrument(s); own devices mostly."""
    arch = "B"
    rid = f"R-B-{ring_index:02d}"
    shared_card = _mk_card(entities, rng, f"payment-sharing shared card ({rid})")
    shared_card2 = _mk_card(entities, rng, f"payment-sharing shared card ({rid})")
    merchants = pick(rng, market.merchants, 4)
    shared_devs = [_mk_device(entities, rng, f"payment-sharing device ({rid})")]
    users: list[str] = []
    for _ in range(cfg.ring_size):
        created = ts(int(rng.integers(6, 10)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        ip = _mk_ip(entities, rng, f"payment-sharing ip ({rid})")
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": shared_card, "devices": [choice(rng, shared_devs)], "home_ip": ip,
                                  "favorites": merchants}, f"payment-reuse account ({rid})"))
    for day in range(11, 28, 2):
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                           {"devices": shared_devs, "cards": [shared_card, shared_card2], "ips": []},
                           day, n_each=2, amount_fn=lambda r: organic_amount(r, 4.1, 1.1),
                           merchants=merchants, window_min=180)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="payment-instrument sharing: multiple accounts reuse the same cards",
                     users=users, devices=shared_devs, cards=[shared_card, shared_card2],
                     merchants=merchants)


def build_infrastructure_abuse(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """C: suspicious accounts share infrastructure (IP + occasional device)."""
    arch = "C"
    rid = f"R-C-{ring_index:02d}"
    shared_ips = [_mk_ip(entities, rng, f"infra-abuse ip ({rid})") for _ in range(2)]
    shared_dev = _mk_device(entities, rng, f"infra-abuse device ({rid})")
    merchants = pick(rng, market.merchants, 5)
    users: list[str] = []
    for _ in range(cfg.ring_size):
        created = ts(int(rng.integers(8, 14)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        card = _mk_card(entities, rng, f"infra-abuse card ({rid})")
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": card, "devices": [shared_dev], "home_ip": choice(rng, shared_ips),
                                  "favorites": merchants}, f"infra-reuse account ({rid})"))
    for day in range(15, 30, 2):
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                           {"devices": [shared_dev], "cards": [], "ips": shared_ips},
                           day, n_each=2, amount_fn=lambda r: organic_amount(r, 4.2, 1.0),
                           merchants=merchants, window_min=240)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="infrastructure abuse: shared IPs/device across suspicious accounts",
                     users=users, devices=[shared_dev], ips=shared_ips, merchants=merchants)


def build_referral_abuse(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """D: coordinated account creation within a tight window + incentive flows."""
    arch = "D"
    rid = f"R-D-{ring_index:02d}"
    merchants = pick(rng, market.merchants, 2)
    shared_dev = _mk_device(entities, rng, f"referral-abuse device ({rid})")
    shared_ip = _mk_ip(entities, rng, f"referral-abuse ip ({rid})")
    # A referrer who seeds the others; created a few days earlier.
    anchor_day = int(rng.integers(10, 12))
    referrer = _abuse_user(entities, rng, arch, ts(anchor_day, 8, 0),
                           {"card": _mk_card(entities, rng, f"referrer card ({rid})"),
                            "devices": [shared_dev], "home_ip": shared_ip, "favorites": merchants},
                           f"referral referrer ({rid})")
    users = [referrer]
    # Accounts created in a tight ~18h window the next day.
    for _ in range(cfg.ring_size - 1):
        created = ts(anchor_day + 1, int(rng.integers(0, 18)), int(rng.integers(0, 60)))
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": _mk_card(entities, rng, f"referral card ({rid})"),
                                  "devices": [shared_dev], "home_ip": shared_ip, "favorites": merchants},
                                 f"referral-incentive account ({rid})"))
    # Small p2p 'incentive' transfers from referrer + spends at the reward merchant.
    for day in (anchor_day + 1, anchor_day + 2):
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users[1:],
                           {"devices": [shared_dev], "cards": [], "ips": [shared_ip]},
                           day, n_each=1, amount_fn=lambda r: round(float(rng.uniform(50, 300)), 2),
                           p2p_dest=[referrer], window_min=240)
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                           {"devices": [shared_dev], "cards": [], "ips": [shared_ip]},
                           day, n_each=1, amount_fn=lambda r: organic_amount(r, 4.0, 0.9),
                           merchants=merchants, window_min=240)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="referral/incentive abuse: burst account creation + small coordinated flows",
                     users=users, devices=[shared_dev], ips=[shared_ip], merchants=merchants)


def build_synthetic_identity(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """E: suspicious combination of phone/address/device with uniform small amounts."""
    arch = "E"
    rid = f"R-E-{ring_index:02d}"
    shared_addr = _mk_address(entities, rng, f"synthetic identity address ({rid})")
    shared_dev = _mk_device(entities, rng, f"synthetic identity device ({rid})")
    shared_ip = _mk_ip(entities, rng, f"synthetic identity ip ({rid})")
    shared_phone = _mk_phone(entities, rng, f"synthetic identity phone ({rid})")
    merchants = pick(rng, market.merchants, 3)
    users: list[str] = []
    for _ in range(cfg.ring_size):
        created = ts(int(rng.integers(5, 9)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": _mk_card(entities, rng, f"synthetic identity card ({rid})"),
                                  "devices": [shared_dev], "home_ip": shared_ip,
                                  "address": shared_addr, "favorites": merchants, "phone": shared_phone},
                                 f"synthetic-identity account ({rid})"))
    for day in range(9, 29, 2):
        # similar small round amounts, moderate sync
        _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                           {"devices": [shared_dev], "cards": [], "ips": [shared_ip]},
                           day, n_each=2, amount_fn=lambda r: round(float(rng.uniform(900, 1100)), 0),
                           merchants=merchants, window_min=180)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="synthetic identity cluster: shared phone/address/device + uniform amounts",
                     users=users, devices=[shared_dev], ips=[shared_ip],
                     addresses=[shared_addr], merchants=merchants)


def _p2p(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    sender: str, receiver: str, amount: float, when: int, archetype: str,
    device: str, ip: str, card: str | None = None, upi_pool: list[str] | None = None,
) -> None:
    """A directed user-to-user transfer (money-flow edge)."""
    if card and rng.uniform() < 0.5:
        instr_type, instrument = CARD, card
    elif upi_pool:
        instr_type, instrument = UPI_ID, choice(rng, upi_pool)
    else:
        instr_type, instrument = UPI_ID, "UPI-POOL"
    session = _make_session(entities, sender, int((when - ts(0)) / 86_400), when, device, ip)
    txn_id = next_txn_id(entities)
    append(entities, Entity(txn_id, TRANSACTION, when, {"amount": amount, "status": "success",
                                                        "payer": sender, "payee": receiver},
                            reason=f"archetype {archetype} money flow"))
    payments.append(Payment(transaction_id=txn_id, payer=sender, payee_type=PAYEE_USER, payee=receiver,
                            amount=amount, instrument_type=instr_type, instrument=instrument,
                            ip_id=ip, device_id=device, merchant=None, session=session, timestamp=when,
                            reason=f"archetype {archetype} money flow", archetype=archetype))


def build_mule_ring(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """F: mule / money-flow ring. Chain A->B->C->hub and feeders -> hub, round amounts + cash-out."""
    arch = "F"
    rid = f"R-F-{ring_index:02d}"
    n = cfg.ring_size
    shared_ip = _mk_ip(entities, rng, f"mule ring ip ({rid})")
    shared_dev = _mk_device(entities, rng, f"mule ring device ({rid})")
    merchants = pick(rng, market.merchants, 3)
    users: list[str] = []
    for i in range(n):
        created = ts(3, int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        care= _mk_card(entities, rng, f"mule card ({rid})")
        role = "hub" if i == n - 1 else ("chain" if i < min(4, n - 1) else "feeder")
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": care, "devices": [shared_dev], "home_ip": shared_ip,
                                  "flow_role": role, "favorites": merchants}, f"mule account ({rid})"))

    hub = users[-1]
    chain = users[: min(4, n - 1)]
    feeders = users[min(4, n - 1):-1]

    for day in range(4, 29):
        when0 = ts(day, 9, 0)
        # chain: A->B->C->...->hub
        for i in range(len(chain) - 1):
            _p2p(rng, cfg, entities, payments, chain[i], chain[i + 1], round_amount(rng, 500.0),
                 when0 + int(rng.integers(0, 600)), arch, shared_dev, shared_ip, upi_pool=market.upi_ids)
        if chain:
            _p2p(rng, cfg, entities, payments, chain[-1], hub, round_amount(rng, 500.0),
                 when0 + 600 + int(rng.integers(0, 600)), arch, shared_dev, shared_ip, upi_pool=market.upi_ids)
        for f in feeders:
            _p2p(rng, cfg, entities, payments, f, hub, round_amount(rng, 500.0),
                 when0 + int(rng.integers(1200, 1800)), arch, shared_dev, shared_ip, upi_pool=market.upi_ids)
    # cash-out: hub spends at merchants later
    for day in (10, 15, 20, 25, 27, 28):
        _sync_members_txns(rng, cfg, entities, payments, market, arch, [hub],
                           {"devices": [shared_dev], "cards": [], "ips": [shared_ip]},
                           day, n_each=2, amount_fn=lambda r: round_amount(r, 500.0),
                           merchants=merchants, window_min=120)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="mule/money-flow ring: directed p2p chains and hubs with round amounts",
                     users=users, devices=[shared_dev], ips=[shared_ip], merchants=merchants)


def build_burst(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """G: accounts dormant since creation, then all active in a narrow time window."""
    arch = "G"
    rid = f"R-G-{ring_index:02d}"
    shared_dev = _mk_device(entities, rng, f"burst shared device ({rid})")
    shared_ip = _mk_ip(entities, rng, f"burst shared ip ({rid})")
    merchants = pick(rng, market.merchants, 2)
    users: list[str] = []
    for _ in range(cfg.ring_size):
        created = ts(int(rng.integers(0, 3)), int(rng.integers(0, 24)), int(rng.integers(0, 60)))
        users.append(_abuse_user(entities, rng, arch, created,
                                 {"card": _mk_card(entities, rng, f"burst card ({rid})"),
                                  "devices": [shared_dev], "home_ip": shared_ip, "favorites": merchants},
                                 f"burst account ({rid})"))
    burst_day = int(rng.integers(21, 24))
    # a single, very tight synchronized burst (intensity boosted)
    _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                       {"devices": [shared_dev], "cards": [], "ips": [shared_ip]},
                       burst_day, n_each=5, amount_fn=lambda r: organic_amount(r, 3.9, 1.0),
                       merchants=merchants, window_min=60, intensity=cfg.attack_intensity * 1.5)
    # a follow-up cash-out next day
    _sync_members_txns(rng, cfg, entities, payments, market, arch, users,
                       {"devices": [shared_dev], "cards": [], "ips": []},
                       burst_day + 1, n_each=2, amount_fn=lambda r: organic_amount(r, 3.9, 1.0),
                       merchants=merchants, window_min=120, intensity=cfg.attack_intensity)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="coordinated burst: dormant accounts erupt together in a narrow window",
                     users=users, devices=[shared_dev], ips=[shared_ip], merchants=merchants)


def build_emerging_ring(
    rng: np.random.Generator, cfg: GeneratorConfig, entities: dict, payments: list[Payment],
    market: Market, ring_index: int,
) -> RingPlant:
    """H: the ring is BUILT GRADUALLY, so risk rises before it becomes obvious."""
    arch = "H"
    rid = f"R-H-{ring_index:02d}"
    shared_dev = _mk_device(entities, rng, f"emerging shared device ({rid})")
    shared_card = _mk_card(entities, rng, f"emerging shared card ({rid})")
    shared_ip = _mk_ip(entities, rng, f"emerging shared ip ({rid})")
    merchants = pick(rng, market.merchants, 3)
    users: list[str] = []
    growth: list[dict] = []
    target = max(3, cfg.emerging_ring_size)
    days = [15, 17, 19, 22, 25, 27]
    remaining = max(0, target - 2)
    # Distribute the remaining growth across the later days, favouring end-loaded growth.
    slot = [max(0, remaining // 5)] * 5
    for i in range(remaining % 5):
        slot[4 - i] += 1
    week_events = list(zip(days[1:], slot))
    schedule = [(days[0], 2)] + [(d, a) for d, a in week_events if a > 0]
    created_days: dict[str, int] = {}
    for day, add in schedule:
        for _ in range(add):
            created = ts(day, int(rng.integers(0, 24)), int(rng.integers(0, 60)))
            uid = _abuse_user(entities, rng, arch, created,
                              {"card": shared_card, "devices": [shared_dev], "home_ip": shared_ip,
                               "favorites": merchants}, f"emerging-ring account ({rid})")
            users.append(uid)
            created_days[uid] = day
        growth.append({"day": day, "n_users": len(users),
                       "event": f"{add} account(s) created (cumulative {len(users)})"})

    def existing_on(day: int) -> list[str]:
        """Members existing by a given simulated day (causality-safe)."""
        return [u for u in users if created_days[u] <= day]

    # Light, loosely coordinated activity as it forms.
    _sync_members_txns(rng, cfg, entities, payments, market, arch, existing_on(16),
                       {"devices": [shared_dev], "cards": [shared_card], "ips": [shared_ip]},
                       16, n_each=1, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                       merchants=merchants, window_min=300)
    _sync_members_txns(rng, cfg, entities, payments, market, arch, existing_on(20),
                       {"devices": [shared_dev], "cards": [shared_card], "ips": [shared_ip]},
                       20, n_each=2, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                       merchants=merchants, window_min=240)
    # Escalation: tighter windows, more txns, entire (forming) ring.
    _sync_members_txns(rng, cfg, entities, payments, market, arch, existing_on(23),
                       {"devices": [shared_dev], "cards": [shared_card], "ips": [shared_ip]},
                       23, n_each=3, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                       merchants=merchants, window_min=120)
    _sync_members_txns(rng, cfg, entities, payments, market, arch, existing_on(26),
                       {"devices": [shared_dev], "cards": [shared_card], "ips": [shared_ip]},
                       26, n_each=4, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                       merchants=merchants, window_min=90)
    _sync_members_txns(rng, cfg, entities, payments, market, arch, existing_on(28),
                       {"devices": [shared_dev], "cards": [shared_card], "ips": [shared_ip]},
                       28, n_each=5, amount_fn=lambda r: organic_amount(r, 4.0, 1.0),
                       merchants=merchants, window_min=60)
    return RingPlant(ring_id=rid, archetype=arch,
                     pattern="emerging ring: size and coordination grow gradually over time",
                     users=users, devices=[shared_dev], cards=[shared_card], ips=[shared_ip],
                     merchants=merchants, growth=growth)


BUILDERS = {
    "A": build_device_farm,
    "B": build_payment_sharing,
    "C": build_infrastructure_abuse,
    "D": build_referral_abuse,
    "E": build_synthetic_identity,
    "F": build_mule_ring,
    "G": build_burst,
}


def generate_archetypes(
    rng: np.random.Generator,
    cfg: GeneratorConfig,
    entities: dict,
    payments: list[Payment],
    market: Market,
) -> list[RingPlant]:
    """Plant the configured non-emerging abuse rings + emerging rings.

    Archetype assignment cycles deterministically through the enabled set so
    every seed produces the same mix (unless the config changes).
    """
    enabled = sorted(set(cfg.archetypes) - {"H"})
    if not enabled:
        enabled = ["A"]
    plants: list[RingPlant] = []
    for i in range(cfg.n_rings):
        arch = enabled[i % len(enabled)]
        plants.append(BUILDERS[arch](rng, cfg, entities, payments, market, i + 1))
    for j in range(cfg.n_emerging_rings):
        plants.append(build_emerging_ring(rng, cfg, entities, payments, market, j + 1))
    return plants