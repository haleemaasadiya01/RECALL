"""Pydantic schemas for Recall – Incident Debugging Agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class Severity(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class FixStyle(str, Enum):
    QUICK_PATCH = "quick_patch"
    PROPER_FIX = "proper_fix"
    ROLLBACK = "rollback"
    UNKNOWN = "unknown"


class ChangeEventType(str, Enum):
    DEPLOY = "deploy"
    CONFIG = "config"
    INFRA = "infra"
    DEPENDENCY = "dependency"
    OTHER = "other"


# ─── Incident ─────────────────────────────────────────────────────────────────


class IncidentCreate(BaseModel):
    """Payload for creating a new incident memory."""

    title: str = Field(..., min_length=3, max_length=500)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    affected_services: list[str] = Field(default_factory=list)
    severity: Severity = Severity.P3
    error_messages: Optional[str] = None
    stack_trace: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    root_cause: Optional[str] = None
    resolution_steps: Optional[str] = None
    prevention_notes: Optional[str] = None
    fixed_by: Optional[str] = None
    fix_style: FixStyle = FixStyle.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="manual")

    @field_validator("affected_services", mode="before")
    @classmethod
    def normalize_services(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []


class IncidentResponse(BaseModel):
    """Response after retaining an incident."""

    success: bool
    memory_id: Optional[str] = None
    bank_id: str
    message: str


class IncidentBatch(BaseModel):
    """Batch of incidents for bulk ingest."""

    incidents: list[IncidentCreate]


# ─── Change Event ─────────────────────────────────────────────────────────────


class ChangeEventCreate(BaseModel):
    """Infrastructure / deploy change event."""

    title: str = Field(..., min_length=3, max_length=500)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: ChangeEventType = ChangeEventType.OTHER
    affected_services: list[str] = Field(default_factory=list)
    description: str
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("affected_services", mode="before")
    @classmethod
    def normalize_services(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []


# ─── Diagnose ─────────────────────────────────────────────────────────────────


class DiagnoseRequest(BaseModel):
    """Engineer's natural-language question or pasted stack trace."""

    query: str = Field(..., min_length=1, max_length=4000)
    service_filter: Optional[str] = None
    with_memory: bool = True


class MemoryUsed(BaseModel):
    """A single Hindsight memory unit used in a diagnosis."""

    id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    occurred_start: Optional[str] = None


class DiagnoseResponse(BaseModel):
    """Full diagnosis result from the agent."""

    query: str
    have_we_seen_this: bool
    occurrence_count: int
    occurrence_dates: list[str]
    root_cause_hypothesis: str
    recommended_fix: str
    what_to_check_first: list[str]
    possible_precursors: list[str]
    prevention_recommendation: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str
    memories_used: list[MemoryUsed]
    with_memory: bool
    raw_response: Optional[str] = None


# ─── Feedback ─────────────────────────────────────────────────────────────────


class FeedbackSubmit(BaseModel):
    """Post-incident feedback to reinforce learning."""

    incident_id: Optional[str] = None
    incident_title: str
    fix_worked: bool
    actual_root_cause: Optional[str] = None
    notes: Optional[str] = None
    fix_style: FixStyle = FixStyle.UNKNOWN


# ─── Patterns ─────────────────────────────────────────────────────────────────


class PatternsRequest(BaseModel):
    """Request parameters for the patterns/reflect view."""

    tags: Optional[list[str]] = None
    budget: str = "mid"


class PatternsResponse(BaseModel):
    """Reflected patterns from Hindsight."""

    text: str
    facts_used: int


# ─── Compare (memory vs no-memory) ───────────────────────────────────────────


class CompareRequest(BaseModel):
    """Side-by-side memory vs no-memory comparison."""

    query: str = Field(..., min_length=1, max_length=4000)


class CompareResponse(BaseModel):
    without_memory: DiagnoseResponse
    with_memory: DiagnoseResponse


# ─── Health ───────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    hindsight_connected: bool
    groq_configured: bool
    bank_id: str
    version: str = "1.0.0"
