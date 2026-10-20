"""Preview-frame extraction service using local FFmpeg subprocess.

Extracts single JPEG frames (clip thumbnails) from source media with a fast
input seek (``-ss`` before ``-i``, so a long video's prefix is never decoded).
Follows the same safety rules as :mod:`app.services.media.audio`:

- Strict subprocess argument arrays (never shell=True)
- Finite per-invocation timeout and cooperative cancellation
- Bounded diagnostic logging (last 64 KB of stderr)
- No processing performed inside HTTP request handlers: extraction runs in
  background jobs only; serving routes stream already-generated files.
"""

import asyncio
import shutil
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.services.media.audio import (
    AudioExtractionError,
    JobCancelledError,
    _read_bounded_stream,
)

THUMBNAIL_WIDTH_PX = 160


def build_frame_extraction_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    at_ms: int,
    width: int = THUMBNAIL_WIDTH_PX,
    height: int | None = None,
) -> list[str]:
    """Argument array for grabbing one preview frame as JPEG.

    ``-ss`` before ``-i`` performs a fast input seek; ``-frames:v 1`` stops
    after the first decoded frame. Width/scale stays small (default 160 px)
    so thumbnails are light to serve and store.
    """
    sec = max(0, at_ms) / 1000.0
    filters = [f"scale={width}:-2"]
    if height is not None:
        filters = [f"scale={width}:{height}"]
    return [
        ffmpeg_bin,
        "-nostdin",
        "-y",
        "-ss",
        f"{sec:.6f}",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-vf",
        ",".join(filters),
        "-q:v",
        "5",
        str(output_path),
    ]


def get_candidate_thumbnail_path(project_id: str, media_id: str, candidate_id: str) -> Path:
    """Deterministic cache path for one candidate's thumbnail JPEG.

    Path components are reduced to safe basenames exactly like every other
    settings helper, so no client-controlled value can traverse directories.
    """
    thumbs_dir = settings.get_media_thumbs_dir(project_id, media_id)
    return thumbs_dir / f"cand_{Path(candidate_id).name}.jpg"


async def extract_preview_frame(
    input_path: Path,
    output_path: Path,
    at_ms: int,
    *,
    cancel_event: asyncio.Event | None = None,
    timeout_sec: float | None = None,
    ffmpeg_bin_override: str | None = None,
) -> Path:
    """Extract one preview frame from media into a JPEG file.

    Raises:
        AudioExtractionError: On missing FFmpeg binary, missing input, or
            subprocess failures/timeouts (error_code ``FRAME_EXTRACT_FAILED``).
        JobCancelledError: When ``cancel_event`` fires.
    """
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    ffmpeg_bin = ffmpeg_bin_override or shutil.which("ffmpeg")
    if not ffmpeg_bin or not Path(ffmpeg_bin).exists():
        raise AudioExtractionError(
            "FFmpeg is not installed or not found on system PATH. Please install ffmpeg.",
            error_code="FFMPEG_NOT_FOUND",
        )

    if not input_path.is_file():
        raise AudioExtractionError(
            f"Input media file does not exist at: {input_path}",
            error_code="INVALID_INPUT",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink(missing_ok=True)

    cmd = build_frame_extraction_command(ffmpeg_bin, input_path, output_path, at_ms)
    timeout = timeout_sec or float(settings.FFMPEG_TIMEOUT_SECONDS)

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_task = asyncio.create_task(_read_bounded_stream(proc.stderr))

        wait_proc_task = asyncio.create_task(proc.wait())
        tasks_to_watch: list[asyncio.Task] = [wait_proc_task]

        wait_cancel_task: asyncio.Task | None = None
        if cancel_event:
            wait_cancel_task = asyncio.create_task(cancel_event.wait())
            tasks_to_watch.append(wait_cancel_task)

        done, pending = await asyncio.wait(
            tasks_to_watch,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if wait_cancel_task:
            try:
                await wait_cancel_task
            except asyncio.CancelledError:
                pass

        if cancel_event and cancel_event.is_set():
            if proc.returncode is None:
                proc.kill()
            try:
                await proc.wait()
            except Exception:  # pragma: no cover - process reaping is best-effort
                pass
            raise JobCancelledError()

        if proc.returncode is None and not done:
            proc.kill()
            try:
                await proc.wait()
            except Exception:  # pragma: no cover - process reaping is best-effort
                pass
            raise AudioExtractionError(
                f"FFmpeg frame extraction timed out after {timeout:.0f}s.",
                error_code="FRAME_EXTRACT_TIMEOUT",
            )

        try:
            await proc.wait()
        except Exception:  # pragma: no cover - process reaping is best-effort
            pass

        stderr_text = await stderr_task

        if proc.returncode != 0 or not output_path.is_file():
            logger.warning(
                f"Frame extraction failed (rc={proc.returncode}); stderr: {stderr_text[:500]}"
            )
            raise AudioExtractionError(
                "FFmpeg could not extract a preview frame from the media.",
                error_code="FRAME_EXTRACT_FAILED",
                diagnostic_logs=stderr_text,
            )

        return output_path
    except AudioExtractionError:
        if proc and proc.returncode is None:
            proc.kill()
        raise
    except Exception as e:
        if proc and proc.returncode is None:
            proc.kill()
        raise AudioExtractionError(
            f"Failed to run FFmpeg frame extraction: {e}",
            error_code="FRAME_EXTRACT_FAILED",
        ) from e
