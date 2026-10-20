"""Main FastAPI application entrypoint for Laqta.

Local-first, secure architecture binding strictly to 127.0.0.1 by default.
CORS is restricted to explicitly configured local origins (no wildcard '*').
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import qatta
from app.api.routes import api_router
from app.core.config import settings
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan event handler for startup and shutdown tasks."""
    logger.info(
        f"Starting {settings.APP_NAME} v{qatta.__version__} on {settings.HOST}:{settings.PORT}"
    )
    logger.info(f"Local-first storage directory: {settings.DATA_DIR}")
    logger.info(f"Allowed CORS origins: {settings.CORS_ORIGINS}")
    # Ensure local data directory structure exists and initialize SQLite DB
    data_dir = settings.get_effective_data_dir()
    logger.info(f"Using effective data directory: {data_dir}")
    from app.db.connection import init_db
    from app.jobs import job_manager

    init_db()
    await job_manager.start()
    yield
    await job_manager.stop()
    logger.info(f"Shutting down {settings.APP_NAME} backend")


app = FastAPI(
    title=settings.APP_NAME,
    version=qatta.__version__,
    description="Local-first long-video-to-Shorts studio API",
    lifespan=lifespan,
)

# Strict CORS policy - explicitly configured local origins, never wildcard '*'
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Mount API routers
app.include_router(api_router, prefix="/api")

from app.api.routes.health import get_health  # noqa: E402  (routes module must not import app.main)
from app.schemas.health import HealthResponse  # noqa: E402


@app.get(
    "/health",
    response_model=HealthResponse,
    include_in_schema=False,
    summary="Health status (alias of /api/health)",
)
async def health_alias() -> HealthResponse:
    """Top-level alias for ``/api/health`` so standard local probes succeed."""
    return await get_health()


@app.get("/v1/models", include_in_schema=False)
async def openai_models_alias() -> JSONResponse:
    """Benign response for local OpenAI-compatible probes."""
    return JSONResponse(
        content={
            "object": "list",
            "data": [],
        }
    )


@app.get("/", include_in_schema=False)
async def root_status() -> JSONResponse:
    """Root info endpoint providing basic guidance."""
    return JSONResponse(
        content={
            "app": settings.APP_NAME,
            "version": qatta.__version__,
            "docs": "/docs",
            "health": "/api/health",
            "capabilities": "/api/capabilities",
            "local_only": True,
        }
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    import uvicorn

    # Strict binding to 127.0.0.1 by default
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
