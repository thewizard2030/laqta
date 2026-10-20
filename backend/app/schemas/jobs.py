"""Job schemas and status enums for Laqta."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """Job lifecycle statuses as mandated by PRD §5 FR-10."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    """Supported job types."""

    AUDIO_EXTRACTION = "audio_extraction"
    TRANSCRIPTION = "transcription"
    MULTIMODAL = "multimodal"
    CANDIDATE_GENERATION = "candidate_generation"
    CANDIDATE_THUMBNAILS = "candidate_thumbnails"
    URL_INGESTION = "url_ingestion"
    RENDER = "render"
    PIPELINE = "pipeline"


class JobCreateRequest(BaseModel):
    """Request payload for creating a processing job."""

    project_id: str = Field(..., description="ID of the project owning this job")
    media_id: str | None = Field(default=None, description="Optional target media asset ID")
    type: JobType = Field(default=JobType.AUDIO_EXTRACTION, description="Type of background job")
    config: dict[str, Any] | None = Field(default=None, description="Optional job configuration")


class JobResponse(BaseModel):
    """Standard response model for background jobs."""

    id: str
    project_id: str
    media_id: str | None = None
    type: str
    status: JobStatus
    stage: str
    progress: float = Field(..., ge=0.0, le=100.0, description="Progress percentage 0.0 - 100.0")
    indeterminate: bool = Field(
        default=False,
        description=(
            "True when the percent value cannot be reliably estimated for "
            "the current stage (e.g. model loading, clip alignment). UIs "
            "should show the stage and elapsed time instead of a percent."
        ),
    )
    error_code: str | None = None
    error_message: str | None = None
    config_json: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


# Stages whose percent value is not a reliable estimate of remaining work.
# Transcription percent derives from real audio position; extraction percent
# from ffmpeg out_time when the media duration is known.
INDETERMINATE_STAGE_NAMES = frozenset(
    {
        "starting",
        "loading_model",
        "loading_clip_alignment_model",
        "aligning_selected_clips",
        "restored_from_cache",
    }
)
