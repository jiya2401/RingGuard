"""Deterministic, fully grounded investigation assistant (M14)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.agents.tools import ToolRegistry


class CopilotQuery(BaseModel):
    ring_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2_000)


class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict[str, Any]
    provenance: list[str]


class CopilotAnswer(BaseModel):
    ring_id: str
    answer: str
    tool_calls: list[ToolCallRecord]
    evidence: dict[str, Any]
    mode: str = "deterministic-grounded"
    data_label: str = "SYNTHETIC / SIMULATED DATA"


class DeterministicCopilot:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def answer(self, query: CopilotQuery) -> CopilotAnswer:
        text = query.question.lower()
        if any(word in text for word in ("legitimate", "household", "not fraud")):
            names = ["get_legitimate_sharing_evidence", "get_ring_details"]
        elif any(word in text for word in ("changed", "history", "emerging", "when")):
            names = ["get_risk_history", "get_ring_details"]
        elif any(word in text for word in ("blast", "affected", "exposure")):
            names = ["calculate_blast_radius", "get_ring_details"]
        elif any(word in text for word in ("without", "counterfactual", "remove")):
            names = ["get_counterfactuals", "get_ring_details"]
        elif any(word in text for word in ("baseline", "model", "compare")):
            names = ["compare_with_baseline", "get_ring_details"]
        else:
            names = ["get_ring_details", "get_legitimate_sharing_evidence"]

        calls: list[ToolCallRecord] = []
        evidence: dict[str, Any] = {}
        for name in names:
            arguments = {"ring_id": query.ring_id}
            result = self.registry.invoke(name, arguments)
            calls.append(
                ToolCallRecord(
                    tool=name,
                    arguments=arguments,
                    provenance=result.provenance,
                )
            )
            evidence[name] = result.data
        return CopilotAnswer(
            ring_id=query.ring_id,
            answer=self._render(names[0], evidence[names[0]], evidence),
            tool_calls=calls,
            evidence=evidence,
        )

    @staticmethod
    def _render(primary: str, data: dict[str, Any], all_evidence: dict[str, Any]) -> str:
        details = all_evidence.get("get_ring_details", {})
        if primary == "get_legitimate_sharing_evidence":
            flagged = data["why_flagged"]
            counter = data["why_not_fraud"]
            return (
                f"{flagged['ring_id']} scores {flagged['risk_score']} with "
                f"{flagged['confidence']} confidence. Its primary pattern is "
                f"{flagged['primary_pattern']}. Counter-evidence is "
                f"{counter['verdict']} (legitimacy score "
                f"{counter['legitimacy_score']}); {counter['summary']}."
            )
        if primary == "get_risk_history":
            history = data["history"]
            first, last = history[0], history[-1]
            return (
                f"{data['ring_id']} moved from risk {first['risk']} on day "
                f"{first['day']} to {last['risk']} on day {last['day']}. "
                f"The latest grounded changes are: "
                f"{'; '.join(last['what_changed']) or 'no new structural change at the final checkpoint'}."
            )
        if primary == "calculate_blast_radius":
            return (
                f"{data['ring_id']} reaches {data['counts']['users']} users within "
                f"{data['max_hops']} hops. Observed simulated transaction exposure "
                f"across those users is INR {data['estimated_simulated_exposure']:.2f}."
            )
        if primary == "get_counterfactuals":
            rows = data["counterfactuals"]
            if not rows:
                return f"{data['ring_id']} has no shared evidence eligible for removal."
            strongest = min(rows, key=lambda row: row["risk_delta"])
            return (
                f"Removing {strongest['entity_type']} {strongest['evidence_id']} and "
                f"recomputing the graph changes risk from {strongest['before_risk']} "
                f"to {strongest['after_risk']} ({strongest['risk_delta']:+d})."
            )
        if primary == "compare_with_baseline":
            if not data.get("available"):
                return "The reproducible evaluation report is not available yet."
            selected = data["selected_graph_model"]
            metrics = data["models"][selected]["test"]
            return (
                f"The selected graph model is {selected}; on the saved synthetic "
                f"test split it measured F1 {metrics['f1']} and PR-AUC "
                f"{metrics['pr_auc']}."
            )
        return (
            f"{data['ring_id']} scores {data['risk_score']} with "
            f"{data['confidence']} confidence. Pattern: {data['primary_pattern']}. "
            f"Recommended action: {data['recommended_action']}."
        )
