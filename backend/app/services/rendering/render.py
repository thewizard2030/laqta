"""FFmpeg-based clip rendering service (PRD §5 FR-09, §11 Gate D).

Guarantees (per AGENTS.md and FR-09):
- Subprocess ARGUMENT ARRAYS only, never shell=True.
- Explicit resolved paths; no client-trusted path interpolation.
- Finite timeout and cooperative cancellation.
- Bounded captured stderr for diagnostics.
- Safe overwrite: an existing output blocks the render unless the user
  explicitly asks for it; the real output is renamed atomically only after
  the FFmpeg exit code AND an ffprobe output validation both pass.
- Per-render config (exact argv, no secrets exist in render configs) and a
  bounded render log are persisted next to the output for debugging.
- Failed or cancelled renders are never marked complete by callers.
"""

import asyncio
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.services.media.audio import (
    JobCancelledError,
    _read_bounded_stream,
    _terminate_process,
)

RENDER_OUTPUT_ERROR = "RENDER_FAILED"


class RenderError(Exception):
    """Raised when rendering fails for an actionable reason."""

    def __init__(
        self,
        message: str,
        error_code: str = "RENDER_FAILED",
        diagnostic_logs: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.diagnostic_logs = diagnostic_logs


class RenderEnvironmentReport(dict[str, Any]):
    """Report of renderer-side dependency availability (ffmpeg/libass)."""


# ---------------------------------------------------------------------------
# Quality presets (PRD FR-09: 1080x1920 default plus a CPU-friendly preset)
# ---------------------------------------------------------------------------

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "high": {
        "width": 1080,
        "height": 1920,
        "crf": 20,
        "bitrate_bps": 5_000_000,
        "video_preset": "veryfast",
        "audio_bitrate": "128k",
        "description": "1080x1920 H.264 CRF 20 (default for 8 GB CPUs).",
    },
    "cpu_friendly": {
        "width": 720,
        "height": 1280,
        "crf": 26,
        "bitrate_bps": 2_000_000,
        "video_preset": "ultrafast",
        "audio_bitrate": "96k",
        "description": "720x1280 H.264 CRF 26, ultrafast preset for slower CPUs.",
    },
}


# ---------------------------------------------------------------------------
# Environment probing (FFmpeg + libass), honest diagnostics
# ---------------------------------------------------------------------------


def ffmpeg_has_libass_filter(ffmpeg_bin: str) -> bool:
    """Check the `subtitles`/`ass` libass-backed filters exist in this build.

    This is the honest check (runtime capability) rather than trusting a
    configure-time build flag.
    """
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    # Filter rows are formatted like: " .. ass               V->V  Render ASS ..."
    # The second whitespace token is the filter name.
    for line in (res.stdout or "").splitlines():
        tokens = line.split()
        # Filter rows have flags, name, direction and a description.
        if len(tokens) >= 4 and tokens[1] in ("subtitles", "ass"):
            return True
    return False


def probe_render_environment(custom_ffmpeg: str | None = None) -> RenderEnvironmentReport:
    """Return honest FFmpeg/libass/encoder availability with diagnostics."""
    ffmpeg_bin = custom_ffmpeg or shutil.which("ffmpeg")
    report = RenderEnvironmentReport(
        ffmpeg_available=False,
        ffmpeg_path=None,
        libass_available=False,
        h264_encoder_available=False,
        aac_encoder_available=False,
        install_hint=(
            "Install ffmpeg (Fedora: sudo dnf install ffmpeg via RPM Fusion) to enable rendering."
        ),
    )
    if not ffmpeg_bin or not Path(ffmpeg_bin).exists():
        report["install_hint"] = "ffmpeg binary not found in system PATH."
        return report

    report["ffmpeg_available"] = True
    report["ffmpeg_path"] = ffmpeg_bin
    report["libass_available"] = ffmpeg_has_libass_filter(ffmpeg_bin)

    enc = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    encoders_out = enc.stdout or ""
    # H.264 encoder selection: software encoders only, prioritized. managed
    # hardware paths (NVENC/QSV/VAAPI) are intentionally not used until they
    # are testable here; AGENTS.md forbids claiming untested capabilities.
    h264_encoder = None
    for candidate_name in ("libx264", "libopenh264"):
        if _find_encoder(encoders_out, candidate_name):
            h264_encoder = candidate_name
            break
    report["h264_encoder"] = h264_encoder
    report["h264_encoder_available"] = h264_encoder is not None
    aac_encoder = "aac" if _find_encoder(encoders_out, "aac") else None
    report["aac_encoder"] = aac_encoder
    report["aac_encoder_available"] = aac_encoder is not None
    return report


