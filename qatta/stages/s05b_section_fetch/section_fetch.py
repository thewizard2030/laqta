"""Stage s05b_section_fetch — download ONLY the ranked-winning sections.

YouTube captions-first flow (``transcript_source == "youtube_subs_first"``):
the full media was never downloaded, Pass 1 read the platform captions,
and now that s05_ranking selected the winning clips, this stage fetches
ONLY those small ranges with yt-dlp's ``download_ranges`` (no ffmpeg
retry loops, no playlist traversal):

- per winning clip: one yt-dlp call for
  ``[clip.start_ms - fine_padding_ms, clip.end_ms + fine_padding_ms]``,
- ``force_keyframes_at_cuts=True`` so the cut lands on a real keyframe,
- the section is transcoded to a 16 kHz mono s16le WAV via the shared
  s01 helper for the local Pass 2 word alignment,
- the section paths + its absolute source offset (``section_start_ms``)
  are recorded on the candidate so Pass 2 and s06_render consume the
  section instead of the (absent) full media.

The stage is a no-op (honest, not silent faking) for plain local-file
sources: the full media already exists there and Pass 2 never needed
sections.

Gate: downloading anything requires URL ingestion to be permitted —
explicit opt-out (``QATTA_ENABLE_URL_INGESTION=false``) is always
honored; nothing is fetched silently.
"""

from __future__ import annotations

from pathlib import Path

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import ClipCandidate, QattaManifest
from qatta.stages.s01_ingest.ingestor import (
    extract_audio_16k,
    is_url,
)

_SECTIONS_DIRNAME = "sections"


def _require_url_download_permitted(settings: QattaSettings) -> None:
    if not settings.cloud_backend_permitted("youtube_subs_first"):
        raise PipelineError(
            "Downloading winning clip sections requires URL ingestion "
            "(QATTA_ENABLE_URL_INGESTION=true); it was explicitly "
            "disabled, so nothing was downloaded."
        )


def _clip_range_ms(candidate: ClipCandidate, settings: QattaSettings) -> tuple[int, int]:
    """Absolute [start_ms, end_ms] of the requested source section."""

    start = max(0, candidate.start_ms - settings.fine_padding_ms)
    end = candidate.end_ms + settings.fine_padding_ms
    if end <= start:
        raise PipelineError(
            f"Clip '{candidate.clip_id}': degenerate section range [{start}, {end}]."
        )
    return start, end


def download_clip_section(
    candidate: ClipCandidate,
    source_url: str,
    work_dir: Path,
    settings: QattaSettings,
) -> tuple[Path, Path, int]:
    """Download one winning clip's section; return (mp4, wav_16k, offset_ms).

    The returned offset is the absolute source millisecond matching
    local time zero inside the downloaded files.
    """
    try:
        import yt_dlp  # lazy: heavy and policy-relevant
    except ImportError as e:
        raise PipelineError(
            "Section download requires yt-dlp installed in this "
            "environment (`pip install yt-dlp`). Nothing downloaded."
        ) from e

    start_ms, end_ms = _clip_range_ms(candidate, settings)
    sections_dir = work_dir / _SECTIONS_DIRNAME
    sections_dir.mkdir(parents=True, exist_ok=True)
    # The final merged path is whatever yt-dlp resolved (download_ranges
    # selected the exact section); we read it from requested_downloads.
    options = {
        "outtmpl": str(sections_dir / f"{candidate.clip_id}.%(ext)s"),
        "format": "bv*[ext=mp4][height<=2160]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "retries": 2,
        "socket_timeout": int(settings.youtube_fetch_timeout_seconds),
        "cachedir": False,
        "source_address": "0.0.0.0",
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
        # The heart of the feature: fetch ONLY [start, end) seconds.
        "download_ranges": lambda _info, _ydl: [
            {"start": start_ms / 1000.0, "end": end_ms / 1000.0}
        ],
        "force_keyframes_at_cuts": True,
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source_url, download=True)
    except Exception as e:  # yt-dlp raises DownloadError etc.
        raise PipelineError(
            f"Section download failed for clip '{candidate.clip_id}' "
            f"({source_url} [{start_ms}-{end_ms}] ms): {e}"
        ) from e

    downloaded = info.get("requested_downloads") or [{}]
    actual_path = info.get("filepath") or (downloaded[0].get("filepath") if downloaded else None)
    if not actual_path:
        raise PipelineError(
            f"yt-dlp finished but the section media file for clip "
            f"'{candidate.clip_id}' could not be located."
        )
    final_path = Path(actual_path)
    if not final_path.is_file() or final_path.stat().st_size == 0:
        raise PipelineError(
            f"yt-dlp produced no section media for clip "
            f"'{candidate.clip_id}' (looked for {final_path})."
        )

    wav_path = sections_dir / f"{candidate.clip_id}_audio_16k.wav"
    audio_path = extract_audio_16k(final_path, wav_path, settings)
    return final_path, audio_path, start_ms


def run_section_fetch_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    work_dir: str | Path | None = None,
) -> QattaManifest:
    """Execute stage s05b_section_fetch for the given manifest.

    Winners follow the same deterministic rule as s05_ranking: gate-passed
    candidates in manifest order, capped at ``max_winners``. Other
    candidates are left untouched; Pass 2 (s02b) honestly reports any
    clip it cannot align.
    """
    settings = settings or QattaSettings()
    if manifest.transcript_source != "youtube_subs_first":
        # Plain local-file flow: the full media exists and Pass 2 slices
        # it directly. Nothing to fetch — return unchanged.
        return manifest
    if not is_url(manifest.source_url or "") and not manifest.source_path.startswith("youtube:"):
        raise PipelineError(
            "Manifest claims a youtube_subs_first transcript but carries "
            "no YouTube source URL; the section stage cannot proceed "
            "honestly."
        )
    _require_url_download_permitted(settings)

    work = Path(work_dir) if work_dir else (settings.manifest_path(manifest.project_id).parent)
    source_url = manifest.source_url or ""
    winners = [c for c in manifest.candidates if c.veto_gates.passed_all][: settings.max_winners]

    fetched = 0
    for candidate in winners:
        if (
            candidate.section_media_path
            and Path(candidate.section_media_path).is_file()
            and candidate.section_audio_16k_path
            and Path(candidate.section_audio_16k_path).is_file()
        ):
            continue  # artifact-based caching per clip
        video_path, wav_path, offset = download_clip_section(candidate, source_url, work, settings)
        payload = candidate.model_dump()
        payload["section_media_path"] = str(video_path.resolve())
        payload["section_audio_16k_path"] = str(wav_path.resolve())
        payload["section_start_ms"] = offset
        payload.setdefault("evidence_log", []).append(
            "s05b: section fetched via yt-dlp "
            f"[{offset}-{candidate.end_ms + settings.fine_padding_ms}] ms"
        )
        updated = candidate.model_validate(payload)
        index = manifest.candidates.index(candidate)
        manifest.candidates[index] = updated
        fetched += 1
    del fetched  # surfaced implicitly via section fields + timings
    return manifest


def register(orchestrator) -> None:
    """Attach s05b_section_fetch to a :class:`PipelineOrchestrator`."""

    @orchestrator.stage("s05b_section_fetch")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_section_fetch_stage(
            manifest, orchestrator.settings, work_dir=orchestrator.work_dir
        )
