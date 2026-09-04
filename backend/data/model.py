"""Core data model for the synthetic payment ecosystem.

Every record carries a human-readable `reason` and (when applicable) an
`archetype` / `community` tag so that each generated artifact is traceable
to the scenario that created it (spec §4: "every generated record should
have a traceable reason for its existence").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

# Entity type constants shared across the backend.
USER = "USER"
DEVICE = "DEVICE"
CARD = "CARD"
BANK_ACCOUNT = "BANK_ACCOUNT"
UPI_ID = "UPI_ID"
IP = "IP"
MERCHANT = "MERCHANT"
PHONE = "PHONE"
ADDRESS = "ADDRESS"
MANDATE = "MANDATE"
SESSION = "SESSION"
TRANSACTION = "TRANSACTION"

ENTITY_TYPES = (
    USER,
    DEVICE,
    CARD,
    BANK_ACCOUNT,
    UPI_ID,
    IP,
    MERCHANT,
    PHONE,
    ADDRESS,
    MANDATE,
    SESSION,
    TRANSACTION,
)

# Transaction payee types
PAYEE_MERCHANT = "merchant"
PAYEE_USER = "user"

# Abuse archetypes (spec §5) and hard negatives (spec §6)
ARCHETYPES = ("A", "B", "C", "D", "E", "F", "G", "H")
HARD_NEGATIVES = ("household", "office", "campus", "business", "family_card")


@dataclass
class Entity:
    """A node in the payment ecosystem (USER/DEVICE/CARD/... or TRANSACTION)."""

    entity_id: str
    entity_type: str
    created_at: int  # simulated epoch seconds (see common.BASE_TS)
    attributes: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    archetype: str | None = None  # "A".."H" when part of a planted abuse ring
    community: str | None = None  # "household" / "office" / ... for hard negatives

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "created_at": self.created_at,
            "attributes": self.attributes,
            "reason": self.reason,
            "archetype": self.archetype,
            "community": self.community,
        }


@dataclass
class Payment:
    """A single simulated transaction (always synthetic)."""

    transaction_id: str
    payer: str  # USER entity id
    payee_type: str  # merchant | user
    payee: str  # MERCHANT entity id or USER entity id
    amount: float
    instrument_type: str  # CARD | BANK_ACCOUNT | UPI_ID
    instrument: str  # entity id of the payment instrument
    ip_id: str
    device_id: str
    merchant: str | None = None
    session: str | None = None
    timestamp: int = 0
    reason: str = ""
    archetype: str | None = None
    community: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RingPlant:
    """Ground-truth description of a planted abuse ring / hard-negative community.

    Used by tests and evaluation to measure detection without hiding
    exactly what was planted and why.
    """

    ring_id: str
    archetype: str  # "A".."H" for abuse rings; "household" etc. for hard negatives
    pattern: str  # human-readable primary pattern
    users: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    merchants: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    # For emerging rings: ordered list of {"day": int, "n_users": int, "event": str}
    growth: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Ecosystem:
    """The fully generated ecosystem: entities, payments, and ground truth."""

    seed: int
    entities: dict[str, list[Entity]]  # keyed by ENTITY_TYPES
    payments: list[Payment]
    plants: list[RingPlant] = field(default_factory=list)

    # Useful for M2 tests without importing config (avoided cycle).
    profile: dict[str, Any] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        """Compact, deterministic summary (counts per type, per archetype)."""
        entity_counts = {t: len(self.entities.get(t, [])) for t in ENTITY_TYPES}
        archetype_users: dict[str, int] = {}
        archetype_txns: dict[str, int] = {}
        community_users: dict[str, int] = {}
        for t, entities in self.entities.items():
            for e in entities:
                if e.archetype:
                    archetype_users[e.archetype] = archetype_users.get(e.archetype, 0) + 1
                if e.community:
                    community_users[e.community] = community_users.get(e.community, 0) + 1
        for p in self.payments:
            if p.archetype:
                archetype_txns[p.archetype] = archetype_txns.get(p.archetype, 0) + 1
        return {
            "seed": self.seed,
            "entities": entity_counts,
            "n_payments": len(self.payments),
            "archetype_users": archetype_users,
            "archetype_txns": archetype_txns,
            "community_users": community_users,
            "n_plants": len(self.plants),
            "total_value": round(sum(p.amount for p in self.payments), 2),
            "profile": self.profile,
        }

    def canonical_bytes(self) -> bytes:
        """Deterministic serialization used for the reproducibility digest."""
        payload = {
            "seed": self.seed,
            "profile": self.profile,
            "entities": {
                t: sorted((e.to_dict() for e in entities), key=lambda d: d["entity_id"])
                for t, entities in self.entities.items()
            },
            "payments": sorted(
                (p.to_dict() for p in self.payments), key=lambda d: d["transaction_id"]
            ),
            "plants": sorted(
                (p.to_dict() for p in self.plants), key=lambda d: d["ring_id"]
            ),
        }
        text = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return text.encode("utf-8")

    def digest(self) -> str:
        """sha256 over the canonical serialization — two identical runs → same hash."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()