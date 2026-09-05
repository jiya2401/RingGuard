"""Grounded explanation renderers (spec §24, §25).

WHY FLAGGED and WHY NOT FRAUD are assembled exclusively from values the
risk engine already computed — ring drivers, layer signals and the
structured legitimate-sharing evidence from
`backend/risk/legitimacy.py`. Nothing here inspects new data and nothing
fabricates: every bullet quotes a computed quantity, so the narrative
can never disagree with the score.
"""

from __future__ import annotations

from typing import Any

from backend.detection.rings import Ring
from backend.risk.legitimacy import evidence_from_ring, summarize_legitimacy

_TOP_SIGNALS = 4  # evidence bullets shown per block


def why_flagged(ring: Ring) -> dict[str, Any]:
    """Structured WHY FLAGGED block for an already-scored ring (spec §24)."""
    if not ring.drivers:
        raise ValueError(f"{ring.ring_id} has not been scored (no drivers)")
    signals = sorted(ring.risk_signals, key=lambda s: s["value"], reverse=True)
    return {
        "ring_id": ring.ring_id,
        "risk_score": ring.risk_score,
        "confidence": ring.confidence,
        "primary_pattern": ring.primary_pattern,
        "primary_drivers": [
            {
                "layer": d["layer"],
                "contribution": d["contribution"],
                "explanation": d["detail"],
            }
            for d in ring.drivers
        ],
        "evidence": [
            {
                "signal": s["signal"],
                "value": s["value"],
                "explanation": s["interpretation"],
            }
            for s in signals[:_TOP_SIGNALS]
        ],
        "recommended_action": ring.recommended_action,
    }


def why_not_fraud(
    ring: Ring, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Structured counter-evidence block (spec §25).

    `evidence` should be the dict produced by
    `backend.risk.legitimacy.collect_legitimate_evidence` for this ring —
    the same object the engine deducted from the score, so the counter-
    argument is provably the one that was weighed. When omitted, the
    evidence is rebuilt from the signals stored on the ring, so queued
    or serialized rings stay explainable without the graph.
    """
    if evidence is None:
        evidence = evidence_from_ring(ring)
    factors = list(evidence.get("factors", []))
    details = evidence.get("details", {})
    checked = [f["signal"] for f in factors]
    return {
        "ring_id": ring.ring_id,
        "verdict": evidence.get("verdict", "NONE"),
        "legitimacy_score": evidence.get("score", 0.0),
        "summary": summarize_legitimacy(evidence),
        "counter_evidence": [
            {
                "signal": f["signal"],
                "value": f["value"],
                "explanation": f["interpretation"],
            }
            for f in factors
        ],
        "what_was_checked": checked,
        "details": details,
        "reading": (
            "Shared infrastructure alone is not abuse; these lawful-sharing "
            "signals were subtracted from the raw risk before the final score."
        ),
    }


def explain_ring(
    ring: Ring, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Both blocks in one payload — the investigation-page explanation."""
    return {
        "why_flagged": why_flagged(ring),
        "why_not_fraud": why_not_fraud(ring, evidence),
    }
