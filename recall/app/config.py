"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central config – all values from .env, never hardcoded."""

    # Hindsight
    HINDSIGHT_API_KEY: str = os.getenv("HINDSIGHT_API_KEY", "")
    HINDSIGHT_BASE_URL: str = os.getenv(
        "HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io"
    )
    HINDSIGHT_BANK_ID: str = os.getenv("HINDSIGHT_BANK_ID", "recall-incidents")

    # Groq
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_PRIMARY_MODEL: str = os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
    GROQ_FALLBACK_MODEL: str = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3-32b")

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",")
    ]

    # Data
    KAGGLE_DATASET_PATH: str = os.getenv(
        "KAGGLE_DATASET_PATH", "data/raw/incident_event_log.csv"
    )
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def is_hindsight_configured(self) -> bool:
        return bool(self.HINDSIGHT_API_KEY)

    def is_groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
