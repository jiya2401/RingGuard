"""Typed FastAPI request and response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    data_label: str = "SYNTHETIC / SIMULATED DATA"
    external_ai_required: bool = False


class OverviewResponse(BaseModel):
    data_label: str
    seed: int
    transactions: int
    entities: int
    relationships: int
    candidate_rings: int
    active_risks: int
    high_risks: int
    simulated_value: float


class RiskQueueResponse(BaseModel):
    total: int
    rings: list[dict[str, Any]]
    data_label: str = "SYNTHETIC / SIMULATED DATA"


class GraphResponse(BaseModel):
    ring_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    data_label: str


class SimulationRequest(BaseModel):
    accounts: int = Field(default=9, ge=3, le=30)
    shared_devices: int = Field(default=2, ge=1, le=5)
    shared_instruments: int = Field(default=1, ge=1, le=5)
    coordinated_transactions: int = Field(default=3, ge=1, le=10)


class InvestigationActionRequest(BaseModel):
    ring_id: str = Field(min_length=1)
    action: Literal[
        "monitor",
        "investigate",
        "escalate",
        "dismiss",
        "mark_legitimate",
        "confirm_abuse",
    ]
    note: str = Field(default="", max_length=4_000)


class CopilotRequest(BaseModel):
    ring_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2_000)


class GenericResponse(BaseModel):
    data: dict[str, Any]
