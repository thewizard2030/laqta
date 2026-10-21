"""Media query endpoints."""

import re
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.logging import logger
from app.db.repository import CandidateRepository, ProjectRepository
from app.schemas.media import (
    MediaAssetResponse,
    UrlIngestAcceptedResponse,
    UrlIngestRequest,
)
from app.services.media.thumbnails import get_candidate_thumbnail_path
from app.services.media.url_ingest import UrlIngestError

router = APIRouter()
repo = ProjectRepository()
candidates_repo = CandidateRepository()

_MEDIA_MIME_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_STREAM_CHUNK_BYTES = 256 * 1024


def _content_disposition_header(original_name: str) -> str:
    """Build a header-safe inline Content-Disposition (RFC 6266/5987).

    Starlette headers must be latin-1 encodable, so the plain ``filename=``
    fallback is stripped to printable ASCII; the original (possibly Arabic)
    name is preserved losslessly in the percent-encoded ``filename*=UTF-8''
    parameter that browsers prefer.
    """
    bare = Path(original_name).name or "media"
    filtered = "".join(
        c for c in bare if c.isascii() and c.isprintable() and c not in '"\\'
    ).strip()
    fallback = filtered or "media"
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(bare, safe='')}"


def _safe_media_path(media) -> Path:
    """Resolve a server-managed, contained media path (no client path input)."""
    if not media.safe_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media asset has no stored file path.",
        )
    path = Path(media.safe_path).resolve()
    allowed_root = settings.get_project_media_dir(media.project_id).resolve()
    if allowed_root != path and allowed_root not in path.parents:
        logger.warning("Blocked media file access outside project dir: %s", media.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Media file path is outside the controlled project directory.",
        )
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Media file no longer exists on disk for playback. The metadata "
                f"record '{media.id}' remains intact."
            ),
        )
    return path


def _parse_range_header(range_header: str | None, size: int) -> tuple[int, int, int]:
    """Parse a single-file Range header into (status, start, end).

    Bounded: only ``bytes=start-end`` form, values clamped inside [0, size),
    no multipart ranges. Malformed headers are ignored (full file returned).
    """
    if not range_header:
        return status.HTTP_200_OK, 0, size - 1
    match = _RANGE_RE.match(range_header.strip())
    if not match:
        return status.HTTP_200_OK, 0, size - 1
    raw_start, raw_end = match.groups()
    if raw_start == "" and raw_end == "":
        return status.HTTP_200_OK, 0, size - 1
    if raw_start == "":  # suffix range: last N bytes
        length = min(int(raw_end), size)
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
    if start >= size:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=f"Requested range starts beyond file size ({size} bytes).",
        )
    end = min(end, size - 1)
    if end < start:
        return status.HTTP_200_OK, 0, size - 1
    return status.HTTP_206_PARTIAL_CONTENT, start, end


@router.get(
    "/media/{media_id}/file",
    summary="Stream the local media file for in-app source preview (local-only)",
)
def serve_media_file(
    media_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    """Serve the user's own media file from the managed project directory.

    Local-only workflow support (user journey step 10: preview source time
    ranges): the path comes exclusively from the server-managed DB record and
    is contained within the project media dir. Byte-range requests are honored
    so <video> seeking works; requests never leave 127.0.0.1.
    """
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )
    path = _safe_media_path(media)
    size = path.stat().st_size
    range_status, start, end = _parse_range_header(range_header, size)

    mime = _MEDIA_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition_header(media.original_name),
    }
    if range_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    length = end - start + 1

    def _stream():
        remaining = length
        with open(path, "rb") as handle:
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
        media_type=mime,
        headers={
            **headers,
            "Content-Length": str(length),
        },
    )


