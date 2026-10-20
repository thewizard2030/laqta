"""Health route."""

from fastapi import APIRouter

import qatta
from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="Service health status")
async def get_health() -> HealthResponse:
    """Return application health status and version."""
    return HealthResponse(
        status="healthy",
        app=settings.APP_NAME,
        version=qatta.__version__,
    )
