"""Stage s01_ingest — media probing and 16 kHz mono PCM extraction.

Accepts a local media path OR a URL. For URLs:

- The PRD FR-12 policy applies: URL ingestion is DISABLED by default and
  requires ``QATTA_ENABLE_URL_INGESTION=true``. Without that opt-in the
  stage refuses with a clear error — nothing is ever downloaded silently.
- With the opt-in, ``yt-dlp`` is imported lazily and downloads the best
  merged mp4 into the project's work dir. Errors surface honestly.

FFmpeg invocation is always a subprocess argument array (no shell, no
interpolation), with a bounded timeout and captured, size-limited stderr.

The audio extraction command matches the spec:
``ffmpeg -y -i <input> -vn -acodec pcm_s16le -ar 16000 -ac 1 -threads 0 <out>``
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import QattaManifest

_AUDIO_FILENAME = "audio_16k.wav"


def is_url(source: str) -> bool:
    """True when the source points at an http(s) resource."""
    try:
        return urlparse(source).scheme in ("http", "https")
    except ValueError:
        return False


@dataclass(frozen=True)
class ProbedMedia:
    """Results of one ffprobe run on a local media file."""

    duration_sec: float
    width: int | None
    height: int | None
    fps: float | None


def _require_ffprobe(timeout: float) -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise PipelineError(
            "ffprobe was not found on PATH. Install ffmpeg/ffprobe to run "
            "stage s01_ingest (on Fedora: 'sudo dnf install ffmpeg')."
        )
    return ffprobe


def _parse_fps(rate: str | None) -> float | None:
    """Parse an ffprobe frame-rate fraction like ``30000/1001``."""
    if not rate:
        return None
    try:
        num, _, den = rate.partition("/")
        value = float(num) / (float(den) if den else 1.0)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def probe_media(media_path: Path, settings: QattaSettings) -> ProbedMedia:
    """One bounded ffprobe call returning duration, resolution and fps."""
    ffprobe = _require_ffprobe(settings.ffprobe_timeout_seconds)
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=settings.ffprobe_timeout_seconds,
            check=True,
        )
        data = json.loads(proc.stdout)
    except subprocess.TimeoutExpired as e:
        raise PipelineError(
            f"ffprobe timed out after {settings.ffprobe_timeout_seconds}s on {media_path}."
        ) from e
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as e:
        raise PipelineError(f"ffprobe could not inspect {media_path}: {e}") from e

    fmt = data.get("format") or {}
    try:
        duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError) as e:
        raise PipelineError(
            f"ffprobe reported no usable duration for {media_path}: format={fmt!r}"
        ) from e
    if duration <= 0:
        raise PipelineError(f"ffprobe reported non-positive duration for {media_path}.")

    width: int | None = None
    height: int | None = None
    fps: float | None = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            try:
                width = int(stream["width"])
                height = int(stream["height"])
            except (KeyError, TypeError, ValueError):
                width, height = None, None
            fps = _parse_fps(stream.get("avg_frame_rate"))
            break

    return ProbedMedia(duration_sec=duration, width=width, height=height, fps=fps)


def extract_audio_16k(source: Path, destination: Path, settings: QattaSettings) -> Path:
    """Extract 16 kHz mono s16le PCM WAV (substrate for both passes)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PipelineError(
            "ffmpeg was not found on PATH. Install ffmpeg to run "
            "stage s01_ingest (on Fedora: 'sudo dnf install ffmpeg')."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Argument array, never shell=True; bounded stderr keeps logs small.
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-threads",
                "0",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_timeout_seconds,
            check=True,
        )
    except subprocess.TimeoutExpired as e:
        raise PipelineError(
            "FFmpeg audio extraction timed out after "
            f"{settings.ffmpeg_timeout_seconds}s on {source}."
        ) from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "")[:2000]
        raise PipelineError(f"FFmpeg failed extracting 16 kHz audio from {source}: {stderr}") from e
    except OSError as e:
        raise PipelineError(f"FFmpeg could not be started for {source}: {e}") from e

    if not destination.is_file() or destination.stat().st_size == 0:
        raise PipelineError(f"FFmpeg produced no audio output at {destination}.")
    return destination


def _require_url_ingestion_permitted(settings: QattaSettings) -> None:
    """Fail-closed gate shared by both URL ingestion paths. Nothing may
    touch the network without the (now default-on, FR-12-reviewed) flag,
    and explicit opt-out must be honored."""
    if not settings.cloud_backend_permitted("youtube_subs_first"):
        raise PipelineError(
            "Ingesting a URL requires URL ingestion to be enabled "
            "(QATTA_ENABLE_URL_INGESTION=true). It was explicitly "
            "disabled, so nothing was fetched or downloaded."
        )


