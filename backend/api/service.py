"""Shared in-process application service backed by the real RingGuard pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from backend.data.config import GeneratorConfig, demo_config
from backend.data.generator import build_ecosystem
from backend.data.model import Ecosystem
from backend.data.storage import InvestigationStore
from backend.detection.rings import Ring, discover_rings
from backend.explanations.why import explain_ring
from backend.graph.builder import build_graph, graph_stats
from backend.graph.schema import USER_SENT_TO_USER, USER_USED_DEVICE
from backend.risk.counterfactual import shared_evidence_counterfactuals
from backend.risk.dna import ring_dna
from backend.risk.emerging import DAY_S, graph_t0, risk_history
from backend.risk.engine import score_rings
from backend.risk.legitimacy import collect_legitimate_evidence
from backend.risk.propagation import calculate_blast_radius
from backend.simulation.engine import AttackSimulator, SimulationControls


class RingGuardService:
    """A deterministic snapshot used by tools, API routes, and the UI."""

    def __init__(
        self,
        ecosystem: Ecosystem | None = None,
        *,
        config: GeneratorConfig | None = None,
        seed: int = 42,
        db_path: str | Path = ":memory:",
    ) -> None:
        self.ecosystem = ecosystem or build_ecosystem(
            config or demo_config(seed=seed), seed=seed
        )
        self.graph = build_graph(self.ecosystem)
        self.rings: list[Ring] = []
        self._rings: dict[str, Ring] = {}
        self._refresh_scores()
        self.store = InvestigationStore(db_path)
        self.simulator = AttackSimulator(self.graph)

    def _refresh_scores(self) -> None:
        self.rings = score_rings(discover_rings(self.graph), self.graph)
        self._rings = {ring.ring_id: ring for ring in self.rings}

    def ring(self, ring_id: str) -> Ring:
        try:
            return self._rings[ring_id]
        except KeyError as exc:
            raise KeyError(f"unknown ring: {ring_id}") from exc

    def overview(self) -> dict[str, Any]:
        stats = graph_stats(self.graph)
        active = [ring for ring in self.rings if (ring.risk_score or 0) >= 25]
        high = [ring for ring in self.rings if (ring.risk_score or 0) >= 65]
        return {
            "data_label": "SYNTHETIC / SIMULATED DATA",
            "seed": self.ecosystem.seed,
            "transactions": int(stats["node_types"].get("TRANSACTION", 0)),
            "entities": stats["nodes"],
            "relationships": stats["edges"],
            "candidate_rings": len(self.rings),
            "active_risks": len(active),
            "high_risks": len(high),
            "simulated_value": round(
                sum(
                    float(data.get("amount", 0.0))
                    for _node, data in self.graph.nodes(data=True)
                    if data.get("entity_type") == "TRANSACTION"
                ),
                2,
            ),
        }

    def risk_queue(self) -> list[dict[str, Any]]:
        return [
            {**ring.to_dict(), "dna": ring_dna(ring)}
            for ring in sorted(
                self.rings,
                key=lambda item: (-(item.risk_score or 0), item.ring_id),
            )
        ]

    def graph_payload(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        selected = set(ring.users)
        for values in ring.affected_entities.values():
            selected.update(values)
        nodes = [
            {"data": {"id": node, **dict(self.graph.nodes[node])}}
            for node in sorted(selected)
            if node in self.graph
        ]
        edges = []
        for index, (source, target, key, data) in enumerate(
            sorted(
                self.graph.edges(keys=True, data=True),
                key=lambda row: (row[0], row[1], str(row[2])),
            )
        ):
            if source in selected and target in selected:
                edges.append(
                    {
                        "data": {
                            "id": f"e-{index}",
                            "source": source,
                            "target": target,
                            **dict(data),
                        }
                    }
                )
        return {
            "ring_id": ring_id,
            "nodes": nodes,
            "edges": edges,
            "data_label": "SYNTHETIC DATA",
        }

    def timeline(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        return {"ring_id": ring_id, "events": ring.timeline}

    def evidence(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        evidence = collect_legitimate_evidence(self.graph, set(ring.users))
        return explain_ring(ring, evidence)

    def history(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        start = graph_t0(self.graph)
        days = (2, 6, 10, 14, 18, 22, 26, 30)
        return {
            "ring_id": ring_id,
            "history": risk_history(
                self.graph,
                ring.users,
                [start + day * DAY_S for day in days],
                t0=start,
            ),
        }

    def blast_radius(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        return {
            "ring_id": ring_id,
            **calculate_blast_radius(self.graph, ring.users, max_hops=2),
        }

    def counterfactuals(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        rows = shared_evidence_counterfactuals(
            self.graph, ring.users, limit=5
        )
        rows.sort(key=lambda row: (row["risk_delta"], row["evidence_id"]))
        return {"ring_id": ring_id, "counterfactuals": rows[:8]}

    def user_profile(self, user_id: str) -> dict[str, Any]:
        if user_id not in self.graph or self.graph.nodes[user_id].get("entity_type") != "USER":
            raise KeyError(f"unknown user: {user_id}")
        return {"user_id": user_id, "attributes": dict(self.graph.nodes[user_id])}

    def connected_entities(self, user_id: str) -> dict[str, Any]:
        self.user_profile(user_id)
        rows: list[dict[str, Any]] = []
        for _source, target, data in self.graph.out_edges(user_id, data=True):
            rows.append(
                {
                    "entity_id": target,
                    "entity_type": self.graph.nodes[target].get("entity_type"),
                    "relation": data.get("rel_type"),
                    "weight": data.get("weight", 1.0),
                }
            )
        return {"user_id": user_id, "entities": sorted(rows, key=lambda r: (r["entity_type"], r["entity_id"]))}

    def shared_entities(self, ring_id: str, entity_type: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        holders: dict[str, set[str]] = {}
        for user in ring.users:
            for _source, target, data in self.graph.out_edges(user, data=True):
                if self.graph.nodes[target].get("entity_type") != entity_type:
                    continue
                if entity_type == "DEVICE" and data.get("rel_type") != USER_USED_DEVICE:
                    continue
                holders.setdefault(target, set()).add(user)
        return {
            "ring_id": ring_id,
            "entity_type": entity_type,
            "shared": [
                {"entity_id": entity, "users": sorted(users)}
                for entity, users in sorted(holders.items())
                if len(users) >= 2
            ],
        }

    def money_flow(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        users = set(ring.users)
        flows = [
            {
                "source": source,
                "target": target,
                "weight": data.get("weight", 1.0),
                "timestamp": data.get("timestamp"),
            }
            for source, target, data in self.graph.edges(data=True)
            if data.get("rel_type") == USER_SENT_TO_USER
            and source in users
            and target in users
        ]
        return {"ring_id": ring_id, "flows": flows}

    def similar_rings(self, ring_id: str) -> dict[str, Any]:
        ring = self.ring(ring_id)
        rows = [
            {
                "ring_id": other.ring_id,
                "primary_pattern": other.primary_pattern,
                "risk_score": other.risk_score,
                "size": other.size,
                "similarity": round(
                    (0.7 if other.primary_pattern == ring.primary_pattern else 0.0)
                    + 0.3 / (1 + abs(other.size - ring.size)),
                    3,
                ),
            }
            for other in self.rings
            if other.ring_id != ring_id
        ]
        return {
            "ring_id": ring_id,
            "similar": sorted(rows, key=lambda row: (-row["similarity"], row["ring_id"]))[:5],
        }

    def baseline_comparison(self) -> dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "docs" / "evaluation_results.json"
        if not path.exists():
            return {"available": False, "reason": "run scripts/run_evaluation.py"}
        report = json.loads(path.read_text(encoding="utf-8"))
        return {
            "available": True,
            "seed": report["seed"],
            "ecosystem_digest": report["ecosystem_digest"],
            "selected_graph_model": report["selected_graph_model"],
            "models": report["models"],
        }

    def start_simulation(self, controls: SimulationControls) -> dict[str, Any]:
        state = self.simulator.start(controls)
        self.graph = self.simulator.graph
        self._refresh_scores()
        return {**state, "alert_triggered": False, "ring": None}

    def step_simulation(self) -> dict[str, Any]:
        state = self.simulator.step()
        self.graph = self.simulator.graph
        self._refresh_scores()
        simulated = set(self.simulator.users)
        candidates = [
            ring for ring in self.rings if simulated & set(ring.users)
        ]
        ring = max(
            candidates,
            key=lambda item: (len(simulated & set(item.users)), item.risk_score or 0),
            default=None,
        )
        return {
            **state,
            "alert_triggered": bool(ring and (ring.risk_score or 0) >= 45),
            "ring": ring.to_dict() if ring else None,
            "blast_radius": self.blast_radius(ring.ring_id) if ring else None,
        }

    def record_action(self, ring_id: str, action: str, note: str = "") -> dict[str, Any]:
        ring = self.ring(ring_id)
        row = self.store.add(ring_id, action, note)
        ring.status = action.upper()
        return {**row, "ring_status": ring.status}

    def actions(self, ring_id: str | None = None) -> list[dict[str, Any]]:
        if ring_id is not None:
            self.ring(ring_id)
        return self.store.list(ring_id)
