"""Run RingGuard's reproducible evaluation and save actual metrics as JSON.

Usage:
    python scripts/run_evaluation.py [--seed 42] [--out docs/evaluation_results.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.data.config import demo_config
from backend.data.generator import build_ecosystem
from backend.evaluation.metrics import evaluate_ecosystem


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="docs/evaluation_results.json")
    parser.add_argument(
        "--skip-emerging",
        action="store_true",
        help="Skip the slower causal emerging-ring replay.",
    )
    args = parser.parse_args()

    ecosystem = build_ecosystem(demo_config(seed=args.seed), seed=args.seed)
    report = evaluate_ecosystem(
        ecosystem, include_emerging=not args.skip_emerging
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"written to: {out}")


if __name__ == "__main__":
    main()
