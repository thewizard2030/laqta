"""Main FastAPI application entrypoint for Laqta.

Local-first, secure architecture binding strictly to 127.0.0.1 by default.
CORS is restricted to explicitly configured local origins (no wildcard '*').
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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
async def root_status() -> Response:
    """The studio UI in release mode, the API status otherwise.

    With a built frontend the root opens the studio — one address for the
    whole application. Without one it stays a helpful JSON status.
    """
    dist = settings.frontend_dist_path()
    if dist.is_dir():
        return FileResponse(dist / "index.html")
    return JSONResponse(
        content={
            "app": settings.APP_NAME,
            "version": qatta.__version__,
            "docs": "/docs",
            "health": "/api/health",
            "capabilities": "/api/capabilities",
            "local_only": True,
            "studio": "run `npm run dev` in frontend/ for the studio UI",
        }
    )


# ---------------------------------------------------------------------------
# The studio UI (release mode)
# ---------------------------------------------------------------------------
# When the frontend has been built (`npm run build`), the API serves it too.
# That is what makes Laqta a one-command application: `laqta studio
# --production` builds the UI and serves everything from a single address.
#
# The catch-all is registered AFTER the API router, so /api/* always wins.
@app.get("/{full_path:path}", include_in_schema=False)
async def studio_ui(full_path: str) -> Response:
    """Serve the built studio, falling back to index.html (client routing).

    The directory is resolved per request, so building the studio while the
    API runs is enough to switch it into release mode.
    """
    dist = settings.frontend_dist_path()
    if not dist.is_dir():
        return JSONResponse(
            content={
                "detail": "Not found",
                "hint": (
                    "The studio UI is not built. Run `npm run build` in "
                    "frontend/, or use `npm run dev` for the dev server."
                ),
            },
            status_code=404,
        )

    candidate = (dist / full_path).resolve()
    # Never serve anything outside the build directory.
    if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
        return FileResponse(candidate)
    return FileResponse(dist / "index.html")


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
