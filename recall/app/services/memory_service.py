"""Hindsight memory service – retain, recall, reflect."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from hindsight_client import Hindsight

from app.config import get_settings
from app.models.schemas import (
    ChangeEventCreate,
    IncidentCreate,
    MemoryUsed,
    PatternsResponse,
)
from app.utils.logging_utils import get_logger, redact_secrets

logger = get_logger(__name__)
settings = get_settings()

# ─── Singleton client ─────────────────────────────────────────────────────────

_hindsight_client: Optional[Hindsight] = None


def get_hindsight() -> Optional[Hindsight]:
    """Return the shared Hindsight client, or None if not configured."""
    global _hindsight_client
    if _hindsight_client is None and settings.is_hindsight_configured():
        _hindsight_client = Hindsight(
            base_url=settings.HINDSIGHT_BASE_URL,
            api_key=settings.HINDSIGHT_API_KEY,
        )
    return _hindsight_client


async def ensure_bank() -> bool:
    """Create the memory bank if it does not already exist."""
    client = get_hindsight()
    if client is None:
        return False
    try:
        await client.acreate_bank(
            bank_id=settings.HINDSIGHT_BANK_ID,
            name="Recall Incident Memory",
            mission=(
                "You are an expert incident-response analyst. "
                "Store and retrieve production incident records, change events, "
                "root causes, resolution steps, and prevention recommendations. "
                "Surface patterns, precursors, and lessons learned."
            ),
            retain_mission=(
                "Extract incident details: title, services affected, severity, "
                "error messages, root cause, resolution steps, fix style, "
                "and any precursor events. Preserve technical terms exactly."
            ),
            reflect_mission=(
                "Analyse the stored incident history and produce clear, "
                "actionable insights about recurring root causes, riskiest services, "
                "common precursors, and team fix preferences."
            ),
            enable_observations=True,
            enable_temporal_retrieval=True,
        )
        logger.info("Memory bank '%s' created", settings.HINDSIGHT_BANK_ID)
        return True
    except Exception as exc:
        # Bank may already exist – that is fine
        err = str(exc)
        if "already exists" in err.lower() or "409" in err or "conflict" in err.lower():
            logger.debug("Bank already exists – continuing")
            return True
        logger.warning("ensure_bank warning: %s", err)
        return False


# ─── Idempotency helper ───────────────────────────────────────────────────────


def _incident_doc_id(incident: IncidentCreate) -> str:
    """Stable document ID from incident title + timestamp (for idempotency)."""
    key = f"{incident.title}|{incident.timestamp.isoformat()}"
    return "inc-" + hashlib.sha256(key.encode()).hexdigest()[:16]


def _change_doc_id(event: ChangeEventCreate) -> str:
    key = f"{event.title}|{event.timestamp.isoformat()}"
    return "chg-" + hashlib.sha256(key.encode()).hexdigest()[:16]


# ─── Retain ───────────────────────────────────────────────────────────────────


async def retain_incident(incident: IncidentCreate) -> dict[str, Any]:
    """Store an incident as a Hindsight memory. Idempotent by document_id."""
    client = get_hindsight()
    if client is None:
        return {"success": False, "message": "Hindsight not configured", "memory_id": None, "bank_id": settings.HINDSIGHT_BANK_ID}

    await ensure_bank()

    # Build rich memory content
    parts = [
        f"INCIDENT: {incident.title}",
        f"Timestamp: {incident.timestamp.isoformat()}",
        f"Severity: {incident.severity.value}",
        f"Affected services: {', '.join(incident.affected_services) or 'unknown'}",
    ]
    if incident.error_messages:
        parts.append(f"Error messages: {redact_secrets(incident.error_messages)}")
    if incident.stack_trace:
        parts.append(f"Stack trace: {redact_secrets(incident.stack_trace)}")
    if incident.duration_minutes is not None:
        parts.append(f"Duration: {incident.duration_minutes} minutes")
    if incident.root_cause:
        parts.append(f"Root cause: {incident.root_cause}")
    if incident.resolution_steps:
        parts.append(f"Resolution steps: {incident.resolution_steps}")
    if incident.prevention_notes:
        parts.append(f"Prevention notes: {incident.prevention_notes}")
    if incident.fixed_by:
        parts.append(f"Fixed by: {incident.fixed_by}")
    parts.append(f"Fix style: {incident.fix_style.value}")

    content = "\n".join(parts)
    doc_id = _incident_doc_id(incident)

    # Build tags
    tags = [
        f"severity:{incident.severity.value}",
        f"fix_style:{incident.fix_style.value}",
        f"source:{incident.source}",
        "type:incident",
    ]
    for svc in incident.affected_services:
        tags.append(f"service:{svc.strip()}")
    tags.extend(incident.tags)

    # Build metadata (str → str only)
    metadata: dict[str, str] = {
        "severity": incident.severity.value,
        "fix_style": incident.fix_style.value,
        "source": incident.source,
        "type": "incident",
        "services": json.dumps(incident.affected_services),
    }
    if incident.fixed_by:
        metadata["fixed_by"] = incident.fixed_by
    if incident.duration_minutes is not None:
        metadata["duration_minutes"] = str(incident.duration_minutes)

    try:
        response = await client.aretain(
            bank_id=settings.HINDSIGHT_BANK_ID,
            content=content,
            timestamp=incident.timestamp,
            document_id=doc_id,
            metadata=metadata,
            tags=tags,
        )
        logger.info("Retained incident '%s' doc_id=%s", incident.title, doc_id)
        return {
            "success": response.success,
            "memory_id": doc_id,
            "bank_id": response.bank_id,
            "message": "Incident retained successfully",
        }
    except Exception as exc:
        logger.error("retain_incident failed: %s", exc)
        return {
            "success": False,
            "memory_id": None,
            "bank_id": settings.HINDSIGHT_BANK_ID,
            "message": f"Failed to retain: {exc}",
        }


async def retain_change_event(event: ChangeEventCreate) -> dict[str, Any]:
    """Store an infrastructure/change event as a Hindsight memory."""
    client = get_hindsight()
    if client is None:
        return {"success": False, "message": "Hindsight not configured"}

    await ensure_bank()

    parts = [
        f"CHANGE EVENT: {event.title}",
        f"Type: {event.event_type.value}",
        f"Timestamp: {event.timestamp.isoformat()}",
        f"Description: {event.description}",
        f"Affected services: {', '.join(event.affected_services) or 'unknown'}",
    ]
    if event.author:
        parts.append(f"Author: {event.author}")

    content = "\n".join(parts)
    doc_id = _change_doc_id(event)

    tags = [
        "type:change_event",
        f"event_type:{event.event_type.value}",
    ]
    for svc in event.affected_services:
        tags.append(f"service:{svc.strip()}")
    tags.extend(event.tags)

    metadata: dict[str, str] = {
        "type": "change_event",
        "event_type": event.event_type.value,
        "services": json.dumps(event.affected_services),
    }
    if event.author:
        metadata["author"] = event.author

    try:
        response = await client.aretain(
            bank_id=settings.HINDSIGHT_BANK_ID,
            content=content,
            timestamp=event.timestamp,
            document_id=doc_id,
            metadata=metadata,
            tags=tags,
        )
        logger.info("Retained change event '%s' doc_id=%s", event.title, doc_id)
        return {"success": response.success, "memory_id": doc_id, "message": "Change event retained"}
    except Exception as exc:
        logger.error("retain_change_event failed: %s", exc)
        return {"success": False, "message": str(exc)}


async def retain_feedback(
    incident_title: str,
    fix_worked: bool,
    actual_root_cause: Optional[str],
    notes: Optional[str],
    fix_style: str,
) -> dict[str, Any]:
    """Store post-incident feedback to reinforce the learning loop."""
    client = get_hindsight()
    if client is None:
        return {"success": False, "message": "Hindsight not configured"}

    await ensure_bank()

    parts = [
        f"FEEDBACK ON INCIDENT: {incident_title}",
        f"Fix worked: {'Yes' if fix_worked else 'No'}",
        f"Fix style: {fix_style}",
    ]
    if actual_root_cause:
        parts.append(f"Confirmed root cause: {actual_root_cause}")
    if notes:
        parts.append(f"Notes: {notes}")

    content = "\n".join(parts)

    tags = [
        "type:feedback",
        f"fix_worked:{str(fix_worked).lower()}",
        f"fix_style:{fix_style}",
    ]
    metadata: dict[str, str] = {
        "type": "feedback",
        "fix_worked": str(fix_worked).lower(),
        "fix_style": fix_style,
    }

    try:
        response = await client.aretain(
            bank_id=settings.HINDSIGHT_BANK_ID,
            content=content,
            metadata=metadata,
            tags=tags,
        )
        return {"success": response.success, "message": "Feedback retained"}
    except Exception as exc:
        logger.error("retain_feedback failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ─── Recall ───────────────────────────────────────────────────────────────────


async def recall_memories(
    query: str,
    tags: Optional[list[str]] = None,
    max_tokens: int = 4096,
) -> list[MemoryUsed]:
    """Search Hindsight for memories relevant to *query*."""
    client = get_hindsight()
    if client is None:
        return []

    try:
        response = await client.arecall(
            bank_id=settings.HINDSIGHT_BANK_ID,
            query=query,
            max_tokens=max_tokens,
            budget="mid",
            tags=tags,
            tags_match="any",
        )
        memories: list[MemoryUsed] = []
        for r in response.results:
            memories.append(
                MemoryUsed(
                    id=r.id,
                    text=r.text,
                    tags=r.tags or [],
                    metadata=r.metadata or {},
                    occurred_start=r.occurred_start,
                )
            )
        logger.debug("Recalled %s memories for query", len(memories))
        return memories
    except Exception as exc:
        logger.error("recall_memories failed: %s", exc)
        return []


# ─── Reflect ──────────────────────────────────────────────────────────────────


async def reflect_patterns(
    query: str = "What are the most common recurring incidents, root causes, and precursors?",
    tags: Optional[list[str]] = None,
) -> PatternsResponse:
    """Use Hindsight reflect to surface patterns from stored memories."""
    client = get_hindsight()
    if client is None:
        return PatternsResponse(
            text="Hindsight is not configured. Add your API key to .env to enable pattern analysis.",
            facts_used=0,
        )

    try:
        response = await client.areflect(
            bank_id=settings.HINDSIGHT_BANK_ID,
            query=query,
            budget="mid",
            tags=tags,
            include_facts=True,
        )
        facts_count = 0
        if response.based_on:
            try:
                facts_count = len(response.based_on.model_dump().get("facts", []) or [])
            except Exception:
                pass
        return PatternsResponse(text=response.text, facts_used=facts_count)
    except Exception as exc:
        logger.error("reflect_patterns failed: %s", exc)
        return PatternsResponse(
            text=f"Pattern analysis unavailable: {exc}",
            facts_used=0,
        )
