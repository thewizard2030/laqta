"""API route definitions."""

from fastapi import APIRouter

from app.api.routes.candidates import router as candidates_router
from app.api.routes.capabilities import router as capabilities_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.media import router as media_router
from app.api.routes.projects import router as projects_router
from app.api.routes.renders import router as renders_router
from app.api.routes.transcription import router as transcription_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="", tags=["health"])
api_router.include_router(capabilities_router, prefix="", tags=["capabilities"])
api_router.include_router(projects_router, prefix="", tags=["projects"])
api_router.include_router(media_router, prefix="", tags=["media"])
api_router.include_router(jobs_router, prefix="", tags=["jobs"])
api_router.include_router(transcription_router, prefix="", tags=["transcription"])
api_router.include_router(candidates_router, prefix="", tags=["candidates"])
api_router.include_router(renders_router, prefix="", tags=["captions & rendering"])

__all__ = ["api_router"]
