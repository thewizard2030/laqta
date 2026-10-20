"""Caption generation and render/export endpoints (PRD §5 FR-08/FR-09, §11 Gate D).

API-shape note: the PRD §6 contract lists ``/api/clips/{clip_id}/...`` while
this codebase consistently implements clips as "candidates"
(``/api/media/{media_id}/candidates`` etc., P2/Gate C). To stay coherent with
the existing routes, render/captions/artifacts endpoints address candidates.
No heavy media processing runs in request handlers: rendering is performed by
the single-worker background job manager (FR-10).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.db.repository import (
    CandidateRepository,
    ProjectRepository,
    RenderRepository,
)
from app.jobs import job_manager
from app.schemas.captions import (
    CandidateArtifactsResponse,
    CandidateCaptionsResponse,
    CaptionArtifact,
    CaptionGenerationRequest,
    CaptionStyleSettings,
)
from app.schemas.jobs import JobResponse, JobStatus, JobType
from app.schemas.rendering import RenderRequest
from app.schemas.transcription import TranscriptSegment
from app.services.captions.service import generate_candidate_captions

router = APIRouter()
repo = ProjectRepository()
candidates_repo = CandidateRepository()
renders_repo = RenderRepository()


def _load_segments(transcript_json: str) -> list[TranscriptSegment]:
    try:
        return [TranscriptSegment(**s) for s in json.loads(transcript_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored transcript segments are not parseable: {e}",
        ) from e


def _get_candidate_or_404(candidate_id: str):
    """Resolve a candidate plus its media asset, or raise 404."""
    candidate = candidates_repo.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    media = repo.get_media_asset(candidate.media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Media asset '{candidate.media_id}' linked to this candidate no longer exists."
            ),
        )
    return candidate, media


def _get_transcript_or_409(candidate) -> str:
    """Load segment JSON of the candidate's transcript, or raise 409."""
    transcript = repo.get_transcript(candidate.transcript_id)
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Transcript no longer exists; regenerate candidates from a "
                "fresh transcription before requesting captions or renders."
            ),
        )
    return transcript.segments_json


@router.post(
    "/candidates/{candidate_id}/captions",
    response_model=CandidateCaptionsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate editable SRT and ASS captions for a candidate clip",
)
async def create_candidate_captions(
    candidate_id: str,
    payload: CaptionGenerationRequest | None = None,
) -> CandidateCaptionsResponse:
    """Generate caption files from transcript timestamps (PRD FR-08).

    Pure text transformation (no media work in the handler). Applies the
    FR-08 no-karaoke fallback when word timings are missing/unreliable.
    """
    candidate, media = _get_candidate_or_404(candidate_id)
    req = payload or CaptionGenerationRequest()

    segments = _load_segments(_get_transcript_or_409(candidate))
    captions_dir = settings.get_project_captions_dir(media.project_id)
    try:
        generated = generate_candidate_captions(
            captions_dir=captions_dir,
            candidate_id=candidate.id,
            start_ms=candidate.start_ms,
            end_ms=candidate.end_ms,
            segments=segments,
            style=req.style,
            formats=tuple(req.formats),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Caption generation failed: {e}",
        ) from e

    return CandidateCaptionsResponse(
        candidate_id=candidate.id,
        media_id=media.id,
        transcript_id=candidate.transcript_id,
        srt_path=generated.srt_path,
        ass_path=generated.ass_path,
        timing_granularity=generated.timing_granularity,
        karaoke_used=generated.karaoke_used,
        warnings=generated.warnings,
        style=req.style,
        created_at=datetime.now(UTC).isoformat(),
    )


