"""Bounded, local-only frame sampling for the reframe stage.

One FFmpeg invocation extracts evenly spaced JPEG frames from a clip span into
a caller-owned directory. Nothing is uploaded, no model is downloaded, and the
process is a plain argument array: no shell, no string interpolation of media
paths or transcript text.

Why a separate sampler instead of decoding in Python: FFmpeg already seeks and
scales faster than a Python loop over decoded frames, and it keeps the memory
footprint flat (a 2-hour source is never held in RAM — only one clip span is
read, and only ``max_frames`` images are written).

Cancellation is checked *before* the extraction starts. The extraction itself
is a single bounded subprocess, so there is no mid-run polling; that matches
the pipeline's documented rule that cancellation happens at stage boundaries
and is never claimed to be instant.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Sampling defaults. Five frames per second is the rate the camera solver was
# written against; more only costs CPU, because the solver's deadband logic
# averages over seconds, not frames.
DEFAULT_SAMPLE_FPS = 5.0
# 600 frames = two minutes at 5 FPS. Longer clips keep the first 600 frames
# rather than growing without bound; the caller can raise the cap explicitly.
DEFAULT_MAX_FRAMES = 600
# Frames are written at 320 px wide. Haar detection is area-bound, and the
# solver only needs face position, not detail.
SAMPLE_WIDTH = 320
FRAME_PATTERN = "frame_%05d.jpg"
DEFAULT_TIMEOUT_SECONDS = 120.0
# A guard, not a feature: asking for more than 30 FPS for face tracking is a
# configuration mistake, and it would multiply the frame count for no gain.
MAX_SAMPLE_FPS = 30.0
# Bounded diagnostics: enough to see the real ffmpeg complaint, never a log.
_STDERR_TAIL = 500


class FrameSamplingError(RuntimeError):
    """Raised when frames cannot be extracted, with an actionable reason."""


class SamplingCancelledError(FrameSamplingError):
    """Raised when sampling is asked to start after cancellation was requested."""


@dataclass(frozen=True)
class SampledFrame:
    """One extracted frame on disk, with its nominal timestamp in the source."""

    path: Path
    timestamp_ms: int


def build_sample_command(
    *,
    ffmpeg_bin: str,
    input_path: Path,
    out_dir: Path,
    start_ms: int,
    end_ms: int,
    fps: float = DEFAULT_SAMPLE_FPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> list[str]:
    """Build the FFmpeg argument array for one sampling run.

    Pure function: no subprocess runs here, so the exact argv is unit-testable
    and reproducible. ``-ss`` before ``-i`` is input seeking (fast and keyframe
    aligned); ``-t`` bounds the read so a long source is never scanned whole.
    """
    if start_ms < 0:
        raise FrameSamplingError(f"start_ms must be >= 0, got {start_ms}.")
    if end_ms <= start_ms:
        raise FrameSamplingError(f"end_ms ({end_ms}) must be greater than start_ms ({start_ms}).")
    if not 0.0 < fps <= MAX_SAMPLE_FPS:
        raise FrameSamplingError(f"fps must be in (0, {MAX_SAMPLE_FPS:g}], got {fps}.")
    if max_frames < 1:
        raise FrameSamplingError(f"max_frames must be >= 1, got {max_frames}.")

    duration_ms = end_ms - start_ms
    return [
        ffmpeg_bin,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_ms / 1000.0:.3f}",
        "-i",
        str(input_path),
        "-t",
        f"{duration_ms / 1000.0:.3f}",
        "-vf",
        f"fps={fps:g},scale={SAMPLE_WIDTH}:-2",
        "-frames:v",
        str(max_frames),
        "-q:v",
        "3",
        str(Path(out_dir) / FRAME_PATTERN),
    ]


def sample_frames(
    *,
    ffmpeg_bin: str,
    input_path: Path,
    out_dir: Path,
    start_ms: int,
    end_ms: int,
    fps: float = DEFAULT_SAMPLE_FPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cancel_event: Any | None = None,
) -> list[SampledFrame]:
    """Extract frames for ``[start_ms, end_ms)`` into ``out_dir``.

    Returns frames sorted by filename, with nominal timestamps derived from the
    frame index and ``fps``. Those timestamps bucket observations into shots;
    they are not a substitute for decoded presentation timestamps.

    Raises :class:`FrameSamplingError` for every failure mode, with the real
    ffmpeg message (bounded) where one exists.
    """
    if timeout_seconds <= 0:
        raise FrameSamplingError(f"timeout_seconds must be > 0, got {timeout_seconds}.")
    if cancel_event is not None and cancel_event.is_set():
        raise SamplingCancelledError(
            "Cancelled before frame sampling started; no frames were extracted."
        )

    source = Path(input_path)
    if not source.is_file():
        raise FrameSamplingError(f"Input media does not exist: {source}")

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    # A reused directory must not mix frames from a previous clip: the
    # filename counter restarts at 00001, so stale files would be silently
    # attributed to this clip.
    for stale in target.glob("frame_*.jpg"):
        try:
            stale.unlink()
        except OSError:
            pass

    cmd = build_sample_command(
        ffmpeg_bin=ffmpeg_bin,
        input_path=source,
        out_dir=target,
        start_ms=start_ms,
        end_ms=end_ms,
        fps=fps,
        max_frames=max_frames,
    )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FrameSamplingError(
            f"Frame sampling timed out after {timeout_seconds:g}s for "
            f"{source.name} [{start_ms}..{end_ms}] ms."
        ) from exc
    except OSError as exc:
        raise FrameSamplingError(f"Could not run ffmpeg for frame sampling: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-_STDERR_TAIL:]
        raise FrameSamplingError(f"ffmpeg frame sampling failed (code {proc.returncode}): {detail}")

    frames = sorted(target.glob("frame_*.jpg"))
    if not frames:
        raise FrameSamplingError(
            f"ffmpeg produced no frames for {source.name} "
            f"[{start_ms}..{end_ms}] ms; check that the span is inside the media."
        )

    return [
        SampledFrame(
            path=frame,
            # Nominal position of frame i: the fps filter emits them evenly
            # from the seek point.
            timestamp_ms=start_ms + int(round(index * 1000.0 / fps)),
        )
        for index, frame in enumerate(frames)
    ]


@contextmanager
def temporary_sample_dir(parent: Path) -> Iterator[Path]:
    """A private directory for one clip's frames, removed on exit.

    ``tempfile.mkdtemp`` creates it mode 0700, so frames from a private
    recording are not readable by other local users while they exist.
    """
    base = Path(parent)
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="qatta-frames-", dir=str(base)))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
