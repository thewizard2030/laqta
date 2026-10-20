"""Audio extraction service using local FFmpeg subprocess.

Extracts mono 16 kHz WAV audio required for transcription.
Operates with strict subprocess argument arrays (no shell=True),
finite timeouts, cancellation support, and bounded diagnostic logging.
"""

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger


class AudioExtractionError(Exception):
    """Exception raised when audio extraction fails."""

    def __init__(
        self,
        message: str,
        error_code: str = "FFMPEG_ERROR",
        diagnostic_logs: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.diagnostic_logs = diagnostic_logs


class JobCancelledError(AudioExtractionError):
    """Exception raised when a job is cancelled by user request."""

    def __init__(self, message: str = "Job was cancelled by user request."):
        super().__init__(message, error_code="CANCELLED")


def build_audio_extraction_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    progress: bool = False,
) -> list[str]:
    """Construct explicit subprocess argument array for 16 kHz mono WAV extraction.

    Uses:
    - -vn: disable video recording
    - -acodec pcm_s16le: 16-bit little-endian PCM WAV
    - -ac 1: single channel (mono)
    - -ar 16000: 16 kHz sampling rate (Whisper standard)

    With ``progress=True`` ffmpeg reports real ``out_time`` machine progress
    on stdout (parsed by :func:`extract_audio_16k`), so the UI percent is a
    measured fraction rather than a static placeholder.
    """
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if progress:
        cmd += ["-nostats", "-progress", "pipe:1", "-loglevel", "error"]
    cmd.append(str(output_path))
    return cmd


def build_clip_audio_extraction_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    start_ms: int,
    duration_ms: int,
) -> list[str]:
    """Argument array for extracting one bounded clip's audio as 16 kHz mono WAV.

    ``-ss`` before ``-i`` performs a fast input seek (never decoding the
    whole prefix of a long video); ffmpeg corrects to the requested time
    using packet timestamps, so word-level re-timing error stays within a
    few tens of milliseconds for typical MP4/MKV audio encodings.
    """
    return [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{max(0, start_ms) / 1000.0:.6f}",
        "-t",
        f"{max(1, duration_ms) / 1000.0:.6f}",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]


async def _read_bounded_stream(stream: asyncio.StreamReader | None, max_bytes: int = 65536) -> str:
    """Read stream in chunks and keep at most the last `max_bytes` to prevent unbounded memory."""
    if stream is None:
        return ""
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes * 2:
                combined = b"".join(chunks)
                chunks = [combined[-max_bytes:]]
                total = len(chunks[0])
    except Exception:
        pass
    combined = b"".join(chunks)
    if len(combined) > max_bytes:
        combined = combined[-max_bytes:]
    return combined.decode("utf-8", errors="replace")


async def _read_progress_stream(
    stream: asyncio.StreamReader | None,
    total_duration_ms: int,
    progress_callback: Callable[[float, str], None],
) -> None:
    """Parse ffmpeg `-progress pipe:1` output into truthful percent updates.

    ffmpeg emits `key=value` lines; `out_time_ms` (microseconds, despite the
    name) is compared against the known media duration. Callback fires at
    most when the reported percent moves by >= 1 point. The stream itself is
    discarded (never buffered) so memory stays constant.
    """
    if stream is None or total_duration_ms <= 0:
        return
    scale = 1000.0 / float(total_duration_ms)  # out_time_ms is microseconds
    last_pct = -1.0
    try:
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("ascii", errors="replace").strip()
            if text.startswith("out_time_ms=") or text.startswith("out_time_us="):
                try:
                    out_time_us = int(text.split("=", 1)[1])
                except ValueError:
                    continue
                pct = min(95.0, max(0.0, out_time_us * scale / 1000.0))
                if pct > last_pct + 1.0:
                    last_pct = pct
                    progress_callback(pct, "extracting_audio")
    except Exception:
        pass


