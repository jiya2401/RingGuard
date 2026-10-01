"""Typed investigation-tool registry grounded in RingGuard application state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from backend.risk.dna import ring_dna

if TYPE_CHECKING:
    from backend.api.service import RingGuardService


class RingInput(BaseModel):
    ring_id: str = Field(min_length=1)


class UserInput(BaseModel):
    user_id: str = Field(min_length=1)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    data: dict[str, Any]
    provenance: list[str]


class ToolDescription(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class InvestigationTool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]
    provenance: tuple[str, ...]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, InvestigationTool] = {}

    def register(self, tool: InvestigationTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def descriptions(self) -> list[ToolDescription]:
        return [
            ToolDescription(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.values()
        ]

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown investigation tool: {name}") from exc
        inputs = tool.input_model.model_validate(arguments)
        return ToolResult(
            tool=name,
            data=tool.handler(inputs),
            provenance=list(tool.provenance),
        )


def build_registry(service: RingGuardService) -> ToolRegistry:
    registry = ToolRegistry()

    def add(
        name: str,
        description: str,
        model: type[BaseModel],
        handler: Callable[[BaseModel], dict[str, Any]],
        *provenance: str,
    ) -> None:
        registry.register(
            InvestigationTool(
                name, description, model, handler, tuple(provenance)
            )
        )

    add(
        "get_ring_details",
        "Return the scored ring contract and Ring DNA.",
        RingInput,
        lambda value: {
            **service.ring(value.ring_id).to_dict(),
            "dna": ring_dna(service.ring(value.ring_id)),
        },
        "discover_rings",
        "score_rings",
    )
    add(
        "get_user_profile",
        "Return one graph-backed synthetic user profile.",
        UserInput,
        lambda value: service.user_profile(value.user_id),
        "graph node attributes",
    )
    add(
        "get_connected_entities",
        "Return direct graph relationships for a user.",
        UserInput,
        lambda value: service.connected_entities(value.user_id),
        "heterogeneous graph edges",
    )
    add(
        "get_transaction_timeline",
        "Return the computed account/activity timeline for a ring.",
        RingInput,
        lambda value: service.timeline(value.ring_id),
        "ring timeline",
    )
    add(
        "get_shared_devices",
        "Return devices shared by at least two ring users.",
        RingInput,
        lambda value: service.shared_entities(value.ring_id, "DEVICE"),
        "USER_USED_DEVICE edges",
    )
    add(
        "get_shared_payment_instruments",
        "Return shared cards, bank accounts, and UPI handles.",
        RingInput,
        lambda value: {
            "ring_id": value.ring_id,
            "instruments": [
                row
                for entity_type in ("CARD", "BANK_ACCOUNT", "UPI_ID")
                for row in service.shared_entities(value.ring_id, entity_type)["shared"]
            ],
        },
        "ownership and instrument-use graph edges",
    )
    add(
        "get_money_flow",
        "Return internal directed money-flow edges.",
        RingInput,
        lambda value: service.money_flow(value.ring_id),
        "USER_SENT_TO_USER edges",
    )
    add(
        "get_risk_features",
        "Return risk layers, evidence signals, score, and action.",
        RingInput,
        lambda value: {
            "ring_id": value.ring_id,
            "risk_score": service.ring(value.ring_id).risk_score,
            "confidence": service.ring(value.ring_id).confidence,
            "drivers": service.ring(value.ring_id).drivers,
            "signals": service.ring(value.ring_id).risk_signals,
            "recommended_action": service.ring(value.ring_id).recommended_action,
        },
        "multi-layer risk engine",
    )
    add(
        "get_legitimate_sharing_evidence",
        "Return grounded WHY FLAGGED and WHY NOT FRAUD evidence.",
        RingInput,
        lambda value: service.evidence(value.ring_id),
        "risk and legitimate-sharing engines",
    )
    add(
        "compare_with_baseline",
        "Return the saved reproducible baseline comparison.",
        RingInput,
        lambda _value: service.baseline_comparison(),
        "docs/evaluation_results.json",
    )
    add(
        "calculate_blast_radius",
        "Return two-hop impact and simulated exposure.",
        RingInput,
        lambda value: service.blast_radius(value.ring_id),
        "coordination projection",
        "transaction amounts",
    )
    add(
        "get_similar_rings",
        "Return evidence-derived structurally similar candidates.",
        RingInput,
        lambda value: service.similar_rings(value.ring_id),
        "scored ring set",
    )
    add(
        "get_risk_history",
        "Return a causal risk trajectory and grounded deltas.",
        RingInput,
        lambda value: service.history(value.ring_id),
        "causal graph snapshots",
        "risk_history",
    )
    add(
        "get_counterfactuals",
        "Remove shared evidence and recompute risk from scratch.",
        RingInput,
        lambda value: service.counterfactuals(value.ring_id),
        "counterfactual graph recomputation",
    )
    return registry
