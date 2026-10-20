"""Transcription job dispatch and transcript retrieval endpoints."""

import json

from fastapi import APIRouter, HTTPException, status

from app.db.models import TranscriptRecord
from app.db.repository import ProjectRepository
from app.jobs import job_manager
from app.schemas.jobs import JobResponse, JobStatus, JobType
from app.schemas.transcription import (
    ProviderCapabilityInfo,
    TranscriptionRequest,
    TranscriptResponse,
    TranscriptSegment,
)
from app.services.transcription.manager import transcription_manager

router = APIRouter()
repo = ProjectRepository()


@router.get(
    "/transcription/providers",
    response_model=list[ProviderCapabilityInfo],
    summary="List available transcription providers and hardware capabilities",
)
async def list_transcription_providers() -> list[ProviderCapabilityInfo]:
    """Return all local and cloud transcription providers with truthful hardware capabilities,
    privacy disclosures, and fallback reasons.
    """
    return transcription_manager.list_providers()


def _to_transcript_response(record: TranscriptRecord) -> TranscriptResponse:
    """Format TranscriptRecord into validated TranscriptResponse."""
    try:
        segments_data = json.loads(record.segments_json)
        segments = [TranscriptSegment(**s) for s in segments_data]
    except Exception:
        segments = []

    return TranscriptResponse(
        id=record.id,
        media_id=record.media_id,
        language=record.language,
        provider=record.provider,
        model=record.model,
        status=record.status,
        text=record.text,
        segments=segments,
        word_timestamps_available=record.word_timestamps_available,
        timing_granularity=record.timing_granularity,
        created_at=record.created_at,
    )


@router.post(
    "/media/{media_id}/transcription-jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue transcription job for media asset",
)
async def create_transcription_job(
    media_id: str,
    payload: TranscriptionRequest | None = None,
) -> JobResponse:
    """Enqueue local speech recognition using faster-whisper on CPU.

    Uses conservative model defaults (int8 'base') suitable for 8 GB RAM machines.
    """
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )

    req = payload or TranscriptionRequest()
    cfg = {
        "model_size": req.model_size,
        "language": req.language,
        "word_timestamps": req.word_timestamps,
        "provider": req.provider,
        "profile": req.profile,
    }

    try:
        job = await job_manager.submit_job(
            project_id=media.project_id,
            job_type=JobType.TRANSCRIPTION.value,
            media_id=media.id,
            config=cfg,
        )
        return JobResponse(
            id=job.id,
            project_id=job.project_id,
            media_id=job.media_id,
            type=job.type,
            status=JobStatus(job.status),
            stage=job.stage,
            progress=job.progress,
            error_code=job.error_code,
            error_message=job.error_message,
            config_json=job.config_json,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/media/{media_id}/transcripts",
    response_model=list[TranscriptResponse],
    summary="List all transcripts for a media asset",
)
async def list_media_transcripts(media_id: str) -> list[TranscriptResponse]:
    """Retrieve all persisted transcripts for a media asset (preserves re-transcriptions)."""
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )
    records = repo.list_media_transcripts(media_id)
    return [_to_transcript_response(r) for r in records]


@router.get(
    "/transcripts/{transcript_id}",
    response_model=TranscriptResponse,
    summary="Get transcript by ID",
)
async def get_transcript(transcript_id: str) -> TranscriptResponse:
    """Retrieve a specific transcript by ID including segment and word timings."""
    record = repo.get_transcript(transcript_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcript '{transcript_id}' not found.",
        )
    return _to_transcript_response(record)
