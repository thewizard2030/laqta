"""Media probe and system capability detection.

Uses safe subprocess argument arrays, strict deadlines, no shell=True, and bounded outputs.
Honest detection: never claims dependencies exist if they are not installed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import qatta
from app.core.config import settings
from app.core.logging import logger
from app.providers.llm.openrouter import FREE_MODEL_IDS as OPENROUTER_FREE_MODEL_IDS
from app.schemas.capabilities import (
    AsrCapabilities,
    BinaryCapability,
    CapabilitiesResponse,
    FFmpegCapability,
    HardwareCapabilities,
    LlmCapabilities,
    StorageCapabilities,
)

if TYPE_CHECKING:  # pragma: no cover - static typing only
    from app.schemas.capabilities import UrlIngestionCapabilities

# FR-11 / PRD §9: any hosted (cloud) provider MUST surface this disclosure in
# the UI and require explicit opt-in before transcript text leaves the device.
TRANSCRIPT_LEAVES_DEVICE_NOTICE = (
    "Warning: with a hosted (cloud) LLM provider, portions of your transcript "
    "text leave this device and are processed by an external service. The "
    "deterministic local baseline needs no network and no API key."
)


class MediaProbeError(Exception):
    """Raised when media probing fails or input is invalid media."""


@dataclass
class MediaProbeResult:
    """Structured inspection result from ffprobe."""

    duration_ms: int
    width: int
    height: int
    video_codec: str
    audio_codec: str
    size_bytes: int
    format_name: str


def _check_module_installed(module_name: str) -> bool:
    """Safely check if a Python module is installed without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def detect_ffmpeg(custom_path: str | None = None) -> FFmpegCapability:
    """Honest detection of installed ffmpeg binary and libass support."""
    ffmpeg_binary = custom_path or shutil.which("ffmpeg")
    if not ffmpeg_binary or not os.path.exists(ffmpeg_binary):
        return FFmpegCapability(
            available=False,
            path=None,
            version=None,
            has_libass=False,
            details=(
                "FFmpeg binary not found in system PATH. Install ffmpeg to enable media processing."
            ),
        )

    try:
        # Safe subprocess execution: argument array, no shell=True, finite timeout
        res = subprocess.run(
            [ffmpeg_binary, "-version"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            lines = res.stdout.splitlines()
            version_str = lines[0].strip() if lines else "unknown"
            # Honest inspection: prefer runtime evidence. First check the
            # configure-time flag, then verify the libass-backed subtitles
            # filters actually exist in this build (each is a necessary
            # hint; both may miss on non-standard builds).
            has_libass = "--enable-libass" in res.stdout
            if not has_libass:
                from app.services.rendering.render import ffmpeg_has_libass_filter

                has_libass = ffmpeg_has_libass_filter(ffmpeg_binary)
                if has_libass:
                    return FFmpegCapability(
                        available=True,
                        path=ffmpeg_binary,
                        version=version_str,
                        has_libass=True,
                        details="FFmpeg detected; libass subtitles filters available.",
                    )
            return FFmpegCapability(
                available=True,
                path=ffmpeg_binary,
                version=version_str,
                has_libass=has_libass,
                details="FFmpeg detected and operational.",
            )
        else:
            return FFmpegCapability(
                available=False,
                path=ffmpeg_binary,
                version=None,
                has_libass=False,
                details=f"FFmpeg returned non-zero exit code: {res.returncode}",
            )
    except subprocess.TimeoutExpired:
        logger.warning("FFmpeg version probe timed out after 3.0s")
        return FFmpegCapability(
            available=False,
            path=ffmpeg_binary,
            version=None,
            has_libass=False,
            details="FFmpeg probe timed out",
        )
    except Exception as e:
        logger.error(f"Error probing ffmpeg: {e}")
        return FFmpegCapability(
            available=False,
            path=ffmpeg_binary,
            version=None,
            has_libass=False,
            details=str(e),
        )


def detect_ffprobe(custom_path: str | None = None) -> BinaryCapability:
    """Honest detection of installed ffprobe binary."""
    ffprobe_binary = custom_path or shutil.which("ffprobe")
    if not ffprobe_binary or not os.path.exists(ffprobe_binary):
        return BinaryCapability(
            available=False,
            path=None,
            version=None,
            details=(
                "FFprobe binary not found in system PATH. Install ffmpeg/ffprobe for media probing."
            ),
        )

    try:
        res = subprocess.run(
            [ffprobe_binary, "-version"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if res.returncode == 0 and res.stdout:
            lines = res.stdout.splitlines()
            version_str = lines[0].strip() if lines else "unknown"
            return BinaryCapability(
                available=True,
                path=ffprobe_binary,
                version=version_str,
                details="FFprobe detected and operational.",
            )
        else:
            return BinaryCapability(
                available=False,
                path=ffprobe_binary,
                version=None,
                details=f"FFprobe returned non-zero exit code: {res.returncode}",
            )
    except subprocess.TimeoutExpired:
        logger.warning("FFprobe version probe timed out after 3.0s")
        return BinaryCapability(
            available=False,
            path=ffprobe_binary,
            version=None,
            details="FFprobe probe timed out",
        )
    except Exception as e:
        logger.error(f"Error probing ffprobe: {e}")
        return BinaryCapability(
            available=False,
            path=ffprobe_binary,
            version=None,
            details=str(e),
        )


def probe_media_file(file_path: Path, custom_ffprobe: str | None = None) -> MediaProbeResult:
    """Probe media container and streams using ffprobe.

    Security & robustness rules:
    - Subprocess argument array only (no shell=True).
    - Finite deadline (10s timeout).
    - Output size limited to 512 KB to prevent memory exhaustion.
    - Validates duration > 0 and presence of decodable video stream.
    """
    if not file_path.exists():
        raise MediaProbeError(f"Media file not found: {file_path}")

    ffprobe_bin = custom_ffprobe or shutil.which("ffprobe")
    if not ffprobe_bin or not os.path.exists(ffprobe_bin):
        raise MediaProbeError("FFprobe is not installed on this system. Cannot probe media.")

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,format_name:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(file_path),
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MediaProbeError("FFprobe process timed out after 10.0s") from e
    except Exception as e:
        raise MediaProbeError(f"Failed to execute ffprobe: {e}") from e

    if res.returncode != 0:
        err_msg = res.stderr.strip() if res.stderr else f"Exit code {res.returncode}"
        raise MediaProbeError(f"Media probe failed: {err_msg}")

    # Bounded output size check
    if len(res.stdout) > 512 * 1024:
        raise MediaProbeError("FFprobe output exceeded maximum allowed size (512 KB).")

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise MediaProbeError("Failed to parse ffprobe JSON output.") from e

    format_data = data.get("format", {})
    streams = data.get("streams", [])

    # Find video stream
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise MediaProbeError("No valid video stream found in uploaded file.")

    width = video_stream.get("width")
    height = video_stream.get("height")
    video_codec = video_stream.get("codec_name", "unknown")

    if not width or not height or width <= 0 or height <= 0:
        raise MediaProbeError(f"Invalid video dimensions: {width}x{height}")

    # Find audio stream (optional, some videos have no audio)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    audio_codec = audio_stream.get("codec_name", "none") if audio_stream else "none"

    # Extract duration
    duration_raw = format_data.get("duration") or video_stream.get("duration")
    if not duration_raw:
        raise MediaProbeError("Could not determine media duration from probe.")

    try:
        duration_sec = float(duration_raw)
        if duration_sec <= 0:
            raise ValueError()
    except (ValueError, TypeError) as e:
        raise MediaProbeError(f"Invalid media duration: {duration_raw}") from e

    duration_ms = int(duration_sec * 1000)

    # Size
    try:
        size_bytes = int(format_data.get("size", file_path.stat().st_size))
    except Exception:
        size_bytes = file_path.stat().st_size

    format_name = format_data.get("format_name", "unknown")

    return MediaProbeResult(
        duration_ms=duration_ms,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        size_bytes=size_bytes,
        format_name=format_name,
    )


def detect_asr_capabilities() -> AsrCapabilities:
    """Check availability of speech-to-text libraries and providers without loading models."""
    from app.services.transcription.manager import transcription_manager

    providers_info = transcription_manager.list_providers()
    wcpp_avail = any(p.provider == "whisper.cpp" and p.available for p in providers_info)

    return AsrCapabilities(
        faster_whisper=_check_module_installed("faster_whisper"),
        whisperx=_check_module_installed("whisperx"),
        whisper_cpp=wcpp_avail,
        cloud_apis_allowed=settings.ALLOW_CLOUD_APIS,
        active_provider=settings.DEFAULT_TRANSCRIPTION_BACKEND,
        providers=providers_info,
    )


def detect_hardware_capabilities() -> HardwareCapabilities:
    """Detect local compute capabilities (CPU vs CUDA) truthfully using CTranslate2 and PyTorch."""
    cuda_available = False
    cuda_count = 0
    cuda_device_name = None

    # Check via ctranslate2 (the actual execution engine for faster-whisper)
    if _check_module_installed("ctranslate2"):
        try:
            import ctranslate2

            cuda_count = ctranslate2.get_cuda_device_count()
            if cuda_count > 0:
                cuda_available = True
                cuda_device_name = f"NVIDIA CUDA ({cuda_count} devices)"
        except Exception:
            pass

    # Also check torch if ctranslate2 did not report devices
    if not cuda_available and _check_module_installed("torch"):
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                cuda_available = True
                cuda_count = torch.cuda.device_count()
                cuda_device_name = torch.cuda.get_device_name(0)
        except Exception:
            pass

    user_requested_cuda = settings.DEFAULT_WHISPER_DEVICE == "cuda"
    fallback_reason = None
    if user_requested_cuda and not cuda_available:
        fallback_reason = "No CUDA devices detected on host; falling back to CPU INT8"

    device = "cuda" if (cuda_available and user_requested_cuda) else "cpu"
    compute_type = "float16" if device == "cuda" else settings.DEFAULT_WHISPER_COMPUTE_TYPE
    precision = compute_type

    return HardwareCapabilities(
        device=device,
        cuda_available=cuda_available,
        recommended_worker_concurrency=1,
        cuda_device_name=cuda_device_name,
        cuda_device_count=cuda_count,
        compute_type=compute_type,
        model=settings.DEFAULT_WHISPER_MODEL,
        precision=precision,
        fallback_reason=fallback_reason,
    )


def detect_storage_capabilities() -> StorageCapabilities:
    """Inspect effective local storage directory."""
    data_dir = settings.get_effective_data_dir()
    exists = data_dir.exists()
    writable = os.access(data_dir, os.W_OK) if exists else False

    return StorageCapabilities(
        data_dir=str(data_dir),
        exists=exists,
        writable=writable,
    )


def detect_llm_capabilities(settings_override=None) -> LlmCapabilities:
    """Secret-free LLM ranker status (FR-11): booleans and endpoint only.

    The API key itself is never included; only ``api_key_configured``. A
    hosted provider additionally requires the explicit opt-in and surfaces
    the disclosure text that the UI must show before transcript text leaves
    the device (PRD §9).
    """
    active = settings_override or settings
    hosted = active.LLM_HOSTED_OPT_IN
    is_openrouter = active.LLM_PROVIDER == "openrouter"
    if is_openrouter:
        base_url = active.LLM_OPENROUTER_BASE_URL
        model = active.LLM_OPENROUTER_MODEL
    else:
        base_url = active.LLM_BASE_URL
        model = active.LLM_MODEL
    return LlmCapabilities(
        openai_compatible=True,
        provider=active.LLM_PROVIDER,
        ranker_enabled=active.LLM_RANKER_ENABLED,
        base_url=base_url,
        model=model,
        api_key_configured=active.llm_api_key_configured(),
        hosted_opt_in=hosted,
        free_models=list(OPENROUTER_FREE_MODEL_IDS) if is_openrouter else [],
        disclosure=(TRANSCRIPT_LEAVES_DEVICE_NOTICE if (hosted and is_openrouter) else None),
    )


def detect_url_ingestion_capabilities() -> "UrlIngestionCapabilities":
    """Fail-closed detection for URL ingestion (PRD FR-12).

    ``enabled`` requires BOTH the explicit operator flag and an installed
    yt-dlp binary; any partial state explains itself via ``notice``.
    """
    from app.schemas.capabilities import UrlIngestionCapabilities
    from app.services.media.url_ingest import detect_yt_dlp

    yt_dlp = detect_yt_dlp()
    flag = settings.ENABLE_URL_INGESTION
    if not flag:
        notice = (
            "URL ingestion is disabled on this machine because the operator "
            "set QATTA_ENABLE_URL_INGESTION=false (it may be re-enabled by "
            "removing that override); incoming imports also require a "
            "per-import confirmation that you own the content or have "
            "permission."
        )
    elif not yt_dlp.available:
        notice = "yt-dlp is not installed; install it to enable URL ingestion."
    else:
        notice = (
            "URL ingestion is enabled locally. Each import requires you to "
            "confirm you own the content or have permission to use it."
        )
    return UrlIngestionCapabilities(
        enabled=flag and yt_dlp.available,
        feature_flag=flag,
        yt_dlp=yt_dlp,
        notice=notice,
    )


def detect_capabilities() -> CapabilitiesResponse:
    """Aggregate honest detection of all system capabilities."""
    return CapabilitiesResponse(
        app_name=settings.APP_NAME,
        version=qatta.__version__,
        local_only=True,
        ffmpeg=detect_ffmpeg(),
        ffprobe=detect_ffprobe(),
        asr=detect_asr_capabilities(),
        llm=detect_llm_capabilities(),
        hardware=detect_hardware_capabilities(),
        storage=detect_storage_capabilities(),
        url_ingestion=detect_url_ingestion_capabilities(),
    )
