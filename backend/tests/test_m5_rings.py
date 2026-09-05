"""M5 tests: ring discovery from the real graph (spec §10).

These tests verify that ring discovery is *causal*, *deterministic*,
achieves candidate-level recall on planted abuse rings, and ranks
hard negatives (household sharing) below genuine coordination.
"""

from __future__ import annotations

import pytest

from backend.data.config import demo_config, tiny_config
from backend.data.generator import build_ecosystem
from backend.data.model import ARCHETYPES
from backend.detection.rings import Ring, discover_rings
from backend.graph.builder import build_graph


@pytest.fixture(scope="module")
def rings_tiny():
    eco = build_ecosystem(tiny_config(), seed=7)
    G = build_graph(eco)
    return eco, G, discover_rings(G)


class TestRingContract:
    """Every discovered ring carries the full spec §10 contract."""

    def test_rings_discovered(self, rings_tiny):
        _, _, rings = rings_tiny
        assert rings, "discovery must produce candidates on the tiny ecosystem"

    def test_required_fields(self, rings_tiny):
        _, _, rings = rings_tiny
        for r in rings:
            assert r.ring_id.startswith("R-")
            assert r.size == len(r.users) >= 3
            assert r.entity_types == ["USER"]
            assert r.primary_pattern, "primary_pattern must be classified"
            assert 0.0 <= r.structural_score <= 1.0
            assert r.risk_signals, "structural signals must be explainable"
            assert r.timeline, "component timeline must be present"
            assert r.status == "NEW"
            assert set(r.affected_entities) >= {"devices", "cards", "ips", "merchants"}

    def test_to_dict_keys(self, rings_tiny):
        _, _, rings = rings_tiny
        d = rings[0].to_dict()
        assert {
            "ring_id", "users", "structural_score", "risk_score", "confidence",
            "size", "entity_types", "primary_pattern", "risk_signals",
            "legitimate_signals", "timeline", "estimated_simulated_exposure",
            "affected_entities", "status",
        } <= set(d)

    def test_rings_sorted_by_score(self, rings_tiny):
        _, _, rings = rings_tiny
        scores = [r.structural_score for r in rings]
        assert scores == sorted(scores, reverse=True)


class TestRecall:
    """Candidate-level recall on planted abuse rings (no labels used)."""

    def test_all_planted_rings_covered(self, rings_tiny):
        eco, _, rings = rings_tiny
        for plant in eco.plants:
            if plant.archetype not in ARCHETYPES:
                continue  # hard negatives are not recall targets
            hits = [r for r in rings if set(plant.users) <= set(r.users)]
            assert hits, f"planted ring {plant.archetype} not covered by any candidate"

    def test_abuse_rings_scored_above_household(self, rings_tiny):
        """Hard-negative sanity: household sharing must not out-rank abuse."""
        eco, _, rings = rings_tiny
        hh = next(p for p in eco.plants if p.archetype not in ARCHETYPES)
        hh_ring = next(r for r in rings if set(hh.users) <= set(r.users))
        abuse = [
            r for r in rings
            if any(p.archetype in ARCHETYPES and set(p.users) <= set(r.users)
                   for p in eco.plants)
        ]
        assert hh_ring.structural_score < max(r.structural_score for r in abuse)

    def test_primary_pattern_reflects_archetype(self, rings_tiny):
        eco, _, rings = rings_tiny
        for plant in eco.plants:
            if plant.archetype not in ARCHETYPES:
                continue
            ring = next(r for r in rings if set(plant.users) <= set(r.users))
            if plant.archetype == "A":  # device farm
                assert "device" in ring.primary_pattern
            elif plant.archetype == "B":  # payment-instrument sharing
                assert "payment" in ring.primary_pattern


class TestDeterminism:
    def test_same_seed_same_rings(self):
        sig = []
        for _ in range(2):
            eco = build_ecosystem(tiny_config(), seed=7)
            G = build_graph(eco)
            sig.append([(r.ring_id, r.users, r.structural_score) for r in discover_rings(G)])
        assert sig[0] == sig[1]


class TestCausalAsOf:
    """Discovery must only see events up to `as_of` (leakage prevention)."""

    def test_emerging_ring_grows_over_time(self, rings_tiny):
        eco, _, _ = rings_tiny
        plant = next(p for p in eco.plants if p.archetype == "H")
        G_full = build_graph(eco)
        created = sorted(G_full.nodes[u]["created_at"] for u in plant.users)
        early = created[len(created) // 2] - 1  # before the later accounts exist

        G_early = build_graph(eco, as_of=early)
        early_hits = [r for r in discover_rings(G_early) if set(plant.users) <= set(r.users)]
        full_hits = [r for r in discover_rings(G_full) if set(plant.users) <= set(r.users)]

        assert full_hits, "full-graph discovery must cover the emerging ring"
        assert not early_hits, (
            "emerging ring must NOT be fully covered before its later accounts exist"
        )

    def test_no_future_edges_leak(self, rings_tiny):
        eco, G, _ = rings_tiny
        ts = sorted(d["timestamp"] for _u, _v, d in G.edges(data=True) if "timestamp" in d)
        mid = ts[len(ts) // 2]
        G_mid = build_graph(eco, as_of=mid)
        assert all(d["timestamp"] <= mid for _u, _v, d in G_mid.edges(data=True)
                   if "timestamp" in d)


class TestFilters:
    def test_min_users_filter(self, rings_tiny):
        _, G, _ = rings_tiny
        assert discover_rings(G, min_users=10_000) == []
        assert all(isinstance(r, Ring) for r in discover_rings(G, min_users=4))


@pytest.fixture(scope="module")
def rings_demo():
    """Demo-scale regression fixture: tiny passes must not hide scale bugs."""
    eco = build_ecosystem(demo_config(), seed=42)
    G = build_graph(eco)
    return eco, discover_rings(G)


class TestDemoScale:
    """Bugs that only appear at spec §46 demo scale (regression guard)."""

    def test_all_planted_rings_covered_at_demo_scale(self, rings_demo):
        eco, rings = rings_demo
        for plant in eco.plants:
            if plant.archetype not in ARCHETYPES:
                continue
            hits = [r for r in rings if set(plant.users) <= set(r.users)]
            assert hits, f"planted ring {plant.archetype} not covered at demo scale"

    def test_no_background_mega_component(self, rings_demo):
        """The market-pool projection must not collapse into one blob."""
        _, rings = rings_demo
        assert max(r.size for r in rings) <= 20, "background blob re-appeared"

    def test_abuse_communities_rank_above_hard_negatives(self, rings_demo):
        eco, rings = rings_demo
        hn_users = {
            u for p in eco.plants if p.archetype not in ARCHETYPES for u in p.users
        }
        top3 = rings[:3]
        for r in top3:
            overlap = len(set(r.users) & hn_users) / len(r.users)
            assert overlap < 0.5, f"top-ranked candidate {r.ring_id} is mostly hard-negative"

    def test_deterministic_at_demo_scale(self, rings_demo):
        eco, rings = rings_demo
        again = discover_rings(build_graph(eco))
        assert [(r.ring_id, r.users, r.structural_score) for r in rings] == [
            (r.ring_id, r.users, r.structural_score) for r in again
        ]