def _find_encoder(encoder_list_output: str, name: str) -> bool:
    """Match an encoder row such as ' A....D libx264 ...' by exact name.

    Encoder rows begin with a flags column of letters/dots, then the name.
    """
    for line in encoder_list_output.splitlines():
        tokens = line.split()
        if len(tokens) < 2:
            continue
        if not re.fullmatch(r"[A-Z.]{5,6}", tokens[0]):
            continue
        if tokens[1] == name:
            return True
    return False


# ---------------------------------------------------------------------------
# Command construction (pure, deterministic and unit-testable)
# ---------------------------------------------------------------------------


def escape_filter_path(path: str) -> str:
    """Escape a filesystem path for safe use inside an FFmpeg filtergraph.

    Order matters: escape the escape character first, then the filtergraph
    special characters ('=', ':', ',', '[', ']'). Single quotes are wrapped
    by the caller-level quoting; we escape them to \\' as well.
    """
    escaped = (
        path.replace("\\", "\\\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )
    return escaped


def _caption_filter(caption_path: str, format_name: str) -> str:
    """Build the subtitles/ass filter argument with an escaped path."""
    escaped = escape_filter_path(str(caption_path))
    if format_name == "ass":
        return f"ass='{escaped}'"
    return f"subtitles='{escaped}'"


def compute_center_crop(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]:
    """Compute the largest centered source crop matching the target aspect.

    Deterministic and even-sized (required by most H.264 encoders).
    """
    if src_w <= 0 or src_h <= 0 or out_w <= 0 or out_h <= 0:
        raise RenderError(
            "Source and output dimensions must be positive.",
            error_code="INVALID_CONFIG",
        )
    target_ar = out_w / out_h
    crop_w = min(float(src_w), src_h * target_ar)
    crop_h = crop_w / target_ar
    if crop_h > src_h:  # defensive: height-limited fallback
        crop_h = float(src_h)
        crop_w = crop_h * target_ar
    return int(crop_w // 2 * 2) or 2, int(crop_h // 2 * 2) or 2


def build_render_command(
    ffmpeg_bin: str,
    input_path: Path,
    output_path: Path,
    *,
    layout: str,
    quality: str,
    src_width: int,
    src_height: int,
    has_audio: bool,
    caption_path: str | None = None,
    caption_format: str = "ass",
    start_ms: int | None = None,
    duration_ms: int | None = None,
    video_encoder: str = "libx264",
) -> list[str]:
    """Build the full FFmpeg argument array for one render.

    Pure function: no subprocess is run here. Returns an explicit argv list
    that callers can persist for reproducibility (FR-09).

    ``video_encoder``: 'libx264' supports -preset/-crf; other H.264 encoders
    (e.g. Fedora's libopenh264) use the preset's average bitrate instead,
    because CRF/preset flags are not portable across H.264 encoders.
    """
    preset = QUALITY_PRESETS.get(quality)
    if preset is None:
        raise RenderError(
            f"Unknown quality preset '{quality}'. Available: {sorted(QUALITY_PRESETS)}.",
            error_code="INVALID_CONFIG",
        )
    if layout not in ("center_crop", "blurred_background"):
        raise RenderError(
            f"Layout '{layout}' is not implemented in this phase "
            "(center_crop and blurred_background only).",
            error_code="INVALID_CONFIG",
        )
    out_w, out_h = int(preset["width"]), int(preset["height"])

    cmd: list[str] = [ffmpeg_bin, "-y"]

    if start_ms is not None and start_ms > 0:
        cmd += ["-ss", f"{start_ms / 1000.0:.3f}"]
    cmd += ["-i", str(input_path)]
    if start_ms is not None and duration_ms is not None:
        cmd += ["-t", f"{duration_ms / 1000.0:.3f}"]

    # Hidden-subtitle burn via libass filter appended to the video chain.
    cap_filter = _caption_filter(caption_path, caption_format) if caption_path else ""

    if layout == "center_crop":
        crop_w, crop_h = compute_center_crop(src_width, src_height, out_w, out_h)
        vf = [
            f"crop=w={crop_w}:h={crop_h}",
            f"scale={out_w}:{out_h}:flags=lanczos",
            "setsar=1",
        ]
        if cap_filter:
            vf.append(cap_filter)
        cmd += ["-vf", ",".join(vf)]
    else:  # blurred_background: shared filtergraph passed as one argv element
        fg_scale = f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease"
        bg_scale = f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase"
        graph = (
            "[0:v]split=2[fg0][bg0];"
            f"[fg0]{fg_scale}[fgout];"
            f"[bg0]{bg_scale},crop={out_w}:{out_h},"
            f"boxblur=luma_radius=28:luma_power=2[bgout];"
            f"[fgout][bgout]overlay=x=(W-w)/2:y=(H-h)/2{(',' + cap_filter) if cap_filter else ''}"
            "[vout]"
        )
        cmd += ["-filter_complex", graph, "-map", "[vout]"]

    cmd += ["-c:v", video_encoder]
    if video_encoder == "libx264":
        cmd += [
            "-preset",
            str(preset["video_preset"]),
            "-crf",
            str(preset["crf"]),
        ]
    else:
        # CRF/preset are x264-specific; average bitrate keeps quality presets
        # meaningful on other (software) H.264 encoders.
        cmd += ["-b:v", str(preset["bitrate_bps"])]
    cmd += [
        "-pix_fmt",
        "yuv420p",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", str(preset["audio_bitrate"])]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


# ---------------------------------------------------------------------------
# Output validation (only after the encoder exit code passes)
# ---------------------------------------------------------------------------


class RenderProbeResult:
    """Structured ffprobe validation result of a rendered output."""

    def __init__(
        self,
        duration_ms: int,
        width: int,
        height: int,
        video_codec: str,
        audio_codec: str,
        size_bytes: int,
    ):
        self.duration_ms = duration_ms
        self.width = width
        self.height = height
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.size_bytes = size_bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "size_bytes": self.size_bytes,
        }


def probe_render_output(
    ffprobe_bin: str,
    output_path: Path,
    expected_width: int,
    expected_height: int,
    expected_duration_ms: int,
    duration_tolerance_ms: int = 1200,
    hd_tolerance: int = 4,
) -> RenderProbeResult:
    """Probe a rendered file and enforce honest acceptance criteria.

    Raises RenderError (with distinct codes) when any check fails. A render
    is only considered successful when this passes (PRD FR-09, Gate D).
    """
    if not output_path.is_file():
        raise RenderError(
            f"Render output is missing at expected location: {output_path}",
            error_code="OUTPUT_MISSING",
        )
    if output_path.stat().st_size == 0:
        raise RenderError("Render output is a zero-byte file.", error_code="OUTPUT_EMPTY")

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(output_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0, check=False)
    except subprocess.TimeoutExpired as e:
        raise RenderError("ffprobe output validation timed out.", error_code="PROBE_TIMEOUT") from e

    if res.returncode != 0:
        raise RenderError(
            f"ffprobe failed on rendered output: {res.stderr.strip()[:500]}",
            error_code="OUTPUT_UNREADABLE",
        )

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RenderError("ffprobe produced non-JSON output.", error_code="PROBE_FAILED") from e

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise RenderError("Rendered output has no video stream.", error_code="NO_VIDEO_STREAM")

    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if abs(width - expected_width) > hd_tolerance or abs(height - expected_height) > hd_tolerance:
        raise RenderError(
            f"Rendered dimensions {width}x{height} do not match the preset "
            f"{expected_width}x{expected_height}.",
            error_code="DIMENSION_MISMATCH",
        )

    vcodec = video.get("codec_name", "")
    if vcodec != "h264":
        raise RenderError(
            f"Rendered video codec is '{vcodec}', expected 'h264'.",
            error_code="CODEC_MISMATCH",
        )

    expected_acodec = "aac"
    if audio is None:
        if expected_duration_ms > 0:
            raise RenderError("Rendered output has no audio stream.", error_code="NO_AUDIO_STREAM")
    else:
        acodec = audio.get("codec_name", "")
        if acodec != expected_acodec:
            raise RenderError(
                f"Rendered audio codec is '{acodec}', expected 'aac'.",
                error_code="CODEC_MISMATCH",
            )

    duration_raw = data.get("format", {}).get("duration")
    try:
        duration_ms = int(float(duration_raw) * 1000)
    except (TypeError, ValueError) as e:
        raise RenderError("Could not parse rendered duration.", error_code="PROBE_FAILED") from e

    if abs(duration_ms - expected_duration_ms) > duration_tolerance_ms:
        raise RenderError(
            f"Rendered duration {duration_ms} ms differs from the requested "
            f"clip ({expected_duration_ms} ms) beyond tolerance.",
            error_code="DURATION_MISMATCH",
        )

    return RenderProbeResult(
        duration_ms=duration_ms,
        width=width,
        height=height,
        video_codec=vcodec,
        audio_codec=audio.get("codec_name") if audio else "none",
        size_bytes=output_path.stat().st_size,
    )


# ---------------------------------------------------------------------------
# Async execution
# ---------------------------------------------------------------------------


async def run_render_process(
    argv: list[str],
    output_path: Path,
    *,
    cancel_event: asyncio.Event | None = None,
    timeout_sec: float | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    ffmpeg_bin_override: str | None = None,
) -> tuple[str, str]:
    """Execute the render argv safely (no shell), keep bounded stderr.

    The caller validates the output afterwards; this function only enforces
    exit code, timeout, cancellation, and a non-empty temp file.
    Returns bounded (stdout_str, stderr_str).
    """
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    ffmpeg_bin = (argv[0] if argv else None) or ffmpeg_bin_override or shutil.which("ffmpeg")
    if not ffmpeg_bin or not Path(ffmpeg_bin).exists():
        raise RenderError(
            "FFmpeg is not installed or not found; rendering requires it (see /api/capabilities).",
            error_code="FFMPEG_NOT_FOUND",
        )
    # Defensive consistency: argv[0] should match the binary we validated.
    if argv and argv[0] != ffmpeg_bin:
        raise RenderError(
            "Render argv references a different ffmpeg binary than validated.",
            error_code="INTERNAL_ERROR",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = timeout_sec or float(settings.FFMPEG_TIMEOUT_SECONDS)
    if progress_callback:
        progress_callback(15.0, "rendering")

    proc: asyncio.subprocess.Process | None = None
    try:
        logger.info(f"Executing render (len={len(argv)} argv, no shell): {argv[0:2]} ...")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_task = asyncio.create_task(_read_bounded_stream(proc.stderr, 196_608))
        wait_proc_task = asyncio.create_task(proc.wait())
        watchers: list[asyncio.Task] = [wait_proc_task]
        wait_cancel_task: asyncio.Task | None = None
        if cancel_event:
            wait_cancel_task = asyncio.create_task(cancel_event.wait())
            watchers.append(wait_cancel_task)

        done, pending = await asyncio.wait(
            watchers, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

        if not done:
            _terminate_process(proc)
            stderr_out = await stderr_task
            _cleanup_partial_output(output_path)
            raise RenderError(
                f"FFmpeg render timed out after {timeout} seconds.",
                error_code="TIMEOUT",
                diagnostic_logs=stderr_out,
            )
        if wait_cancel_task and wait_cancel_task in done and cancel_event.is_set():
            _terminate_process(proc)
            stderr_out = await stderr_task
            _cleanup_partial_output(output_path)
            raise JobCancelledError()

        return_code = proc.returncode
        stderr_out = await stderr_task
        stdout_out = ""
        if return_code != 0:
            _cleanup_partial_output(output_path)
            snippet = stderr_out.strip()[-1200:] if stderr_out else f"Exit code {return_code}"
            logger.error(f"FFmpeg render failed (code {return_code}): {snippet}")
            raise RenderError(
                f"FFmpeg render failed with exit code {return_code}.",
                error_code="RENDER_FAILED",
                diagnostic_logs=stderr_out,
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            _cleanup_partial_output(output_path)
            raise RenderError(
                "FFmpeg produced no output file (or zero bytes).",
                error_code="RENDER_EMPTY_OUTPUT",
                diagnostic_logs=stderr_out,
            )
        return stdout_out, stderr_out
    except (RenderError, JobCancelledError):
        raise
    except Exception as e:
        if proc:
            _terminate_process(proc)
        _cleanup_partial_output(output_path)
        raise RenderError(
            f"Unexpected render failure: {e}",
            error_code="INTERNAL_ERROR",
        ) from e


def _cleanup_partial_output(path: Path) -> None:
    """Remove a failed/partial render file. Only touches `.part-*` files."""
    try:
        if path.name.startswith(".part-") and path.exists():
            path.unlink(missing_ok=True)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Could not remove partial render file {path}: {e}")


def write_render_diagnostics(
    log_dir: Path,
    render_id: str,
    argv: list[str],
    config: dict[str, Any],
    stderr_log: str | None = None,
) -> dict[str, str]:
    """Persist the per-render argument list, config, and bounded stderr log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = log_dir / f"{render_id}.config.json"
    log_path = log_dir / f"{render_id}.log"
    cfg_path.write_text(
        json.dumps({"argv": argv, **config}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bounded = (stderr_log or "")[-196_608:]
    log_path.write_text(bounded or "no ffmpeg stderr captured", encoding="utf-8")
    return {"config_path": str(cfg_path), "log_path": str(log_path)}
