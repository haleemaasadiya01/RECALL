"""Core Recall agent – orchestrates memory recall + LLM reasoning."""

from __future__ import annotations

from typing import Any, Optional

from app.models.schemas import DiagnoseResponse, MemoryUsed
from app.services import llm_service, memory_service
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


async def diagnose(
    query: str,
    service_filter: Optional[str] = None,
    with_memory: bool = True,
) -> DiagnoseResponse:
    """
    Run the full diagnosis pipeline.

    1. If with_memory: recall relevant memories from Hindsight
    2. Build a structured LLM prompt (with or without memories)
    3. Parse and return the structured DiagnoseResponse
    """
    memories: list[MemoryUsed] = []

    if with_memory:
        tags = [f"service:{service_filter}"] if service_filter else None
        memories = await memory_service.recall_memories(query=query, tags=tags)

    # Convert to plain dicts for prompt builder
    memory_dicts: list[dict[str, Any]] = [
        {
            "id": m.id,
            "text": m.text,
            "tags": m.tags,
            "metadata": m.metadata,
            "occurred_start": m.occurred_start,
        }
        for m in memories
    ]

    messages = llm_service.build_diagnosis_prompt(
        query=query,
        memories=memory_dicts,
        with_memory=with_memory,
    )

    llm_result = llm_service.call_llm_json(messages=messages)

    # Extract occurrence dates from memories if LLM didn't populate them
    if not llm_result.get("occurrence_dates") and memories:
        dates = [
            m.occurred_start or m.metadata.get("timestamp", "")
            for m in memories
            if m.occurred_start or m.metadata.get("timestamp")
        ]
        llm_result["occurrence_dates"] = dates[:10]

    # Safeguard defaults
    confidence = float(llm_result.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    # Auto-label confidence
    if confidence >= 0.75:
        confidence_label = "High"
    elif confidence >= 0.45:
        confidence_label = "Medium"
    elif confidence > 0.0:
        confidence_label = "Low"
    else:
        confidence_label = llm_result.get("confidence_label", "No match")

    # If no memory, force have_we_seen_this false
    have_seen = bool(llm_result.get("have_we_seen_this", False))
    if not with_memory:
        have_seen = False

    return DiagnoseResponse(
        query=query,
        have_we_seen_this=have_seen,
        occurrence_count=int(llm_result.get("occurrence_count", 0)),
        occurrence_dates=llm_result.get("occurrence_dates", []),
        root_cause_hypothesis=llm_result.get(
            "root_cause_hypothesis", "Unable to determine – check logs for more context."
        ),
        recommended_fix=llm_result.get(
            "recommended_fix", "Review recent changes and check service health metrics."
        ),
        what_to_check_first=llm_result.get("what_to_check_first", []),
        possible_precursors=llm_result.get("possible_precursors", []),
        prevention_recommendation=llm_result.get(
            "prevention_recommendation", "No specific recommendation available."
        ),
        confidence=confidence,
        confidence_label=confidence_label,
        memories_used=memories,
        with_memory=with_memory,
        raw_response=None,
    )