async def extract_audio_16k(
    input_path: Path,
    output_path: Path,
    cancel_event: asyncio.Event | None = None,
    timeout_sec: float | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    ffmpeg_bin_override: str | None = None,
    total_duration_ms: int | None = None,
) -> Path:
    """Extract mono 16 kHz WAV audio from input media using local FFmpeg.

    Args:
        input_path: Safe path to input media asset.
        output_path: Safe target path for 16 kHz mono WAV.
        cancel_event: Optional asyncio Event to trigger immediate cooperative cancellation.
        timeout_sec: Maximum execution time in seconds. Defaults to settings.FFMPEG_TIMEOUT_SECONDS.
        progress_callback: Optional callback for reporting progress (progress_pct, stage).
        ffmpeg_bin_override: Optional path to FFmpeg binary (useful for testing missing binary).

    Returns:
        Path to extracted WAV audio file.

    Raises:
        AudioExtractionError: On FFmpeg failures, missing binary, or timeouts.
        JobCancelledError: When cancel_event is triggered.
    """
    # 1. Early cancellation check
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    # 2. Check binary existence
    ffmpeg_bin = ffmpeg_bin_override or shutil.which("ffmpeg")
    if not ffmpeg_bin or not Path(ffmpeg_bin).exists():
        raise AudioExtractionError(
            "FFmpeg is not installed or not found on system PATH. Please install ffmpeg.",
            error_code="FFMPEG_NOT_FOUND",
        )

    # 3. Check input file exists
    if not input_path.is_file():
        raise AudioExtractionError(
            f"Input media file does not exist at: {input_path}",
            error_code="INVALID_INPUT",
        )

    # 4. Prepare target directory
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink(missing_ok=True)

    cmd = build_audio_extraction_command(ffmpeg_bin, input_path, output_path)
    # Real percent reporting is only enabled when both a callback and a
    # known total duration are provided; otherwise the static 10/100 markers
    # below remain (an honest indeterminate state).
    stream_progress = bool(progress_callback and total_duration_ms and total_duration_ms > 0)
    cmd = build_audio_extraction_command(
        ffmpeg_bin, input_path, output_path, progress=stream_progress
    )
    logger.info(f"Extracting audio: {' '.join(cmd)}")

    if progress_callback:
        progress_callback(10.0, "extracting_audio")

    # 5. Execute subprocess without shell=True
    timeout = timeout_sec or float(settings.FFMPEG_TIMEOUT_SECONDS)
    proc: asyncio.subprocess.Process | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=(asyncio.subprocess.PIPE if stream_progress else asyncio.subprocess.DEVNULL),
            stderr=asyncio.subprocess.PIPE,
        )

        progress_task: asyncio.Task | None = None
        if stream_progress:
            progress_task = asyncio.create_task(
                _read_progress_stream(proc.stdout, int(total_duration_ms), progress_callback)
            )
        stderr_task = asyncio.create_task(_read_bounded_stream(proc.stderr))

        # Wait with cancellation check and timeout
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

        # Cancel remaining watcher tasks
        for t in pending:
            t.cancel()

        # Check timeout
        if not done:
            _terminate_process(proc)
            await stderr_task
            _cleanup_partial_file(output_path)
            raise AudioExtractionError(
                f"Audio extraction timed out after {timeout} seconds.",
                error_code="TIMEOUT",
            )

        # Check cancellation
        if wait_cancel_task and wait_cancel_task in done and cancel_event.is_set():
            _terminate_process(proc)
            await stderr_task
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            _cleanup_partial_file(output_path)
            raise JobCancelledError()

        # Process exited
        return_code = proc.returncode
        stderr_output = await stderr_task
        if progress_task:
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

        if return_code != 0:
            _cleanup_partial_file(output_path)
            # Safe diagnostic details: bounded stderr
            diagnostic_snippet = (
                stderr_output.strip()[-1000:] if stderr_output else f"Exit code {return_code}"
            )
            logger.error(
                f"FFmpeg audio extraction failed (code {return_code}): {diagnostic_snippet}"
            )
            raise AudioExtractionError(
                f"FFmpeg extraction failed (code {return_code}): {diagnostic_snippet}",
                error_code="FFMPEG_ERROR",
                diagnostic_logs=stderr_output,
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            _cleanup_partial_file(output_path)
            raise AudioExtractionError(
                "Extracted audio file is missing or zero bytes.",
                error_code="FFMPEG_EMPTY_OUTPUT",
            )

        if progress_callback:
            progress_callback(100.0, "completed")

        out_size = output_path.stat().st_size
        logger.info(f"Audio extraction succeeded: {output_path} ({out_size} bytes)")
        return output_path

    except (AudioExtractionError, JobCancelledError):
        raise
    except Exception as e:
        if proc:
            _terminate_process(proc)
        _cleanup_partial_file(output_path)
        logger.error(f"Unexpected error during audio extraction: {e}")
        raise AudioExtractionError(
            f"Unexpected audio extraction failure: {e}",
            error_code="INTERNAL_ERROR",
        ) from e


async def extract_clip_audio_16k(
    input_path: Path,
    output_path: Path,
    start_ms: int,
    duration_ms: int,
    cancel_event: asyncio.Event | None = None,
    timeout_sec: float | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    ffmpeg_bin_override: str | None = None,
) -> Path:
    """Extract one bounded clip (start_ms .. start_ms+duration_ms) as 16 kHz
    mono WAV for Pass B clip re-timing.

    Identical safety model to :func:`extract_audio_16k` (arg array, timeout,
    cancellation, partial-file cleanup) but bounded by the clip duration, so
    a long source video never blocks this stage.
    """
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

    cmd = build_clip_audio_extraction_command(
        ffmpeg_bin, input_path, output_path, start_ms, duration_ms
    )
    logger.info(f"Extracting clip audio: {' '.join(cmd)}")
    if progress_callback:
        progress_callback(10.0, "extracting_clip_audio")

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
        tasks_to_watch = [wait_proc_task]
        wait_cancel_task: asyncio.Task | None = None
        if cancel_event:
            wait_cancel_task = asyncio.create_task(cancel_event.wait())
            tasks_to_watch.append(wait_cancel_task)

        done, pending = await asyncio.wait(
            tasks_to_watch, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

        if not done:
            _terminate_process(proc)
            await stderr_task
            _cleanup_partial_file(output_path)
            raise AudioExtractionError(
                f"Clip audio extraction timed out after {timeout} seconds.",
                error_code="TIMEOUT",
            )
        if wait_cancel_task and wait_cancel_task in done and cancel_event.is_set():
            _terminate_process(proc)
            await stderr_task
            _cleanup_partial_file(output_path)
            raise JobCancelledError()

        return_code = proc.returncode
        stderr_output = await stderr_task
        if return_code != 0:
            _cleanup_partial_file(output_path)
            diagnostic_snippet = (
                stderr_output.strip()[-1000:] if stderr_output else f"Exit code {return_code}"
            )
            raise AudioExtractionError(
                f"FFmpeg clip extraction failed (code {return_code}): {diagnostic_snippet}",
                error_code="FFMPEG_ERROR",
                diagnostic_logs=stderr_output,
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            _cleanup_partial_file(output_path)
            raise AudioExtractionError(
                "Extracted clip audio is missing or zero bytes; the requested "
                "clip may lie beyond the end of the source media.",
                error_code="FFMPEG_EMPTY_OUTPUT",
            )
        if progress_callback:
            progress_callback(100.0, "completed")
        return output_path
    except (AudioExtractionError, JobCancelledError):
        raise
    except Exception as e:
        if proc:
            _terminate_process(proc)
        _cleanup_partial_file(output_path)
        logger.error(f"Unexpected error during clip audio extraction: {e}")
        raise AudioExtractionError(
            f"Unexpected clip audio extraction failure: {e}",
            error_code="INTERNAL_ERROR",
        ) from e


def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Safely terminate a subprocess with escalation to SIGKILL."""
    try:
        if proc.returncode is None:
            proc.terminate()
            # Give short grace period before killing
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    except Exception:
        pass


def _cleanup_partial_file(path: Path) -> None:
    """Safely clean up incomplete or failed output file."""
    try:
        if path.exists():
            path.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Failed to remove partial audio file {path}: {e}")


def clean_intermediate_audio(output_path: Path) -> bool:
    """Remove intermediate WAV file if cleanup is configured.

    Guarantees safety:
    - Never deletes original media files.
    - Only deletes files with .wav extension situated in temp directories.
    """
    if not settings.CLEAN_INTERMEDIATE_WAV:
        return False

    try:
        # Strict validation: must be inside a temp directory and have .wav suffix
        resolved = output_path.resolve()
        if "temp" in resolved.parts and resolved.suffix.lower() == ".wav" and resolved.exists():
            resolved.unlink(missing_ok=True)
            logger.info(f"Cleaned intermediate WAV file: {resolved}")
            return True
    except Exception as e:
        logger.warning(f"Failed to clean intermediate audio {output_path}: {e}")
    return False