def _ingest_youtube_subs_first(
    manifest: QattaManifest, settings: QattaSettings, work_dir: Path
) -> None:
    """Captions-first ingest for YouTube sources (backend
    ``youtube_subs_first``): fetch metadata + caption track WITHOUT the
    media download; the full Whisper pass 1 is skipped entirely.
    """
    _require_url_ingestion_permitted(settings)
    from qatta.stages.s02_transcript.youtube_subs import fetch_info_and_subs

    info, vtt_path = fetch_info_and_subs(
        str(manifest.source_url or manifest.source_path),
        work_dir,
        settings.youtube_sub_language_list(),
        settings.youtube_fetch_timeout_seconds,
    )
    manifest.source_url = manifest.source_path  # keep the URL recorded
    manifest.subtitle_path = str(vtt_path.resolve())
    duration = info.get("duration")
    if not duration or float(duration) <= 0:
        raise PipelineError(
            "yt-dlp returned no positive duration; cannot initialize a "
            "meaningful project timeline from this source."
        )
    manifest.duration_sec = float(duration)
    manifest.source_path = f"youtube:{info.get('id') or info.get('webpage_url') or 'unknown'}"
    detail = info.get("resolution") or ""
    width = info.get("width")
    height = info.get("height")
    if isinstance(width, int) and isinstance(height, int):
        manifest.video_width = width
        manifest.video_height = height
    fps = info.get("fps")
    if isinstance(fps, (int, float)) and float(fps) > 0:
        manifest.fps = float(fps)
    del detail


def _download_url_if_needed(
    manifest: QattaManifest, settings: QattaSettings, work_dir: Path
) -> Path:
    """Download a URL source via yt-dlp (gated; lazy import; honest errors)."""
    if not settings.cloud_backend_permitted("youtube_subs_first"):
        raise PipelineError(
            "Ingesting a URL requires explicit opt-in "
            "(QATTA_ENABLE_URL_INGESTION=true). The PRD FR-12 policy review "
            "is pending, so URL ingestion is disabled by default and nothing "
            "was downloaded."
        )
    try:
        import yt_dlp  # lazy: heavy and policy-gated
    except ImportError as e:
        raise PipelineError(
            "URL ingestion is enabled but yt-dlp is not installed in this "
            "environment (`pip install yt-dlp`). No download was attempted."
        ) from e

    target_dir = work_dir / "source_media"
    target_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": settings.youtube_sub_language_list(),
        "subtitlesformat": "vtt/best",
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": True,
        "cachedir": False,
        "source_address": "0.0.0.0",
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
        "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(str(manifest.source_url), download=True)
    except Exception as e:  # yt-dlp raises DownloadError etc.
        raise PipelineError(f"URL ingestion failed for {manifest.source_url}: {e}") from e

    if not info or info.get("_type") not in (None, "video"):
        raise PipelineError(
            "URL ingestion supports single videos only (playlists are "
            "rejected rather than silently truncated)."
        )
    filename = info.get("filepath") or (info.get("requested_downloads") or [{}])[0].get("filepath")
    if not filename or not Path(filename).is_file():
        raise PipelineError("yt-dlp finished but the merged media file could not be located.")

    # Locate and attach platform subtitles if downloaded alongside the media
    from qatta.stages.s02_transcript.youtube_subs import _locate_sub_file

    video_id = info.get("id") or ""
    vtt_path = _locate_sub_file(target_dir, video_id)
    if vtt_path and vtt_path.is_file():
        manifest.subtitle_path = str(vtt_path.resolve())

    return Path(filename)


def run_ingest_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    work_dir: str | Path | None = None,
) -> QattaManifest:
    """Execute stage s01_ingest for the given manifest.

    - Probes duration / resolution / fps with ffprobe.
    - Extracts ``audio_16k.wav`` (16 kHz mono s16le PCM).
    - For URL sources: gated yt-dlp download first (see FR-12 notes).

    The manifest is updated in place and returned; the orchestrator
    persists it and marks the stage complete.
    """
    settings = settings or QattaSettings()
    work = Path(work_dir) if work_dir else (settings.manifest_path(manifest.project_id).parent)
    work.mkdir(parents=True, exist_ok=True)

    source = Path(manifest.source_path)
    if is_url(manifest.source_path):
        if settings.transcription_backend == "youtube_subs_first":
            # Captions-first path: NO media download, NO full-audio
            # extraction; utterances come from the platform caption
            # track and only ranked sections are downloaded later.
            manifest.source_url = manifest.source_path
            _ingest_youtube_subs_first(manifest, settings, work)
            return manifest
        _require_url_ingestion_permitted(settings)
        local_path = _download_url_if_needed(manifest, settings, work)
        manifest.source_url = manifest.source_path
        manifest.source_path = str(local_path.resolve())
        source = local_path

    if not source.is_file():
        raise PipelineError(
            f"Source media does not exist: {source} "
            "(the manifest source_path always stays a local file)."
        )

    probed = probe_media(source, settings)
    audio_path = extract_audio_16k(source, work / _AUDIO_FILENAME, settings)

    manifest.duration_sec = probed.duration_sec
    manifest.video_width = probed.width
    manifest.video_height = probed.height
    manifest.fps = probed.fps
    manifest.audio_16k_path = str(audio_path.resolve())
    return manifest


def register(orchestrator) -> None:
    """Attach s01_ingest to a :class:`PipelineOrchestrator`."""

    @orchestrator.stage("s01_ingest")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_ingest_stage(manifest, orchestrator.settings, work_dir=orchestrator.work_dir)
