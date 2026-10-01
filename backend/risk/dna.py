"""Stable, evidence-derived Ring DNA summaries."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.detection.rings import Ring


def ring_dna(ring: Ring) -> dict[str, Any]:
    """Return a reproducible signature made only from computed evidence."""
    risk_signals = {
        item["signal"]: item["value"] for item in ring.risk_signals
    }
    legitimate_signals = {
        item["signal"]: item["value"] for item in ring.legitimate_signals
    }
    payload = {
        "size": len(ring.users),
        "primary_pattern": ring.primary_pattern,
        "structural_score": ring.structural_score,
        "risk_score": ring.risk_score,
        "risk_signals": risk_signals,
        "legitimate_signals": legitimate_signals,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        **payload,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
        "dominant_drivers": [row["layer"] for row in ring.drivers[:3]],
    }
