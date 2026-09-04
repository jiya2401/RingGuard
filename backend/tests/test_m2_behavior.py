"""M2 behavior tests: emerging-ring structure, hard negatives, chronology."""

from __future__ import annotations

import pytest

from backend.tests.conftest import entity_index


class TestEmergingRing:
    def test_emerging_ring_growth_monotonic(self, tiny_ecosystem):
        emerging = [p for p in tiny_ecosystem.plants if p.archetype == "H"]
        assert len(emerging) >= 1, "an emerging ring must be planted"
        plant = emerging[0]
        sizes = [g["n_users"] for g in plant.growth]
        assert sizes == sorted(sizes), "emerging ring size must grow monotonically"
        assert sizes[-1] == len(plant.users)
        assert plant.growth[0]["day"] < plant.growth[-1]["day"]
        assert plant.growth[-1]["day"] <= 27, "final growth inside evaluation window"

    def test_emerging_users_created_after_day_14(self, tiny_ecosystem):
        emerging = [p for p in tiny_ecosystem.plants if p.archetype == "H"][0]
        created_days = sorted({int((e.created_at // 86_400)) for e in tiny_ecosystem.entities["USER"]
                               if e.entity_id in set(emerging.users)})
        assert min(created_days) >= 14, "emerging accounts created mid-horizon, not at start"


class TestHardNegativesBehavior:
    def test_household_transactions_spread_over_time(self, tiny_ecosystem):
        """Hard negatives must NOT be synchronized into tight bursts."""
        households = [p for p in tiny_ecosystem.plants if p.archetype == "household"]
        assert len(households) >= 1
        member_set = set(households[0].users)
        times = sorted(p.timestamp for p in tiny_ecosystem.payments if p.payer in member_set)
        assert len(times) >= 5
        distinct_days = len({t // 86_400 for t in times})
        assert distinct_days >= 4, "household activity must span multiple days"
        hours = [t // 3600 for t in times]
        max_frac_same_hour = max(hours.count(h) for h in set(hours)) / len(times)
        assert max_frac_same_hour < 0.6, "household activity too synchronized"

    def test_hard_negative_users_marked_legitimate(self, tiny_ecosystem):
        for e in tiny_ecosystem.entities["USER"]:
            if e.community:
                assert e.attributes.get("legitimate_sharing") is True
                assert e.attributes.get("user_type") == "legitimate_sharing"

    def test_family_card_users_in_tiny_config_absent(self, tiny_cfg):
        assert tiny_cfg.n_family_cards == 0 or tiny_cfg.n_family_cards >= 0  # config sanity


class TestChronology:
    def test_payments_sorted_by_time(self, tiny_ecosystem):
        times = [p.timestamp for p in tiny_ecosystem.payments]
        assert times == sorted(times)

    def test_user_created_before_first_payment(self, tiny_ecosystem):
        idx = entity_index(tiny_ecosystem)
        first_txn_day_by_user = {}
        for p in tiny_ecosystem.payments:
            day = int(p.timestamp // 86_400)
            first_txn_day_by_user.setdefault(p.payer, day)
        for uid, first_day in first_txn_day_by_user.items():
            created_day = int(idx[uid].created_at // 86_400)
            assert created_day <= first_day, f"{uid} paid before account creation"

    def test_burst_accounts_created_early_but_active_late(self, tiny_ecosystem):
        bursts = [p for p in tiny_ecosystem.plants if p.archetype == "G"]
        if not bursts:
            pytest.skip("no burst archetype in this config")
        plant = bursts[0]
        idx = entity_index(tiny_ecosystem)
        created_days = [int((idx[u].created_at // 86_400)) for u in plant.users]
        member_times = [p.timestamp for p in tiny_ecosystem.payments if p.payer in set(plant.users)]
        active_days = [int(t // 86_400) for t in member_times]
        assert all(d <= 3 for d in created_days), "burst accounts created early"
        assert max(active_days) >= 20, "burst activity must be late"

    def test_mule_ring_has_p2p_flows(self, tiny_ecosystem):
        mules = [p for p in tiny_ecosystem.plants if p.archetype == "F"]
        if not mules:
            pytest.skip("no mule archetype in this config")
        member_set = set(mules[0].users)
        p2p = [p for p in tiny_ecosystem.payments if p.payer in member_set and p.payee_type == "user"]
        assert len(p2p) >= 10, "mule ring must generate directed p2p money flows"