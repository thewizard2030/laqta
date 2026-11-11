"""Settings and Bring Your Own Keys (BYOK) routes."""

from fastapi import APIRouter, status

from app.schemas.settings import (
    ClearCacheResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    VerifyKeyRequest,
    VerifyKeyResponse,
)
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "",
    response_model=SettingsResponse,
    summary="Get application settings and provider status",
)
async def get_settings() -> SettingsResponse:
    """Return effective application settings with masked secrets."""
    return SettingsService.get_settings_response()


@router.patch(
    "",
    response_model=SettingsResponse,
    summary="Update application settings and BYOK credentials",
)
async def update_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
    """Update user settings and store them locally in SQLite."""
    return SettingsService.update_settings(payload)


@router.post(
    "/verify",
    response_model=VerifyKeyResponse,
    summary="Verify connection and credentials for an AI provider",
)
async def verify_provider_key(payload: VerifyKeyRequest) -> VerifyKeyResponse:
    """Execute a lightweight live connection probe against a provider endpoint."""
    return await SettingsService.verify_provider_connection(payload)


@router.post(
    "/clear-cache",
    response_model=ClearCacheResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear the local transcript cache",
)
async def clear_transcript_cache() -> ClearCacheResponse:
    """Safely delete cached transcript files from disk."""
    return SettingsService.clear_transcript_cache()


@router.post(
    "/reset",
    response_model=SettingsResponse,
    summary="Reset user settings to factory defaults",
)
async def reset_settings() -> SettingsResponse:
    """Clear all stored user settings and restore defaults."""
    return SettingsService.reset_to_defaults()