@router.get(
    "/media/{media_id}",
    response_model=MediaAssetResponse,
    summary="Get media asset by ID",
)
async def get_media(media_id: str) -> MediaAssetResponse:
    """Retrieve media asset details including probed video/audio metadata."""
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )
    return MediaAssetResponse(
        id=media.id,
        project_id=media.project_id,
        original_name=media.original_name,
        size_bytes=media.size_bytes,
        duration_ms=media.duration_ms,
        width=media.width,
        height=media.height,
        video_codec=media.video_codec,
        audio_codec=media.audio_codec,
        status=media.status,
        created_at=media.created_at,
    )


@router.get(
    "/media/{media_id}/candidates/{candidate_id}/thumbnail",
    summary="Serve a pre-extracted candidate preview frame",
)
def get_candidate_thumbnail(media_id: str, candidate_id: str) -> FileResponse:
    """Stream a candidate's cached JPEG preview frame.

    This route never extracts anything itself: thumbnail frames are generated
    exclusively by ``candidate_thumbnails`` background jobs, keeping FFmpeg
    media processing out of request handlers. When no frame has been generated
    yet the response is a clear 404 and the UI shows its placeholder.
    """
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )

    candidate = candidates_repo.get_candidate(candidate_id)
    if not candidate or candidate.media_id != media_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found for this media asset.",
        )

    thumb_path = get_candidate_thumbnail_path(media.project_id, media_id, candidate_id)
    if not thumb_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Thumbnail not generated yet. It is produced by the "
                "'candidate_thumbnails' background job after clip generation."
            ),
        )

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


@router.post(
    "/media/url",
    response_model=UrlIngestAcceptedResponse,
    status_code=202,
    summary="Queue a gated URL ingestion background job (PRD FR-12)",
)
async def ingest_media_from_url(payload: UrlIngestRequest) -> UrlIngestAcceptedResponse:
    """Queue a yt-dlp download into a project as a background job.

    Fail-closed gating, in explicit order — every refusal is a clear error:
    1. ``QATTA_ENABLE_URL_INGESTION`` must be enabled locally. It ships
       disabled (fail-closed): an operator has to opt in explicitly with
       ``QATTA_ENABLE_URL_INGESTION=true``.
    2. yt-dlp must be installed locally.
    3. The user must have confirmed content rights for THIS import.
    4. The URL must be a public http(s) resource (SSRF-guarded).
    The running job still requires the same settings; no download ever starts
    from a mere HTTP request with the flag disabled.
    """
    from app.jobs.manager import job_manager
    from app.schemas.jobs import JobType
    from app.services.media.url_ingest import (
        detect_yt_dlp,
        validate_public_http_url,
    )

    if not settings.ENABLE_URL_INGESTION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "URL ingestion is disabled on this machine "
                "(QATTA_ENABLE_URL_INGESTION=false). Set it to true to "
                "enable it."
            ),
        )

    if not payload.rights_confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This import was refused because content rights were not "
                "explicitly confirmed. Only import videos you own or have "
                "permission to process."
            ),
        )

    capability = detect_yt_dlp()
    if not capability.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "yt-dlp is not installed on this machine. URL ingestion is "
                "gated and requires the local yt-dlp binary."
            ),
        )

    try:
        validated_url = validate_public_http_url(payload.url)
    except UrlIngestError as e:
        code = status.HTTP_400_BAD_REQUEST
        if e.error_code == "URL_FORBIDDEN_HOST":
            code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=e.message) from e

    project = repo.get_project(payload.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{payload.project_id}' not found.",
        )

    media_dir = settings.get_project_media_dir(payload.project_id)
    if not settings.check_available_space(media_dir, required_bytes=50 * 1024 * 1024):
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Insufficient local disk space available for media import.",
        )

    try:
        job = await job_manager.submit_job(
            project_id=payload.project_id,
            job_type=JobType.URL_INGESTION.value,
            config={"url": validated_url, "rights_confirmed": True},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    hostname = urlparse(validated_url).hostname or ""
    return UrlIngestAcceptedResponse(
        job_id=job.id,
        status="queued",
        url_host=hostname,
    )
