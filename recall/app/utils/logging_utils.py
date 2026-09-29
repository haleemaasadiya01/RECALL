"""Structured logging and secret redaction utilities."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

# ─── Secret redaction ─────────────────────────────────────────────────────────

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'(?i)(api[_-]?key|token|password|secret|auth|bearer)["\s:=]+([^\s"&,\]}{]+)', re.I),
    re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'),  # emails
    re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),  # IPv4
    re.compile(r'(?i)sk-[a-zA-Z0-9]{20,}'),  # OpenAI-style keys
    re.compile(r'(?i)gsk_[a-zA-Z0-9]{20,}'),  # Groq keys
]


def redact_secrets(text: str) -> str:
    """Remove known secret patterns from *text* before logging or storing."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ─── Structured logging ───────────────────────────────────────────────────────


class RedactingFormatter(logging.Formatter):
    """Logging formatter that redacts secrets from log records."""

    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact_secrets(str(record.msg))
        if record.args:
            try:
                record.args = tuple(redact_secrets(str(a)) for a in record.args)
            except Exception:
                pass
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for *name*."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            RedactingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


def safe_log_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *d* with secrets redacted in string values."""
    return {
        k: redact_secrets(str(v)) if isinstance(v, str) else v
        for k, v in d.items()
    }
