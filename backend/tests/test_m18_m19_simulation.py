"""M18-M19: deterministic simulation and persistent investigator feedback."""

from __future__ import annotations

import pytest

from backend.api.service import RingGuardService
from backend.data.config import tiny_config
from backend.data.generator import build_ecosystem
from backend.data.storage import ALLOWED_ACTIONS, InvestigationStore
from backend.graph.builder import build_graph
from backend.simulation.engine import AttackSimulator, SimulationControls


def _ecosystem():
    return build_ecosystem(tiny_config(n_transactions=900), seed=7)


class TestAttackSimulator:
    def test_same_controls_produce_identical_growth(self):
        controls = SimulationControls(
            accounts=9,
            shared_devices=2,
            shared_instruments=1,
            coordinated_transactions=3,
        )
        signatures = []
        for _ in range(2):
            simulator = AttackSimulator(build_graph(_ecosystem()))
            states = [simulator.start(controls)]
            states.extend(simulator.step() for _ in range(3))
            signatures.append(
                (
                    states,
                    sorted(
                        (u, v, str(key), data.get("timestamp"))
                        for u, v, key, data in simulator.graph.edges(
                            keys=True, data=True
                        )
                        if str(u).startswith("SIM-")
                    ),
                )
            )
        assert signatures[0] == signatures[1]

    def test_graph_risk_alert_and_blast_radius_grow(self):
        service = RingGuardService(_ecosystem())
        started = service.start_simulation(SimulationControls())
        outputs = [service.step_simulation() for _ in range(3)]
        assert started["nodes"] < outputs[0]["nodes"] < outputs[-1]["nodes"]
        risks = [output["ring"]["risk_score"] for output in outputs]
        assert risks == sorted(risks)
        blast_users = [output["blast_radius"]["counts"]["users"] for output in outputs]
        assert blast_users == sorted(blast_users)
        assert outputs[-1]["alert_triggered"] is True


class TestInvestigatorPersistence:
    @pytest.mark.parametrize("action", sorted(ALLOWED_ACTIONS))
    def test_every_action_is_accepted(self, tmp_path, action):
        store = InvestigationStore(tmp_path / f"{action}.db")
        saved = store.add("R-001", action, f"note for {action}")
        assert saved["action"] == action
        assert store.list("R-001")[0]["note"] == f"note for {action}"

    def test_actions_survive_a_new_store_instance(self, tmp_path):
        path = tmp_path / "ringguard.db"
        first = InvestigationStore(path)
        first.add("R-001", "monitor", "watch next checkpoint")
        second = InvestigationStore(path)
        assert second.list("R-001") == first.list("R-001")
