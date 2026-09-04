"""Generate the deterministic demo dataset and persist it for the API/dashboard.

Usage:
    python scripts/generate_demo.py [--seed 42] [--out data/ecosystem.json]

Writes a canonical JSON snapshot of the ecosystem and prints a manifest.
The digest acts as a reproducibility fingerprint: identical inputs -> same file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running as `python scripts/generate_demo.py` from anywhere in the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.data.config import demo_config
from backend.data.generator import build_ecosystem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="data/ecosystem.json")
    args = parser.parse_args()

    cfg = demo_config(seed=args.seed)
    t0 = time.perf_counter()
    eco = build_ecosystem(cfg, seed=args.seed)
    elapsed = time.perf_counter() - t0

    manifest = eco.manifest()
    print("=== RingGuard demo ecosystem ===")
    print(f"build time            : {elapsed:.2f}s")
    print(f"transactions          : {manifest['n_payments']:,}")
    print(f"users                 : {manifest['entities']['USER']:,}")
    print(f"entities (total)      : {sum(manifest['entities'].values()):,}")
    print(f"abuse rings planted   : {manifest['n_plants']}")
    print(f"  non-emerging        : {manifest['profile']['n_abuse_rings']}")
    print(f"  hard negatives      : {manifest['profile']['n_hard_negative_communities']}")
    print(f"emerging rings        : {len(manifest['profile']['emerging_rings'])}")
    print("archetype users / txns :")
    for k in sorted(manifest["archetype_users"]):
        print(f"  {k}: {manifest['archetype_users'][k]} users / {manifest['archetype_txns'].get(k, 0)} txns")
    print("community users        :")
    for k in sorted(manifest["community_users"]):
        print(f"  {k}: {manifest['community_users'][k]}")
    print(f"total simulated value : Rs {manifest['total_value']:,.2f} (SIMULATED)")
    print(f"digest                : {eco.digest()[:24]}...")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": eco.seed,
        "profile": eco.profile,
        "plants": [p.to_dict() for p in eco.plants],
        "digest": eco.digest(),
        "entities": {
            t: [e.to_dict() for e in es] for t, es in eco.entities.items()
        },
        "payments": [p.to_dict() for p in eco.payments],
    }
    out.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
    print(f"written to            : {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()