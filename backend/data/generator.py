"""Top-level synthetic ecosystem generator (spec §4).

Pipeline: marketplace -> hard negatives -> abuse archetypes -> normal
users (fill remaining transaction budget). Each component uses its own
deterministic RNG salt (derived from the global seed) so the whole build
is reproducible from (config, seed). Transactions are sorted
chronologically at the end for the storage / API layer.
"""

from __future__ import annotations

from backend.data.archetypes import generate_archetypes
from backend.data.common import component_rng
from backend.data.config import GeneratorConfig, demo_config
from backend.data.hard_negatives import generate_hard_negatives
from backend.data.model import (
    TRANSACTION,
    Ecosystem,
    Payment,
)
from backend.data.normal import generate_marketplace, generate_normal_users


def build_ecosystem(
    cfg: GeneratorConfig | None = None,
    seed: int | None = None,
) -> Ecosystem:
    """Deterministically build a complete synthetic ecosystem."""
    cfg = (cfg or demo_config()).validate()
    seed = int(seed if seed is not None else cfg.seed)

    entities: dict[str, list] = {}
    payments: list[Payment] = []

    marketplace = generate_marketplace(component_rng(seed, "marketplace"), cfg, entities)
    hard_negative_plants = generate_hard_negatives(
        component_rng(seed, "hard_negatives"), cfg, entities, payments, marketplace
    )
    archetype_plants = generate_archetypes(
        component_rng(seed, "archetypes"), cfg, entities, payments, marketplace
    )

    # Normal users organically fill the remaining transaction budget.
    budget = max(0, cfg.n_transactions - len(payments))
    generate_normal_users(
        component_rng(seed, "normal"), cfg, entities, payments, marketplace, budget
    )

    # Chronological ordering (M3 graph builder consumes events in time order).
    entities[TRANSACTION].sort(key=lambda e: e.created_at)
    payments.sort(key=lambda p: p.timestamp)

    plants = archetype_plants + hard_negative_plants
    ecosystem = Ecosystem(seed=seed, entities=entities, payments=payments, plants=plants)
    ecosystem.profile = _profile(ecosystem, cfg)
    return ecosystem


def _profile(ecosystem: Ecosystem, cfg: GeneratorConfig) -> dict:
    """Human-readable profile stored on the ecosystem (from actual data)."""
    archetype_set = {"A", "B", "C", "D", "E", "F", "G", "H"}
    abuse_rings = [p for p in ecosystem.plants if p.archetype in archetype_set]
    emerging = [p for p in ecosystem.plants if p.archetype == "H"]
    return {
        "n_abuse_rings": len(abuse_rings),
        "n_hard_negative_communities": len(ecosystem.plants) - len(abuse_rings),
        "emerging_rings": [p.growth for p in emerging],
        "noise_level": cfg.noise_level,
        "attack_intensity": cfg.attack_intensity,
        "days": cfg.days,
    }