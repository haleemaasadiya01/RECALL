"""Groq LLM service – function calling, retries, fallback model."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.utils.logging_utils import get_logger, redact_secrets

logger = get_logger(__name__)
settings = get_settings()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

_MAX_RETRIES = 3
_RETRY_BACKOFF = [1.0, 2.0, 4.0]


# ─── Core call ────────────────────────────────────────────────────────────────


def _call_groq(
    messages: list[dict[str, Any]],
    model: str,
    response_format: Optional[dict[str, str]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    """Raw Groq API call. Raises on non-2xx after retries."""
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    last_exc: Exception = RuntimeError("No attempts made")
    for attempt, backoff in enumerate(_RETRY_BACKOFF, start=1):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(GROQ_API_URL, headers=headers, json=payload)
            if resp.status_code == 429:  # rate limit
                logger.warning("Groq rate-limited on attempt %d, backing off %.1fs", attempt, backoff)
                time.sleep(backoff)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            logger.warning("Groq attempt %s/%s failed: %s", attempt, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(backoff)

    raise last_exc


def call_llm(
    messages: list[dict[str, Any]],
    response_format: Optional[dict[str, str]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> str:
    """Call Groq with primary model, falling back to GROQ_FALLBACK_MODEL on error."""
    for model in (settings.GROQ_PRIMARY_MODEL, settings.GROQ_FALLBACK_MODEL):
        try:
            result = _call_groq(
                messages=messages,
                model=model,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return result["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("LLM call failed with model %s: %s", model, exc)

    return "LLM unavailable – please try again shortly."


def call_llm_json(
    messages: list[dict[str, Any]],
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Call Groq requesting JSON output. Falls back to empty dict on parse failure."""
    raw = call_llm(
        messages=messages,
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=max_tokens,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON block from markdown fences
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        logger.error("Failed to parse LLM JSON response: %s", redact_secrets(raw[:200]))
        return {}


# ─── Diagnosis prompt ─────────────────────────────────────────────────────────


def build_diagnosis_prompt(
    query: str,
    memories: list[dict[str, Any]],
    with_memory: bool,
) -> list[dict[str, Any]]:
    """Build the messages list for incident diagnosis."""

    system_content = (
        "You are Recall, an expert incident-debugging agent for production systems. "
        "Your job is to help engineers diagnose incidents quickly by drawing on institutional memory.\n\n"
        "RULES:\n"
        "- NEVER fabricate past incidents. Every historical claim MUST cite a recalled memory.\n"
        "- If no close match exists, say so honestly.\n"
        "- Be concise, actionable, and structured.\n"
        "- Output valid JSON matching the schema described in the user message.\n"
        "- confidence is a float 0.0-1.0 based on how many relevant memories were found and how closely they match.\n"
    )

    if with_memory and memories:
        memory_block = "\n\n---RECALLED MEMORIES---\n"
        for i, m in enumerate(memories, 1):
            memory_block += f"\n[Memory {i}] (id={m.get('id','?')}, tags={m.get('tags',[])})\n{m.get('text','')}\n"
        user_prefix = (
            f"Engineer query: {query}\n\n"
            f"{memory_block}\n\n"
            "Based ONLY on the recalled memories above, provide a diagnosis as JSON:\n"
        )
    else:
        user_prefix = (
            f"Engineer query: {query}\n\n"
            "You have NO historical incident memory available. "
            "Provide a generic diagnosis as JSON:\n"
        )

    schema = json.dumps({
        "have_we_seen_this": "bool – true only if recalled memories show a past match",
        "occurrence_count": "int – count of matching past incidents (0 if none)",
        "occurrence_dates": "list[str] – ISO dates of past occurrences",
        "root_cause_hypothesis": "str – most likely root cause",
        "recommended_fix": "str – what to do right now",
        "what_to_check_first": "list[str] – top 3-5 things to check, ranked",
        "possible_precursors": "list[str] – recent changes that may have triggered this",
        "prevention_recommendation": "str – how to prevent recurrence",
        "confidence": "float 0.0-1.0",
        "confidence_label": "str – one of: High, Medium, Low, No match",
    }, indent=2)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prefix + schema},
    ]
