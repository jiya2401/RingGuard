"""Hard-negative benchmark (spec §6, §39): false-positive awareness.

A RingGuard claim that matters is *shared infrastructure != abuse*.
This module scores that claim directly: for every planted abuse ring
and every planted hard-negative community (household, office, campus,
business, family card) it finds the best-matching discovered ring and
reports, per action threshold, the abuse detection rate against the
hard-negative false-positive rate — the operating trade-off a risk
team actually chooses on.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from backend.data.model import ARCHETYPES
from backend.detection.rings import Ring

DEFAULT_THRESHOLDS = (65, 45, 25)


def _best_ring_for_plant(plant_users: list[str], rings: list[Ring]) -> Ring | None:
    """Highest-risk discovered ring fully containing the plant's users."""
    want = set(plant_users)
    hits = [r for r in rings if want <= set(r.users)]
    return max(hits, key=lambda r: r.risk_score) if hits else None


def _plant_risk_rows(eco: Any, rings: list[Ring]) -> tuple[list[dict], list[dict]]:
    """One row per planted community: archetype, best ring, its risk."""
    abuse, hard_neg = [], []
    for p in eco.plants:
        ring = _best_ring_for_plant(p.users, rings)
        row = {
            "plant_id": p.ring_id,
            "archetype": p.archetype,
            "ring_id": ring.ring_id if ring else None,
            "risk_score": ring.risk_score if ring else None,
            "recommended_action": ring.recommended_action if ring else None,
        }
        (abuse if p.archetype in ARCHETYPES else hard_neg).append(row)
    return abuse, hard_neg


def benchmark_hard_negatives(
    eco: Any,
    G: nx.MultiDiGraph,  # noqa: ARG001 — kept for API symmetry (per-plant re-scoring later)
    rings: list[Ring],
    thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Plant-level abuse TPR vs hard-negative FPR at each risk threshold.

    Ring-level matching keeps this honest: a hard negative only counts
    as a false positive when a discovered ring that *contains the whole
    legitimate community* scores at or above the threshold.
    """
    abuse, hard_neg = _plant_risk_rows(eco, rings)
    abuse_risks = [r["risk_score"] for r in abuse if r["risk_score"] is not None]
    hn_risks = [r["risk_score"] for r in hard_neg if r["risk_score"] is not None]

    per_threshold = {}
    for t in thresholds:
        per_threshold[t] = {
            "abuse_detection_rate": (
                round(sum(x >= t for x in abuse_risks) / len(abuse_risks), 3)
                if abuse_risks
                else 0.0
            ),
            "hard_negative_fpr": (
                round(sum(x >= t for x in hn_risks) / len(hn_risks), 3)
                if hn_risks
                else 0.0
            ),
        }

    abuse_mean = sum(abuse_risks) / len(abuse_risks) if abuse_risks else 0.0
    hn_mean = sum(hn_risks) / len(hn_risks) if hn_risks else 0.0
    return {
        "abuse_plants": abuse,
        "hard_negative_plants": hard_neg,
        "abuse_risk_scores": abuse_risks,
        "hard_negative_risk_scores": hn_risks,
        "mean_abuse_risk": round(abuse_mean, 1),
        "mean_hard_negative_risk": round(hn_mean, 1),
        "separation": round(abuse_mean - hn_mean, 1),
        "per_threshold": per_threshold,
    }


def false_positive_rate(rings: list[Ring], threshold: int = 45) -> float:
    """Share of discovered rings scoring >= `threshold` (queue-noise proxy)."""
    if not rings:
        return 0.0
    return round(sum(r.risk_score >= threshold for r in rings) / len(rings), 3)