@router.post(
    "/candidates/{candidate_id}/render-jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a background render job for a candidate clip",
)
async def create_render_job(
    candidate_id: str,
    payload: RenderRequest | None = None,
) -> JobResponse:
    """Enqueue local FFmpeg rendering (single worker, PRD FR-09/FR-10).

    The job validates FFmpeg/libass/encoders, generates captions, burns them
    in with an argument-array FFmpeg command, validates the output with
    ffprobe, and only then records success.
    """
    candidate, media = _get_candidate_or_404(candidate_id)
    req = payload or RenderRequest()

    # Bound the caption style safely (validation lives in the Pydantic model).
    style = req.style or CaptionStyleSettings()
    cfg = {
        "candidate_id": candidate.id,
        "layout": req.layout.value,
        "quality": req.quality.value,
        "caption_format": req.caption_format.value,
        "style": style.model_dump(),
        "overwrite": req.overwrite,
    }

    try:
        job = await job_manager.submit_job(
            project_id=media.project_id,
            job_type=JobType.RENDER.value,
            media_id=media.id,
            config=cfg,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

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


def _artifact_from_file(kind: str, path: Path) -> CaptionArtifact:
    """Build a bounded artifact descriptor for an existing file."""
    try:
        size = path.stat().st_size
        created = datetime.fromtimestamp(path.stat().st_ctime, tz=UTC).isoformat()
    except OSError:
        size, created = 0, datetime.now(UTC).isoformat()
    return CaptionArtifact(kind=kind, path=str(path), size_bytes=size, created_at=created)  # type: ignore[arg-type]


_KIND_BY_SUFFIX = {
    ".srt": "srt",
    ".ass": "ass",
    ".log": "render_log",
    ".config.json": "render_config",
}


@router.get(
    "/candidates/{candidate_id}/artifacts",
    response_model=CandidateArtifactsResponse,
    summary="List caption files and validated rendered outputs for a candidate",
)
async def list_candidate_artifacts(candidate_id: str) -> CandidateArtifactsResponse:
    """Enumerate this candidate's caption files and validated renders."""
    candidate, media = _get_candidate_or_404(candidate_id)
    project_dir = settings.get_project_dir(media.project_id)

    captions: list[CaptionArtifact] = []
    captions_dir = project_dir / "captions"
    if captions_dir.is_dir():
        for path in sorted(captions_dir.glob(f"{candidate.id}.*")):
            kind = _KIND_BY_SUFFIX.get(path.suffix.lower())
            if not kind or kind == "mp4":
                continue
            captions.append(_artifact_from_file(kind, path))

    rendered: list[CaptionArtifact] = []
    warnings: list[str] = []
    for record in renders_repo.list_candidate_renders(candidate.id):
        out_path = Path(record.output_path)
        if out_path.is_file():
            rendered.append(_artifact_from_file("mp4", out_path))
        else:
            warnings.append(f"Recorded render output is missing on disk: {record.output_path}")

    diag_dir = project_dir / "renders" / "logs"
    if diag_dir.is_dir():
        for path in sorted(diag_dir.iterdir()):
            if not path.is_file():
                continue
            kind = (
                "render_log"
                if path.suffix == ".log"
                else ("render_config" if path.name.endswith(".config.json") else None)
            )
            if kind:
                rendered.append(_artifact_from_file(kind, path))

    return CandidateArtifactsResponse(
        candidate_id=candidate.id,
        media_id=media.id,
        captions=captions,
        rendered_clips=rendered,
        warnings=warnings,
    )


@router.get(
    "/candidates/{candidate_id}/render-file",
    summary="Download or stream the validated rendered MP4 video file for a candidate",
)
def serve_candidate_render_file(
    candidate_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    """Stream or download the validated rendered Short for this candidate."""
    candidate, media = _get_candidate_or_404(candidate_id)
    renders = renders_repo.list_candidate_renders(candidate.id)
    out_path: Path | None = None
    if renders:
        for r in renders:
            p = Path(r.output_path)
            if p.is_file():
                out_path = p
                break

    if not out_path:
        project_dir = settings.get_project_dir(media.project_id)
        candidate_mp4 = project_dir / "renders" / f"{candidate.id}.mp4"
        if candidate_mp4.is_file():
            out_path = candidate_mp4

    if not out_path or not out_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No rendered video found for candidate '{candidate_id}'.",
        )

    allowed_root = settings.get_project_dir(media.project_id).resolve()
    resolved_path = out_path.resolve()
    if allowed_root != resolved_path and allowed_root not in resolved_path.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Render file path is outside the controlled project directory.",
        )

    size = resolved_path.stat().st_size
    from app.api.routes.media import (
        _STREAM_CHUNK_BYTES,
        _content_disposition_header,
        _parse_range_header,
    )

    range_status, start, end = _parse_range_header(range_header, size)

    download_name = f"{(candidate.title or candidate.id).replace(' ', '_')}.mp4"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition_header(download_name),
    }
    if range_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    length = end - start + 1

    def _stream():
        remaining = length
        with open(resolved_path, "rb") as handle:
            handle.seek(start)
            while remaining > 0:
                chunk = handle.read(min(_STREAM_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        _stream(),
        status_code=range_status,
        media_type="video/mp4",
        headers={
            **headers,
            "Content-Length": str(length),
        },
    )
