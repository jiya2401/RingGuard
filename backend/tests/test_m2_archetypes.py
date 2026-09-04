"""M2 coverage: every abuse-archetype builder produces a valid, active ring.

The generic tiny config only instantiates a few archetypes, so this file
builds one ring per archetype to exercise each builder and assert its
structural invariants.
"""

from __future__ import annotations

import pytest

from backend.data.config import tiny_config
from backend.data.generator import build_ecosystem
from backend.data.model import USER


def ring_for(archetype: str):
    """Build an ecosystem with exactly one ring of `archetype` and return it."""
    cfg = tiny_config(seed=1, n_rings=1, archetypes=frozenset({archetype}), n_emerging_rings=0)
    eco = build_ecosystem(cfg, seed=1)
    plants = [p for p in eco.plants if p.archetype == archetype]
    assert len(plants) == 1, f"expected exactly one {archetype} ring"
    return eco, plants[0]


ABUSE = ["A", "B", "C", "D", "E", "F", "G"]


@pytest.mark.parametrize("archetype", ABUSE)
def test_archetype_builder_valid(archetype):
    eco, plant = ring_for(archetype)
    assert len(plant.users) >= 3
    # All planted users exist and are tagged.
    user_ids = {e.entity_id for e in eco.entities[USER]}
    assert set(plant.users) <= user_ids
    for uid in plant.users:
        ent = next(e for e in eco.entities[USER] if e.entity_id == uid)
        assert ent.archetype == archetype
    # A planted ring must actually produce payments.
    member_payments = [p for p in eco.payments if p.payer in set(plant.users)]
    assert len(member_payments) >= 5, f"archetype {archetype} produced too few transactions"


@pytest.mark.parametrize("archetype", ABUSE)
def test_archetype_uses_legitimate_merchants(archetype):
    """Abuse must not be trivially separable by a fake merchant set (spec §15)."""
    eco, plant = ring_for(archetype)
    merchant_ids = {e.entity_id for e in eco.entities["MERCHANT"]}
    for m in plant.merchants:
        assert m in merchant_ids, f"{archetype} references non-market merchant {m}"


def test_emerging_ring_builder():
    cfg = tiny_config(seed=2, n_rings=0, archetypes=frozenset(), n_emerging_rings=1)
    eco = build_ecosystem(cfg, seed=2)
    emerging = [p for p in eco.plants if p.archetype == "H"]
    assert len(emerging) == 1
    plant = emerging[0]
    assert len(plant.growth) >= 2, "emerging ring needs a multi-step timeline"
    sizes = [g["n_users"] for g in plant.growth]
    assert sizes == sorted(sizes)


def test_mule_has_directed_p2p_flow():
    eco, plant = ring_for("F")
    member_set = set(plant.users)
    p2p = [p for p in eco.payments if p.payee_type == "user" and p.payer in member_set]
    assert len(p2p) >= 5, "mule ring needs directed user-to-user flows"