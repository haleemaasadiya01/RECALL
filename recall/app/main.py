"""FastAPI application factory for Recall."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import get_settings
from app.services.memory_service import ensure_bank
from app.utils.logging_utils import get_logger

settings = get_settings()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Recall – Incident Debugging Agent",
        description=(
            "AI-powered incident diagnosis with persistent memory via Hindsight (Vectorize). "
            "Remembers every incident, surfaces patterns, and gets smarter with each fix."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(router, prefix="/api")

    # Serve frontend SPA
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(str(frontend_dir / "index.html"))

        @app.get("/demo-data.json", include_in_schema=False)
        async def serve_demo_data() -> FileResponse:
            return FileResponse(str(frontend_dir / "demo-data.json"), media_type="application/json")

        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str) -> FileResponse:
            # SPA fallback
            return FileResponse(str(frontend_dir / "index.html"))

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("Recall starting up – env=%s", settings.APP_ENV)
        if settings.is_hindsight_configured():
            ok = await ensure_bank()
            logger.info("Hindsight bank ready: %s", ok)
        else:
            logger.warning("HINDSIGHT_API_KEY not set – memory features disabled")
        if not settings.is_groq_configured():
            logger.warning("GROQ_API_KEY not set – LLM features disabled")

    return app


app = create_app()
