"""Generator configuration (spec §4).

All scale knobs, archetype toggles, and hard-negative sizes live here so
experiments are reproducible from a single typed config object.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.data.model import ARCHETYPES, HARD_NEGATIVES


@dataclass(frozen=True)
class GeneratorConfig:
    """Deterministic, validated configuration for the synthetic ecosystem."""

    # ---- global determinism ----
    seed: int = 42

    # ---- ecosystem scale ----
    n_users: int = 120
    n_devices: int = 25
    n_cards: int = 18
    n_bank_accounts: int = 8
    n_upi_ids: int = 60
    n_ips: int = 18
    n_merchants: int = 26
    n_phones: int = 90
    n_addresses: int = 45
    n_mandates: int = 30
    n_transactions: int = 12_000
    days: int = 30  # evaluation horizon (train 1-21 / val 22-25 / test 26-30)

    # ---- abuse rings ----
    n_rings: int = 4  # non-emerging abuse rings (archetypes A-G)
    ring_size: int = 8
    n_emerging_rings: int = 1
    emerging_ring_size: int = 9

    # ---- signal controls ----
    noise_level: float = 0.15  # 0..1: fraction of abuse activity made "normal-looking"
    attack_intensity: float = 1.0  # scales synchronization / burst tightness
    privacy_level: float = 0.45  # 0..1: fraction of normal users with PRIVATE device+card

    # ---- hard negatives (legitimate sharing, spec §6) ----
    n_households: int = 2
    household_size: int = 4
    n_offices: int = 1
    office_size: int = 6
    n_campuses: int = 1
    campus_size: int = 5
    n_businesses: int = 1
    business_size: int = 4
    n_family_cards: int = 1
    family_card_size: int = 4

    # ---- archetype toggles ----
    archetypes: frozenset = frozenset(ARCHETYPES)
    hard_negatives: frozenset = frozenset(HARD_NEGATIVES)

    # ---- time model ----
    # Normal / hard-negative accounts may predate the evaluation window.
    max_account_age_days: int = 180

    def validate(self) -> "GeneratorConfig":
        if self.n_users <= 0 or self.n_transactions < 0 or self.days <= 0:
            raise ValueError("n_users and days must be positive; n_transactions must be >= 0")
        if not (0.0 <= self.noise_level <= 1.0):
            raise ValueError("noise_level must be in [0, 1]")
        if not (0.0 <= self.privacy_level <= 1.0):
            raise ValueError("privacy_level must be in [0, 1]")
        if self.attack_intensity <= 0:
            raise ValueError("attack_intensity must be > 0")
        if not self.archetypes <= frozenset(ARCHETYPES):
            raise ValueError(f"unknown archetypes: {self.archetypes - frozenset(ARCHETYPES)}")
        if not self.hard_negatives <= frozenset(HARD_NEGATIVES):
            raise ValueError(
                f"unknown hard negatives: {self.hard_negatives - frozenset(HARD_NEGATIVES)}"
            )
        if self.ring_size < 3 or self.emerging_ring_size < 3:
            raise ValueError("ring sizes must be >= 3")
        return self

    def __post_init__(self) -> None:
        self.validate()


# Small config used by fast unit tests.
def tiny_config(**overrides) -> GeneratorConfig:
    base = dict(
        seed=7,
        n_users=12,
        n_devices=4,
        n_cards=4,
        n_bank_accounts=2,
        n_upi_ids=6,
        n_ips=4,
        n_merchants=6,
        n_phones=10,
        n_addresses=6,
        n_mandates=2,
        n_transactions=400,
        days=30,
        privacy_level=0.55,
        n_rings=2,
        ring_size=4,
        n_emerging_rings=1,
        emerging_ring_size=6,
        n_households=1,
        household_size=3,
        n_offices=0,
        n_campuses=0,
        n_businesses=0,
        n_family_cards=0,
    )
    base.update(overrides)
    return GeneratorConfig(**base)


# Demo config matching the spec §46 demo dataset scale.
def demo_config(**overrides) -> GeneratorConfig:
    base = dict(
        seed=42,
        n_users=120,
        n_devices=25,
        n_cards=18,
        n_bank_accounts=8,
        n_upi_ids=60,
        n_ips=18,
        n_merchants=26,
        n_phones=90,
        n_addresses=45,
        n_mandates=30,
        n_transactions=12_000,
        days=30,
        privacy_level=0.45,
        n_rings=4,
        ring_size=8,
        n_emerging_rings=1,
        emerging_ring_size=9,
        noise_level=0.15,
        attack_intensity=1.0,
        n_households=2,
        household_size=4,
        n_offices=1,
        office_size=6,
        n_campuses=1,
        campus_size=5,
        n_businesses=1,
        business_size=4,
        n_family_cards=1,
        family_card_size=4,
    )
    base.update(overrides)
    return GeneratorConfig(**base)