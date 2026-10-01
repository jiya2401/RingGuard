"""End-to-end RingGuard smoke: generate -> detect -> serve -> act -> simulate.

Usage:
    python scripts/e2e_smoke.py          # fast tiny-scale verification
    python scripts/e2e_smoke.py --demo   # full 12k-transaction demo scale
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.app import create_app
from backend.api.service import RingGuardService
from backend.data.config import demo_config, tiny_config
from backend.data.generator import build_ecosystem


def run_smoke(*, demo: bool = False, require_frontend: bool = True) -> dict:
    config = demo_config() if demo else tiny_config(n_transactions=900)
    ecosystem = build_ecosystem(config, seed=config.seed)
    with tempfile.TemporaryDirectory(prefix="ringguard-e2e-") as temp_dir:
        service = RingGuardService(
            ecosystem, db_path=Path(temp_dir) / "actions.db"
        )
        client = TestClient(create_app(service))

        assert client.get("/health").json()["status"] == "ok"
        overview = client.get("/overview").json()
        queue = client.get("/risks?sort=risk_desc").json()
        assert overview["transactions"] == len(ecosystem.payments)
        assert queue["rings"]

        ring_id = queue["rings"][0]["ring_id"]
        graph = client.get(f"/rings/{ring_id}/graph").json()
        evidence = client.get(f"/rings/{ring_id}/evidence").json()
        history = client.get(f"/rings/{ring_id}/history").json()
        blast = client.get(f"/rings/{ring_id}/blast-radius").json()
        counterfactual = client.get(f"/rings/{ring_id}/counterfactual").json()
        copilot = client.post(
            "/copilot/query",
            json={"ring_id": ring_id, "question": "Why was this ring flagged?"},
        ).json()
        assert graph["nodes"] and graph["edges"]
        assert evidence["why_flagged"]["risk_score"] == queue["rings"][0]["risk_score"]
        assert history["history"]
        assert blast["data_label"] == "SIMULATED DATA"
        assert "counterfactuals" in counterfactual
        assert copilot["tool_calls"] and copilot["evidence"]

        action = client.post(
            "/investigation/action",
            json={
                "ring_id": ring_id,
                "action": "investigate",
                "note": "E2E smoke note",
            },
        ).json()
        assert action["ring_status"] == "INVESTIGATE"

        start = client.post(
            "/simulation/start",
            json={
                "accounts": 9,
                "shared_devices": 2,
                "shared_instruments": 1,
                "coordinated_transactions": 3,
            },
        ).json()
        steps = [client.post("/simulation/step").json() for _ in range(3)]
        assert steps[-1]["complete"] is True
        assert steps[-1]["ring"] is not None
        assert steps[-1]["alert_triggered"] is True
        assert steps[-1]["nodes"] > start["nodes"]

        frontend_index = (
            Path(__file__).resolve().parents[1] / "frontend" / "dist" / "index.html"
        )
        if require_frontend:
            assert frontend_index.exists(), "run `pnpm run build` in frontend first"

        return {
            "scale": "demo" if demo else "tiny",
            "digest": ecosystem.digest(),
            "overview": overview,
            "top_ring": ring_id,
            "top_ring_risk": evidence["why_flagged"]["risk_score"],
            "graph_nodes": len(graph["nodes"]),
            "history_points": len(history["history"]),
            "counterfactuals": len(counterfactual["counterfactuals"]),
            "simulated_ring_risk": steps[-1]["ring"]["risk_score"],
            "simulated_alert": steps[-1]["alert_triggered"],
            "investigator_action_id": action["id"],
            "frontend_build_present": frontend_index.exists(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_smoke(demo=args.demo), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
