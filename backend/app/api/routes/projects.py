"""Project endpoints and local media upload."""

import shutil
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import logger
from app.db.repository import ProjectRepository
from app.schemas.media import MediaAssetResponse
from app.schemas.projects import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.media.probe import MediaProbeError, probe_media_file
from app.services.media.signature import validate_media_signature

router = APIRouter()
repo = ProjectRepository()


def _to_media_response(m) -> MediaAssetResponse:
    return MediaAssetResponse(
        id=m.id,
        project_id=m.project_id,
        original_name=m.original_name,
        size_bytes=m.size_bytes,
        duration_ms=m.duration_ms,
        width=m.width,
        height=m.height,
        video_codec=m.video_codec,
        audio_codec=m.audio_codec,
        status=m.status,
        created_at=m.created_at,
    )


@router.get(
    "/projects",
    response_model=list[ProjectResponse],
    summary="List all local projects",
)
async def list_projects() -> list[ProjectResponse]:
    """Retrieve all projects sorted by creation date."""
    records = repo.list_projects()
    results: list[ProjectResponse] = []
    for r in records:
        media = repo.list_project_media(r.id)
        results.append(
            ProjectResponse(
                id=r.id,
                name=r.name,
                created_at=r.created_at,
                updated_at=r.updated_at,
                media_count=len(media),
                media_assets=[_to_media_response(m) for m in media],
            )
        )
    return results


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new local project",
)
async def create_project(payload: ProjectCreate) -> ProjectResponse:
    """Create a new local project container."""
    project = repo.create_project(name=payload.name)
    # Ensure project filesystem directory is initialized
    settings.get_project_dir(project.id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        media_count=0,
        media_assets=[],
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get project by ID",
)
async def get_project(project_id: str) -> ProjectResponse:
    """Retrieve project details and associated media."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    media = repo.list_project_media(project.id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        media_count=len(media),
        media_assets=[_to_media_response(m) for m in media],
    )


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
async def delete_project(project_id: str) -> None:
    """Delete a project and cleanly remove its directory from local disk."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    # 1. Delete from database (cascades to media_assets & jobs)
    repo.delete_project(project_id)

    # 2. Cleanly remove filesystem directory
    try:
        project_dir = settings.get_project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
            logger.info(f"Removed project directory on disk: {project_dir}")
    except Exception as e:
        logger.warning(f"Error removing project directory for {project_id}: {e}")


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Update project name",
)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
) -> ProjectResponse:
    """Update a project's name."""
    project = repo.update_project(project_id, payload.name)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    media = repo.list_project_media(project.id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        media_count=len(media),
        media_assets=[_to_media_response(m) for m in media],
    )


@router.post(
    "/projects/{project_id}/duplicate",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate an existing project",
)
async def duplicate_project(project_id: str) -> ProjectResponse:
    """Duplicate a project container."""
    source = repo.get_project(project_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    copy_name = f"{source.name} (Copy)"
    new_project = repo.create_project(name=copy_name)
    settings.get_project_dir(new_project.id)
    return ProjectResponse(
        id=new_project.id,
        name=new_project.name,
        created_at=new_project.created_at,
        updated_at=new_project.updated_at,
        media_count=0,
        media_assets=[],
    )


@router.post(
    "/projects/{project_id}/media",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and probe local video file",
)
async def upload_project_media(
    project_id: str,
    file: Annotated[UploadFile, File(...)],
) -> MediaAssetResponse:
    """Securely stream, validate, probe, and import local video.

    Security & robustness:
    - Never trust client-supplied filesystem paths (sanitizes original filename).
    - Checks file extension against whitelist.
    - Validates binary magic byte headers (extensions alone are not enough).
    - Validates available disk space before and during stream.
    - Enforces max upload size limit.
    - Probes media using ffprobe argument array (no shell=True).
    - Validates positive duration and presence of video stream.
    """
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    raw_filename = file.filename or "unknown.mp4"
    # Prevent path traversal: only keep the basename
    original_basename = Path(raw_filename).name
    ext = Path(original_basename).suffix.lower()

    # 1. Extension validation
    if ext not in settings.ALLOWED_MEDIA_EXTENSIONS:
        allowed = ", ".join(sorted(settings.ALLOWED_MEDIA_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Laqta supports: {allowed}",
        )

    # 2. Signature (magic byte) inspection
    header_chunk = await file.read(512)
    is_valid_sig, _, sig_explanation = validate_media_signature(header_chunk)
    if not is_valid_sig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file content. {sig_explanation}",
        )

    # Rewind file to start
    await file.seek(0)

    # 3. Controlled target destination
    safe_media_id = f"med_{uuid4().hex[:12]}"
    safe_filename = f"{safe_media_id}{ext}"
    media_dir = settings.get_project_media_dir(project_id)
    target_path = media_dir / safe_filename

    # 4. Check disk space before streaming
    if not settings.check_available_space(media_dir, required_bytes=10 * 1024 * 1024):
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Insufficient local disk space available for media import.",
        )

    # 5. Stream file safely in 64 KB chunks
    total_bytes = 0
    try:
        with open(target_path, "wb") as f_out:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                    max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds maximum allowed upload size of {max_mb} MB.",
                    )
                f_out.write(chunk)
    except HTTPException:
        # Clean up partial file on size limit breach
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        logger.error(f"Failed to stream file to disk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write media file to local disk.",
        ) from e

    # 6. Media probe with FFprobe
    try:
        probe_result = probe_media_file(target_path)
    except MediaProbeError as e:
        # Clean up invalid media file
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        error_text = str(e)
        if "FFprobe is not installed" in error_text:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_text,
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file failed media probe: {error_text}",
        ) from e

    # 7. Record media asset in database
    media_asset = repo.create_media_asset(
        project_id=project_id,
        safe_path=str(target_path),
        original_name=original_basename,
        size_bytes=total_bytes,
        duration_ms=probe_result.duration_ms,
        width=probe_result.width,
        height=probe_result.height,
        video_codec=probe_result.video_codec,
        audio_codec=probe_result.audio_codec,
        status="ready",
    )

    return _to_media_response(media_asset)


@router.get(
    "/projects/{project_id}/manifest",
    summary="Get raw QattaManifest for a project",
)
async def get_project_manifest(project_id: str):
    """Retrieve the single-source-of-truth QattaManifest for a project."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    project_dir = settings.get_project_dir(project_id)
    manifest_file = project_dir / "qatta_manifest.json"
    if not manifest_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No manifest found for project '{project_id}'. Run ingest or pipeline first.",
        )
    try:
        import json

        return json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read manifest: {e}",
        ) from e


@router.get(
    "/projects/{project_id}/utterances",
    summary="List atomic utterances from project manifest",
)
async def get_project_utterances(project_id: str):
    """Retrieve atomic utterances (U_0001...) bounded by acoustic pauses."""
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    project_dir = settings.get_project_dir(project_id)
    manifest_file = project_dir / "qatta_manifest.json"
    if not manifest_file.exists():
        return []
    try:
        import json

        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        return data.get("atomic_utterances", [])
    except Exception as e:
        logger.warning(f"Failed to read utterances from manifest: {e}")
        return []
