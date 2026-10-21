"""Health route."""

from fastapi import APIRouter

import qatta
from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Service health status")
async def get_health() -> HealthResponse:
    """Return the application health status.

    The status is honest: it reports "degraded" when the background job
    worker is not running, because a stopped worker means queued jobs would
    never be executed. Reporting "healthy" in that state would be a lie the
    studio would happily show.
    """
    from app.jobs.manager import job_manager

    worker_running = job_manager.is_running()
    return HealthResponse(
        status="healthy" if worker_running else "degraded",
        app=settings.APP_NAME,
        version=qatta.__version__,
        worker="running" if worker_running else "stopped",
    )
