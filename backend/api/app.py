"""RingGuard FastAPI application factory (M15)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import backend
from backend.agents.copilot import CopilotQuery, DeterministicCopilot
from backend.agents.tools import build_registry
from backend.api.schemas import (
    CopilotRequest,
    GraphResponse,
    HealthResponse,
    InvestigationActionRequest,
    OverviewResponse,
    RiskQueueResponse,
    SimulationRequest,
)
from backend.api.service import RingGuardService
from backend.simulation.engine import SimulationControls
from config.settings import settings


def _get_service(request: Request) -> RingGuardService:
    if request.app.state.service is None:
        settings.ensure_directories()
        request.app.state.service = RingGuardService(db_path=settings.db_path)
    return request.app.state.service


ServiceDependency = Annotated[RingGuardService, Depends(_get_service)]


def create_app(service: RingGuardService | None = None) -> FastAPI:
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=settings.api_description,
    )
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def missing_handler(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc).strip("'")})

    @app.exception_handler(ValueError)
    async def value_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(version=backend.__version__)

    @app.get("/overview", response_model=OverviewResponse, tags=["risk"])
    def overview(svc: ServiceDependency) -> dict[str, Any]:
        return svc.overview()

    @app.get("/risks", response_model=RiskQueueResponse, tags=["risk"])
    def risks(
        svc: ServiceDependency,
        search: str = "",
        min_risk: int = Query(default=0, ge=0, le=100),
        action: str | None = None,
        sort: Literal["risk_desc", "risk_asc", "size_desc"] = "risk_desc",
    ) -> dict[str, Any]:
        rows = svc.risk_queue()
        if search:
            needle = search.lower()
            rows = [
                row
                for row in rows
                if needle in row["ring_id"].lower()
                or needle in row["primary_pattern"].lower()
                or any(needle in user.lower() for user in row["users"])
            ]
        rows = [row for row in rows if (row["risk_score"] or 0) >= min_risk]
        if action:
            rows = [row for row in rows if row["recommended_action"] == action.upper()]
        if sort == "risk_asc":
            rows.sort(key=lambda row: ((row["risk_score"] or 0), row["ring_id"]))
        elif sort == "size_desc":
            rows.sort(key=lambda row: (-row["size"], row["ring_id"]))
        return {"total": len(rows), "rings": rows}

    @app.get("/rings", response_model=RiskQueueResponse, tags=["risk"])
    def rings(svc: ServiceDependency) -> dict[str, Any]:
        rows = svc.risk_queue()
        return {"total": len(rows), "rings": rows}

    @app.get("/rings/{ring_id}", tags=["investigation"])
    def ring_details(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.ring(ring_id).to_dict()

    @app.get("/rings/{ring_id}/graph", response_model=GraphResponse, tags=["investigation"])
    def graph(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.graph_payload(ring_id)

    @app.get("/rings/{ring_id}/timeline", tags=["investigation"])
    def timeline(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.timeline(ring_id)

    @app.get("/rings/{ring_id}/evidence", tags=["investigation"])
    def evidence(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.evidence(ring_id)

    @app.get("/rings/{ring_id}/history", tags=["investigation"])
    def history(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.history(ring_id)

    @app.get("/rings/{ring_id}/blast-radius", tags=["investigation"])
    def blast_radius(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.blast_radius(ring_id)

    @app.get("/rings/{ring_id}/counterfactual", tags=["investigation"])
    def counterfactual(ring_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.counterfactuals(ring_id)

    @app.get("/users/{user_id}", tags=["investigation"])
    def user_profile(user_id: str, svc: ServiceDependency) -> dict[str, Any]:
        return svc.user_profile(user_id)

    @app.get("/tools", tags=["copilot"])
    def tools(svc: ServiceDependency) -> list[dict[str, Any]]:
        return [item.model_dump() for item in build_registry(svc).descriptions()]

    @app.post("/copilot/query", tags=["copilot"])
    def copilot(body: CopilotRequest, svc: ServiceDependency) -> dict[str, Any]:
        assistant = DeterministicCopilot(build_registry(svc))
        return assistant.answer(
            CopilotQuery(ring_id=body.ring_id, question=body.question)
        ).model_dump()

    @app.post("/simulation/start", tags=["simulation"])
    def simulation_start(body: SimulationRequest, svc: ServiceDependency) -> dict[str, Any]:
        return svc.start_simulation(SimulationControls(**body.model_dump()))

    @app.post("/simulation/step", tags=["simulation"])
    def simulation_step(svc: ServiceDependency) -> dict[str, Any]:
        return svc.step_simulation()

    @app.post("/investigation/action", tags=["investigation"])
    def investigation_action(
        body: InvestigationActionRequest, svc: ServiceDependency
    ) -> dict[str, Any]:
        return svc.record_action(body.ring_id, body.action, body.note)

    @app.get("/investigation/actions", tags=["investigation"])
    def investigation_actions(
        svc: ServiceDependency, ring_id: str | None = None
    ) -> dict[str, Any]:
        return {"actions": svc.actions(ring_id)}

    return app

app = create_app()
