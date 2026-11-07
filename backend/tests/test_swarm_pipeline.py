"""Tests for the swarm scenario generator, evasions, identity resolution and pipeline."""

from __future__ import annotations

from backend.swarm.evasion import drop_events, rename_agents, tamper_agents
from backend.swarm.evaluate import group_rows
from backend.swarm.identity import apply_aliases, resolve_by_fingerprint
from backend.swarm.scenarios import generate_scenario


def test_scenarios_are_deterministic_and_labeled():
    a, b = generate_scenario(7), generate_scenario(7)
    assert [(e.ts, e.agent, e.target) for e in a.events] == [(e.ts, e.agent, e.target) for e in b.events]
    kinds = {k for k, _ in a.truth.values()}
    assert kinds == {"independent", "sanctioned", "covert"}


def test_pipeline_finds_planted_groups_and_policy_feature_separates_them():
    sc = generate_scenario(3)
    rows = group_rows(sc.events, sc, seed=3)
    assert all(r.found for r in rows)
    cov = [r.feats["unsanc_share"] for r in rows if r.kind == "covert"]
    san = [r.feats["unsanc_share"] for r in rows if r.kind == "sanctioned"]
    assert min(cov) > max(san)


def test_evasions_change_logs_as_expected():
    sc = generate_scenario(5)
    assert len(drop_events(sc.events, 0.5, 1)) < len(sc.events)
    assert len({e.agent for e in tamper_agents(sc.events, 0.3, 1)}) < len({e.agent for e in sc.events})
    renamed, alias_of = rename_agents(sc.events, 6.6, 1)
    assert len({e.agent for e in renamed}) > len({e.agent for e in sc.events})
    assert set(alias_of.values()) >= {e.agent for e in sc.events}


def test_fingerprint_resolution_recovers_true_agents_at_full_coverage():
    sc = generate_scenario(5)
    renamed, alias_of = rename_agents(sc.events, 6.6, 1)
    mapping = resolve_by_fingerprint(renamed, 1.0, 1)
    merged = apply_aliases(renamed, mapping)
    assert len({e.agent for e in merged}) == len({e.agent for e in sc.events}) 