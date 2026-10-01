"""M13-M15: typed tools, deterministic copilot, and FastAPI contracts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.agents.copilot import CopilotQuery, DeterministicCopilot
from backend.agents.tools import build_registry
from backend.api.app import create_app
from backend.api.service import RingGuardService
from backend.data.config import tiny_config
from backend.data.generator import build_ecosystem


@pytest.fixture()
def service(tmp_path):
    ecosystem = build_ecosystem(tiny_config(n_transactions=900), seed=7)
    return RingGuardService(ecosystem, db_path=tmp_path / "actions.db")


@pytest.fixture()
def client(service):
    return TestClient(create_app(service))


class TestTypedTools:
    def test_registry_has_every_required_tool(self, service):
        registry = build_registry(service)
        names = {item.name for item in registry.descriptions()}
        assert names == {
            "get_ring_details",
            "get_user_profile",
            "get_connected_entities",
            "get_transaction_timeline",
            "get_shared_devices",
            "get_shared_payment_instruments",
            "get_money_flow",
            "get_risk_features",
            "get_legitimate_sharing_evidence",
            "compare_with_baseline",
            "calculate_blast_radius",
            "get_similar_rings",
            "get_risk_history",
            "get_counterfactuals",
        }
        assert all(item.input_schema for item in registry.descriptions())

    def test_tool_input_is_validated_and_output_has_provenance(self, service):
        registry = build_registry(service)
        ring_id = service.rings[0].ring_id
        result = registry.invoke("get_risk_features", {"ring_id": ring_id})
        assert result.data["risk_score"] == service.ring(ring_id).risk_score
        assert result.provenance
        with pytest.raises(ValidationError):
            registry.invoke("get_ring_details", {"ring_id": ""})

    def test_copilot_is_grounded_and_deterministic(self, service):
        ring_id = service.rings[0].ring_id
        assistant = DeterministicCopilot(build_registry(service))
        query = CopilotQuery(ring_id=ring_id, question="Why was this ring flagged?")
        first = assistant.answer(query)
        second = assistant.answer(query)
        assert first == second
        assert first.tool_calls
        assert first.mode == "deterministic-grounded"
        assert str(service.ring(ring_id).risk_score) in first.answer
        assert first.evidence


class TestApi:
    def test_health_and_overview(self, client, service):
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["external_ai_required"] is False
        overview = client.get("/overview")
        assert overview.status_code == 200
        assert overview.json() == service.overview()
        assert "SYNTHETIC" in overview.json()["data_label"]

    def test_risk_queue_search_sort_and_ring_endpoints(self, client, service):
        queue = client.get("/risks?sort=risk_desc").json()
        assert queue["total"] == len(service.rings)
        scores = [row["risk_score"] for row in queue["rings"]]
        assert scores == sorted(scores, reverse=True)
        ring_id = queue["rings"][0]["ring_id"]
        assert client.get(f"/rings/{ring_id}").status_code == 200
        graph = client.get(f"/rings/{ring_id}/graph").json()
        assert graph["nodes"] and graph["edges"]
        assert client.get(f"/rings/{ring_id}/timeline").json()["events"]
        evidence = client.get(f"/rings/{ring_id}/evidence").json()
        assert set(evidence) == {"why_flagged", "why_not_fraud"}
        assert client.get(f"/rings/{ring_id}/blast-radius").json()["counts"]
        assert client.get(f"/rings/{ring_id}/history").json()["history"]

    def test_not_found_and_copilot(self, client, service):
        assert client.get("/rings/NOPE").status_code == 404
        ring_id = service.rings[0].ring_id
        response = client.post(
            "/copilot/query",
            json={"ring_id": ring_id, "question": "Could this be legitimate?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tool_calls"]
        assert "get_legitimate_sharing_evidence" in body["evidence"]

    def test_investigator_action_persists(self, client, service):
        ring_id = service.rings[0].ring_id
        saved = client.post(
            "/investigation/action",
            json={"ring_id": ring_id, "action": "investigate", "note": "review links"},
        )
        assert saved.status_code == 200
        actions = client.get(
            "/investigation/actions", params={"ring_id": ring_id}
        ).json()["actions"]
        assert actions[-1]["note"] == "review links"
        assert service.ring(ring_id).status == "INVESTIGATE"

    def test_simulator_grows_graph_and_uses_risk_pipeline(self, client):
        started = client.post(
            "/simulation/start",
            json={
                "accounts": 9,
                "shared_devices": 2,
                "shared_instruments": 1,
                "coordinated_transactions": 3,
            },
        ).json()
        nodes = started["nodes"]
        results = []
        for _ in range(3):
            response = client.post("/simulation/step")
            assert response.status_code == 200
            results.append(response.json())
        assert results[0]["nodes"] > nodes
        assert results[-1]["complete"] is True
        assert results[-1]["ring"] is not None
        assert results[-1]["ring"]["risk_score"] >= results[0]["ring"]["risk_score"]
        assert results[-1]["blast_radius"]["data_label"] == "SIMULATED DATA"
