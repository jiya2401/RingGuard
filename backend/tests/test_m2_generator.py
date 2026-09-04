"""M2 tests: determinism, transaction budget, traceability, and generator invariants."""

from __future__ import annotations

import pytest

from backend.data.config import GeneratorConfig, tiny_config
from backend.data.generator import build_ecosystem
from backend.data.model import (
    ARCHETYPES,
    HARD_NEGATIVES,
    PAYEE_MERCHANT,
    PAYEE_USER,
    TRANSACTION,
    USER,
)
from backend.tests.conftest import entity_index


class TestDeterminism:
    def test_same_seed_same_digest(self):
        eco_a = build_ecosystem(tiny_config(), seed=11)
        eco_b = build_ecosystem(tiny_config(), seed=11)
        assert eco_a.digest() == eco_b.digest()
        assert eco_a.digest() != ""

    def test_different_seeds_differ(self):
        assert build_ecosystem(tiny_config(), seed=11).digest() != build_ecosystem(
            tiny_config(), seed=12
        ).digest()

    def test_config_change_changes_output(self):
        base = tiny_config()
        other = tiny_config(n_merchants=base.n_merchants + 1)
        assert build_ecosystem(base, seed=7).digest() != build_ecosystem(other, seed=7).digest()


class TestTransactionBudget:
    def test_exact_budget(self, tiny_ecosystem, tiny_cfg):
        assert len(tiny_ecosystem.payments) == tiny_cfg.n_transactions
        assert len(tiny_ecosystem.entities[TRANSACTION]) == len(tiny_ecosystem.payments)

    def test_zero_budget_allowed(self):
        """With n_transactions=0 only structural (archetype/hard-negative) traffic exists."""
        eco = build_ecosystem(tiny_config(n_transactions=0), seed=1)
        normal_payments = [p for p in eco.payments if p.archetype is None and p.community is None]
        assert normal_payments == [], "no normal traffic when budget is zero"
        assert len(eco.payments) > 0, "structural traffic (archetypes + hard negatives) still exists"


class TestTraceability:
    def test_every_user_has_reason(self, tiny_ecosystem):
        for e in tiny_ecosystem.entities[USER]:
            assert e.reason and e.reason.strip(), "generated user missing traceable reason"

    def test_abuse_users_tagged(self, tiny_ecosystem):
        for e in tiny_ecosystem.entities[USER]:
            attrs = e.attributes
            if attrs.get("user_type") == "abuse":
                assert e.archetype in ARCHETYPES
                assert e.community is None
            elif attrs.get("user_type") == "legitimate_sharing":
                assert e.community in HARD_NEGATIVES
                assert e.archetype is None

    def test_planted_rings_match_entity_tags(self, tiny_ecosystem):
        idx = entity_index(tiny_ecosystem)
        for plant in tiny_ecosystem.plants:
            for uid in plant.users:
                assert uid in idx, f"plant references unknown user {uid}"
                assert (
                    idx[uid].archetype == plant.archetype
                    or idx[uid].community == plant.archetype
                )


class TestReferentialIntegrity:
    def test_payments_reference_real_entities(self, tiny_ecosystem):
        idx = entity_index(tiny_ecosystem)
        for p in tiny_ecosystem.payments:
            assert p.payer in idx and idx[p.payer].entity_type == USER
            if p.payee_type == PAYEE_USER:
                assert p.payee in idx and idx[p.payee].entity_type == USER
            else:
                assert p.merchant == p.payee
            assert p.instrument in idx, f"missing instrument {p.instrument}"
            assert idx[p.instrument].entity_type == p.instrument_type
            assert p.ip_id in idx
            assert p.device_id in idx
            assert p.session is None or p.session in idx
            assert p.timestamp > 0


class TestConfigValidation:
    def test_invalid_noise_rejected(self):
        with pytest.raises(ValueError):
            GeneratorConfig(noise_level=2.0).validate()

    def test_invalid_archetype_rejected(self):
        with pytest.raises(ValueError):
            GeneratorConfig(archetypes=frozenset({"Z"})).validate()

    def test_invalid_hard_negative_rejected(self):
        with pytest.raises(ValueError):
            GeneratorConfig(hard_negatives=frozenset({"zombies"})).validate()

    def test_nonpositive_transactions_rejected(self):
        with pytest.raises(ValueError):
            GeneratorConfig(n_transactions=-5).validate()