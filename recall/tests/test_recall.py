"""
Pytest tests for Recall – ingestion, recall formatting, redaction, fallback logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import (
    ChangeEventCreate,
    DiagnoseRequest,
    FeedbackSubmit,
    FixStyle,
    IncidentBatch,
    IncidentCreate,
    Severity,
)
from app.utils.logging_utils import redact_secrets


# ─── Redaction tests ──────────────────────────────────────────────────────────


class TestRedaction:
    def test_redact_api_key_in_header(self) -> None:
        text = 'Authorization: Bearer sk-abc123456789012345678901234567890'
        result = redact_secrets(text)
        assert "sk-abc" not in result
        assert "[REDACTED]" in result

    def test_redact_groq_key(self) -> None:
        text = "gsk_abcdefghijklmnopqrstuvwxyz12345678901234567890"
        result = redact_secrets(text)
        assert "gsk_" not in result

    def test_redact_password_in_url(self) -> None:
        text = 'password="s3cr3tPassw0rd" connecting to db'
        result = redact_secrets(text)
        assert "s3cr3t" not in result

    def test_redact_email(self) -> None:
        text = "Fixed by engineer@company.com who found the root cause"
        result = redact_secrets(text)
        assert "engineer@company.com" not in result
        assert "[REDACTED]" in result

    def test_no_redaction_of_normal_text(self) -> None:
        text = "Connection timeout on DB write – RDS CPU at 95%"
        result = redact_secrets(text)
        assert result == text

    def test_redact_api_key_equals(self) -> None:
        text = 'api_key="GROQ-1234567890abcdef1234567890abcdef"'
        result = redact_secrets(text)
        assert "GROQ-1234567890" not in result


# ─── Schema validation tests ──────────────────────────────────────────────────


class TestIncidentSchema:
    def test_valid_incident_creation(self) -> None:
        inc = IncidentCreate(
            title="Connection timeout on DB write",
            severity=Severity.P1,
            affected_services=["payments-api", "rds-primary"],
            error_messages="psycopg2.OperationalError: connection timeout",
            root_cause="RDS CPU at 95%",
            resolution_steps="Kill long-running query, add index",
            fix_style=FixStyle.PROPER_FIX,
        )
        assert inc.title == "Connection timeout on DB write"
        assert inc.severity == Severity.P1
        assert len(inc.affected_services) == 2

    def test_services_from_comma_string(self) -> None:
        inc = IncidentCreate(
            title="Test incident",
            affected_services="auth-service, payments-api, checkout-worker",
        )
        assert inc.affected_services == ["auth-service", "payments-api", "checkout-worker"]

    def test_services_empty_default(self) -> None:
        inc = IncidentCreate(title="Test incident")
        assert inc.affected_services == []

    def test_severity_default(self) -> None:
        inc = IncidentCreate(title="Test incident")
        assert inc.severity == Severity.P3

    def test_fix_style_default(self) -> None:
        inc = IncidentCreate(title="Test incident")
        assert inc.fix_style == FixStyle.UNKNOWN

    def test_title_min_length(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IncidentCreate(title="ab")

    def test_change_event_valid(self) -> None:
        ev = ChangeEventCreate(
            title="Node.js 18 → 20 upgrade",
            description="Upgraded checkout-worker runtime",
            affected_services=["checkout-worker"],
        )
        assert ev.title.startswith("Node")

    def test_incident_batch(self) -> None:
        batch = IncidentBatch(
            incidents=[
                IncidentCreate(title="First incident"),
                IncidentCreate(title="Second incident"),
            ]
        )
        assert len(batch.incidents) == 2


# ─── Memory service tests (mocked Hindsight) ──────────────────────────────────


class TestMemoryService:
    def test_retain_incident_success(self) -> None:
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.bank_id = "recall-incidents"
        mock_response.items_count = 1

        mock_client = MagicMock()
        mock_client.retain.return_value = mock_response
        mock_client.create_bank.return_value = MagicMock()

        with patch("app.services.memory_service.get_hindsight", return_value=mock_client):
            with patch("app.services.memory_service.ensure_bank", return_value=True):
                from app.services.memory_service import retain_incident
                inc = IncidentCreate(
                    title="Test DB timeout",
                    severity=Severity.P1,
                    affected_services=["payments-api"],
                )
                result = retain_incident(inc)
                assert result["success"] is True
                mock_client.retain.assert_called_once()

    def test_retain_incident_hindsight_unavailable(self) -> None:
        with patch("app.services.memory_service.get_hindsight", return_value=None):
            from app.services.memory_service import retain_incident
            inc = IncidentCreate(title="Test incident")
            result = retain_incident(inc)
            assert result["success"] is False
            assert "not configured" in result["message"]

    def test_retain_incident_api_error(self) -> None:
        mock_client = MagicMock()
        mock_client.retain.side_effect = Exception("Hindsight API error 500")

        with patch("app.services.memory_service.get_hindsight", return_value=mock_client):
            with patch("app.services.memory_service.ensure_bank", return_value=True):
                from app.services.memory_service import retain_incident
                inc = IncidentCreate(title="Test incident")
                result = retain_incident(inc)
                assert result["success"] is False
                assert "Failed to retain" in result["message"]

    def test_recall_returns_memory_list(self) -> None:
        mock_result = MagicMock()
        mock_result.id = "mem-001"
        mock_result.text = "INCIDENT: Connection timeout on DB write"
        mock_result.tags = ["severity:P1", "service:payments-api"]
        mock_result.metadata = {"severity": "P1"}
        mock_result.occurred_start = "2024-02-15T02:14:00Z"

        mock_recall_response = MagicMock()
        mock_recall_response.results = [mock_result]

        mock_client = MagicMock()
        mock_client.recall.return_value = mock_recall_response

        with patch("app.services.memory_service.get_hindsight", return_value=mock_client):
            from app.services.memory_service import recall_memories
            memories = recall_memories(query="DB connection timeout")
            assert len(memories) == 1
            assert memories[0].id == "mem-001"
            assert "Connection timeout" in memories[0].text

    def test_recall_empty_on_hindsight_unavailable(self) -> None:
        with patch("app.services.memory_service.get_hindsight", return_value=None):
            from app.services.memory_service import recall_memories
            memories = recall_memories("any query")
            assert memories == []

    def test_recall_empty_on_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.recall.side_effect = Exception("Network error")

        with patch("app.services.memory_service.get_hindsight", return_value=mock_client):
            from app.services.memory_service import recall_memories
            memories = recall_memories("any query")
            assert memories == []

    def test_document_id_idempotency(self) -> None:
        """Same incident title+timestamp always produces the same doc_id."""
        from app.services.memory_service import _incident_doc_id
        ts = datetime(2024, 2, 15, 2, 14, 0, tzinfo=timezone.utc)
        inc1 = IncidentCreate(title="Connection timeout on DB write", timestamp=ts)
        inc2 = IncidentCreate(title="Connection timeout on DB write", timestamp=ts)
        assert _incident_doc_id(inc1) == _incident_doc_id(inc2)

    def test_different_incidents_different_doc_ids(self) -> None:
        from app.services.memory_service import _incident_doc_id
        ts = datetime(2024, 2, 15, 2, 14, 0, tzinfo=timezone.utc)
        inc1 = IncidentCreate(title="Incident A", timestamp=ts)
        inc2 = IncidentCreate(title="Incident B", timestamp=ts)
        assert _incident_doc_id(inc1) != _incident_doc_id(inc2)


# ─── LLM service tests ────────────────────────────────────────────────────────


class TestLLMService:
    def test_fallback_model_on_primary_failure(self) -> None:
        """Should try primary then fall back to fallback model."""
        models_called: list[str] = []

        def mock_call_groq(messages, model, **kwargs):
            models_called.append(model)
            if model == "openai/gpt-oss-120b":
                raise Exception("Model unavailable")
            return {"choices": [{"message": {"content": '{"result": "ok"}'}}]}

        from app.services import llm_service as llm

        original_primary = llm.settings.GROQ_PRIMARY_MODEL
        original_fallback = llm.settings.GROQ_FALLBACK_MODEL
        llm.settings.GROQ_PRIMARY_MODEL = "openai/gpt-oss-120b"
        llm.settings.GROQ_FALLBACK_MODEL = "qwen/qwen3-32b"

        try:
            with patch("app.services.llm_service._call_groq", side_effect=mock_call_groq):
                result = llm.call_llm(messages=[{"role": "user", "content": "test"}])
                assert '{"result": "ok"}' in result
                assert "openai/gpt-oss-120b" in models_called
                assert "qwen/qwen3-32b" in models_called
        finally:
            llm.settings.GROQ_PRIMARY_MODEL = original_primary
            llm.settings.GROQ_FALLBACK_MODEL = original_fallback

    def test_call_llm_json_parses_response(self) -> None:
        with patch("app.services.llm_service.call_llm", return_value='{"have_we_seen_this": true, "occurrence_count": 3}'):
            from app.services.llm_service import call_llm_json
            result = call_llm_json(messages=[])
            assert result["have_we_seen_this"] is True
            assert result["occurrence_count"] == 3

    def test_call_llm_json_handles_parse_failure(self) -> None:
        with patch("app.services.llm_service.call_llm", return_value="This is not JSON at all"):
            from app.services.llm_service import call_llm_json
            result = call_llm_json(messages=[])
            assert result == {}

    def test_call_llm_json_extracts_from_markdown_fence(self) -> None:
        wrapped = '```json\n{"key": "value"}\n```'
        with patch("app.services.llm_service.call_llm", return_value=wrapped):
            from app.services.llm_service import call_llm_json
            result = call_llm_json(messages=[])
            assert result.get("key") == "value"

    def test_diagnosis_prompt_with_memory(self) -> None:
        from app.services.llm_service import build_diagnosis_prompt
        memories = [{"id": "m1", "text": "INCIDENT: DB timeout", "tags": ["severity:P1"], "metadata": {}, "occurred_start": None}]
        msgs = build_diagnosis_prompt("DB timeout", memories, with_memory=True)
        assert len(msgs) == 2
        assert "RECALLED MEMORIES" in msgs[1]["content"]
        assert "m1" in msgs[1]["content"]

    def test_diagnosis_prompt_without_memory(self) -> None:
        from app.services.llm_service import build_diagnosis_prompt
        msgs = build_diagnosis_prompt("DB timeout", [], with_memory=False)
        assert "NO historical incident memory" in msgs[1]["content"]
        assert "RECALLED MEMORIES" not in msgs[1]["content"]


# ─── Agent tests ──────────────────────────────────────────────────────────────


class TestAgent:
    def test_diagnose_with_memory(self) -> None:
        from app.models.schemas import MemoryUsed as MemUsed
        mock_memory = MemUsed(
            id="mem-001",
            text="INCIDENT: Connection timeout – RDS CPU 95%",
            tags=["severity:P1", "service:payments-api"],
            metadata={"severity": "P1"},
            occurred_start="2024-02-15",
        )

        llm_result = {
            "have_we_seen_this": True,
            "occurrence_count": 4,
            "occurrence_dates": ["2024-02-15", "2024-04-03"],
            "root_cause_hypothesis": "RDS CPU at 95% from unoptimized query",
            "recommended_fix": "Kill long-running query and add index",
            "what_to_check_first": ["Check pg_stat_activity", "Check RDS CPU metrics"],
            "possible_precursors": ["Recent deploy of fraud detection feature"],
            "prevention_recommendation": "Add CPU alert at 80%",
            "confidence": 0.92,
            "confidence_label": "High",
        }

        with patch("app.services.memory_service.recall_memories", return_value=[mock_memory]):
            with patch("app.services.llm_service.call_llm_json", return_value=llm_result):
                from app.services.agent import diagnose
                result = diagnose("Connection timeout on DB write", with_memory=True)
                assert result.have_we_seen_this is True
                assert result.occurrence_count == 4
                assert result.confidence == 0.92
                assert result.confidence_label == "High"
                assert len(result.memories_used) == 1
                assert result.with_memory is True

    def test_diagnose_without_memory_forces_no_match(self) -> None:
        llm_result = {
            "have_we_seen_this": True,  # LLM might say True but should be forced False
            "occurrence_count": 0,
            "occurrence_dates": [],
            "root_cause_hypothesis": "Generic: check database connections",
            "recommended_fix": "Review recent changes",
            "what_to_check_first": ["Check service logs"],
            "possible_precursors": [],
            "prevention_recommendation": "Add monitoring",
            "confidence": 0.2,
            "confidence_label": "Low",
        }

        with patch("app.services.memory_service.recall_memories", return_value=[]):
            with patch("app.services.llm_service.call_llm_json", return_value=llm_result):
                from app.services.agent import diagnose
                result = diagnose("Any query", with_memory=False)
                # with_memory=False forces have_we_seen_this=False
                assert result.have_we_seen_this is False
                assert result.with_memory is False

    def test_diagnose_confidence_clamp(self) -> None:
        """Confidence out of range should be clamped to 0.0–1.0."""
        llm_result = {
            "have_we_seen_this": False,
            "occurrence_count": 0,
            "occurrence_dates": [],
            "root_cause_hypothesis": "Unknown",
            "recommended_fix": "Check logs",
            "what_to_check_first": [],
            "possible_precursors": [],
            "prevention_recommendation": "Monitor",
            "confidence": 1.5,  # Out of range
            "confidence_label": "High",
        }

        with patch("app.services.memory_service.recall_memories", return_value=[]):
            with patch("app.services.llm_service.call_llm_json", return_value=llm_result):
                from app.services.agent import diagnose
                result = diagnose("test")
                assert 0.0 <= result.confidence <= 1.0


# ─── Kaggle ingest helpers tests ─────────────────────────────────────────────


class TestKaggleIngest:
    def test_clean_val_placeholder(self) -> None:
        from scripts.ingest_kaggle import clean_val
        assert clean_val("?") is None
        assert clean_val("nan") is None
        assert clean_val("") is None
        assert clean_val(None) is None

    def test_clean_val_real(self) -> None:
        from scripts.ingest_kaggle import clean_val
        assert clean_val("P1 - Critical") == "P1 - Critical"
        assert clean_val("  auth-service  ") == "auth-service"

    def test_normalize_priority(self) -> None:
        from scripts.ingest_kaggle import normalize_priority
        assert normalize_priority("1 - critical") == Severity.P1
        assert normalize_priority("2 - high") == Severity.P2
        assert normalize_priority("3 - moderate") == Severity.P3
        assert normalize_priority("?") == Severity.P3
        assert normalize_priority(None) == Severity.P3

    def test_parse_ts_formats(self) -> None:
        from scripts.ingest_kaggle import parse_ts
        assert parse_ts("15/02/2024 14:30") is not None
        assert parse_ts("2024-02-15 14:30:00") is not None
        assert parse_ts("?") is None
        assert parse_ts(None) is None
