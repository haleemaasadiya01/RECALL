"""FastAPI router – incident ingest, diagnose, patterns, compare."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
import json

from app.models.schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentBatch,
    ChangeEventCreate,
    DiagnoseRequest,
    DiagnoseResponse,
    FeedbackSubmit,
    PatternsRequest,
    PatternsResponse,
    CompareRequest,
    CompareResponse,
    HealthResponse,
)
from app.services import memory_service, agent
from app.config import get_settings
from app.utils.logging_utils import get_logger

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


# ─── Health ───────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Liveness / readiness probe."""
    hindsight_ok = False
    if settings.is_hindsight_configured():
        try:
            client = memory_service.get_hindsight()
            if client:
                await client.aget_version()
                hindsight_ok = True
        except Exception:
            hindsight_ok = False

    return HealthResponse(
        status="ok",
        hindsight_connected=hindsight_ok,
        groq_configured=settings.is_groq_configured(),
        bank_id=settings.HINDSIGHT_BANK_ID,
    )


# ─── Ingest ───────────────────────────────────────────────────────────────────


@router.post("/incidents", response_model=IncidentResponse, tags=["Ingest"])
async def create_incident(incident: IncidentCreate) -> IncidentResponse:
    """Retain a single incident into Hindsight memory."""
    try:
        result = await memory_service.retain_incident(incident)
        return IncidentResponse(
            success=result.get("success", False),
            memory_id=result.get("memory_id"),
            bank_id=result.get("bank_id", settings.HINDSIGHT_BANK_ID),
            message=result.get("message", "Unknown error"),
        )
    except Exception as exc:
        logger.error("create_incident error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/incidents/batch", tags=["Ingest"])
async def create_incidents_batch(batch: IncidentBatch) -> dict:
    """Retain multiple incidents at once."""
    results = []
    for incident in batch.incidents:
        r = await memory_service.retain_incident(incident)
        results.append(r)
    success_count = sum(1 for r in results if r.get("success"))
    return {
        "total": len(results),
        "succeeded": success_count,
        "failed": len(results) - success_count,
        "results": results,
    }


@router.post("/incidents/upload", tags=["Ingest"])
async def upload_incidents_json(file: UploadFile = File(...)) -> dict:
    """Upload a JSON file containing incidents for bulk ingest."""
    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    incidents_raw = data if isinstance(data, list) else data.get("incidents", [])
    results = []
    for raw in incidents_raw:
        try:
            incident = IncidentCreate(**raw)
            r = await memory_service.retain_incident(incident)
            results.append(r)
        except Exception as exc:
            results.append({"success": False, "message": str(exc)})

    success_count = sum(1 for r in results if r.get("success"))
    return {"total": len(results), "succeeded": success_count, "results": results}


@router.post("/changes", tags=["Ingest"])
async def create_change_event(event: ChangeEventCreate) -> dict:
    """Retain an infrastructure/config change event."""
    result = await memory_service.retain_change_event(event)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))
    return result


# ─── Diagnose ─────────────────────────────────────────────────────────────────


@router.post("/diagnose", response_model=DiagnoseResponse, tags=["Agent"])
async def diagnose_incident(request: DiagnoseRequest) -> DiagnoseResponse:
    """
    Diagnose an incident with or without Hindsight memory.

    Returns structured analysis: root cause, fix recommendation,
    past occurrences, precursors, and confidence level.
    """
    try:
        return await agent.diagnose(
            query=request.query,
            service_filter=request.service_filter,
            with_memory=request.with_memory,
        )
    except Exception as exc:
        logger.error("diagnose endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/compare", response_model=CompareResponse, tags=["Agent"])
async def compare_with_without_memory(request: CompareRequest) -> CompareResponse:
    """
    Side-by-side: run the same query without memory AND with memory.
    This is the before/after demo view.
    """
    try:
        without = await agent.diagnose(query=request.query, with_memory=False)
        with_mem = await agent.diagnose(query=request.query, with_memory=True)
        return CompareResponse(without_memory=without, with_memory=with_mem)
    except Exception as exc:
        logger.error("compare endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Feedback ─────────────────────────────────────────────────────────────────


@router.post("/feedback", tags=["Learning"])
async def submit_feedback(feedback: FeedbackSubmit) -> dict:
    """Submit post-incident feedback to reinforce learning."""
    result = await memory_service.retain_feedback(
        incident_title=feedback.incident_title,
        fix_worked=feedback.fix_worked,
        actual_root_cause=feedback.actual_root_cause,
        notes=feedback.notes,
        fix_style=feedback.fix_style.value,
    )
    return result


# ─── Patterns ─────────────────────────────────────────────────────────────────


@router.post("/patterns", response_model=PatternsResponse, tags=["Insights"])
async def get_patterns(request: PatternsRequest) -> PatternsResponse:
    """
    Use Hindsight's reflect capability to surface recurring root causes,
    riskiest services, and common precursors.
    """
    query = (
        "Analyse all stored incidents and change events. "
        "Surface: (1) top recurring root causes with frequency, "
        "(2) riskiest services by incident count and severity, "
        "(3) common precursor patterns (change event → incident), "
        "(4) team fix preferences (quick patch vs proper fix ratio), "
        "(5) prevention recommendations. Use headers, bullet points, and tables."
    )
    return await memory_service.reflect_patterns(query=query, tags=request.tags)


@router.get("/patterns/services", tags=["Insights"])
async def get_service_patterns() -> PatternsResponse:
    """Reflect on per-service incident patterns."""
    return await memory_service.reflect_patterns(
        query="Which services have the most incidents? Show breakdown by severity and root cause.",
        tags=None,
    )
