"""Capabilities route."""

from fastapi import APIRouter

from app.schemas.capabilities import CapabilitiesResponse
from app.services.media.probe import detect_capabilities

router = APIRouter()


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="System and media processing capabilities",
)
async def get_capabilities() -> CapabilitiesResponse:
    """Return honest detection of FFmpeg, FFprobe, and optional dependencies."""
    return detect_capabilities()
