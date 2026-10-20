"""Job management and execution endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.db.models import JobRecord
from app.db.repository import ProjectRepository
from app.jobs import job_manager
from app.schemas.jobs import (
    INDETERMINATE_STAGE_NAMES,
    JobCreateRequest,
    JobResponse,
    JobStatus,
)

router = APIRouter()
repo = ProjectRepository()


def _to_job_response(record: JobRecord) -> JobResponse:
    """Format JobRecord into standard JobResponse."""
    return JobResponse(
        id=record.id,
        project_id=record.project_id,
        media_id=record.media_id,
        type=record.type,
        status=JobStatus(record.status),
        stage=record.stage,
        progress=record.progress,
        indeterminate=record.stage in INDETERMINATE_STAGE_NAMES,
        error_code=record.error_code,
        error_message=record.error_message,
        config_json=record.config_json,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new background job",
)
async def submit_job(payload: JobCreateRequest) -> JobResponse:
    """Enqueue a job to the single-worker background queue."""
    try:
        record = await job_manager.submit_job(
            project_id=payload.project_id,
            job_type=payload.type.value,
            media_id=payload.media_id,
            config=payload.config,
        )
        return _to_job_response(record)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post(
    "/media/{media_id}/audio-extraction-jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue audio extraction job for media asset",
)
async def create_media_audio_extraction_job(media_id: str) -> JobResponse:
    """Enqueue 16 kHz mono WAV audio extraction for a given media asset."""
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )

    try:
        record = await job_manager.submit_job(
            project_id=media.project_id,
            job_type="audio_extraction",
            media_id=media.id,
        )
        return _to_job_response(record)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job status by ID",
)
async def get_job(job_id: str) -> JobResponse:
    """Retrieve detailed status, stage, progress, and diagnostic error if any."""
    record = repo.get_job(job_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return _to_job_response(record)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=JobResponse,
    summary="Cancel a queued or running job",
)
async def cancel_job(job_id: str) -> JobResponse:
    """Cancel a queued or running job and terminate underlying subprocess if active."""
    record = await job_manager.cancel_job(job_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return _to_job_response(record)


@router.get(
    "/projects/{project_id}/jobs",
    response_model=list[JobResponse],
    summary="List all jobs for a project",
)
async def list_project_jobs(project_id: str) -> list[JobResponse]:
    """Retrieve all jobs associated with a project sorted by date descending."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    jobs = repo.list_project_jobs(project_id)
    return [_to_job_response(j) for j in jobs]


@router.delete(
    "/projects/{project_id}/jobs",
    summary="Clear historical finished/failed jobs for a project",
)
async def clear_project_jobs(project_id: str) -> dict[str, int]:
    """Delete historical succeeded, failed, or cancelled jobs for a project."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    deleted_count = repo.clear_project_jobs(project_id, keep_active=True)
    return {"deleted_count": deleted_count}


@router.post(
    "/projects/{project_id}/pipeline-jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue full pipeline job for project",
)
async def create_project_pipeline_job(project_id: str) -> JobResponse:
    """Enqueue end-to-end shorts generation pipeline (s01..s06) for a project."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    media_list = repo.list_project_media(project_id)
    media_id = media_list[0].id if media_list else None
    try:
        record = await job_manager.submit_job(
            project_id=project_id,
            job_type="pipeline",
            media_id=media_id,
        )
        return _to_job_response(record)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
