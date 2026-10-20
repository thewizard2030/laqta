"""Media asset schemas."""

from pydantic import BaseModel, Field


class MediaAssetResponse(BaseModel):
    """Media asset detail response."""

    id: str = Field(..., description="Unique media asset ID")
    project_id: str = Field(..., description="Parent project ID")
    original_name: str = Field(..., description="Original user filename")
    size_bytes: int = Field(..., description="File size in bytes")
    duration_ms: int = Field(..., description="Duration in milliseconds")
    width: int = Field(..., description="Video width in pixels")
    height: int = Field(..., description="Video height in pixels")
    video_codec: str = Field(..., description="Detected video codec")
    audio_codec: str = Field(..., description="Detected audio codec or 'none'")
    status: str = Field(..., description="Media status (e.g. ready, processing)")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class UrlIngestRequest(BaseModel):
    """Request payload for gated URL ingestion (PRD FR-12, fail-closed)."""

    project_id: str = Field(..., description="Target project for the downloaded video")
    url: str = Field(..., min_length=1, max_length=2048, description="Public http(s) video URL")
    rights_confirmed: bool = Field(
        default=False,
        description=(
            "Explicit per-import confirmation that the user owns this content "
            "or has permission to process it. Imports are refused otherwise."
        ),
    )


class UrlIngestAcceptedResponse(BaseModel):
    """Acknowledgement that a background URL-ingestion job was queued."""

    job_id: str = Field(..., description="Background job tracking the download")
    status: str = Field(default="queued", description="Initial job status")
    url_host: str = Field(..., description="Host of the requested URL (no path/query)")
