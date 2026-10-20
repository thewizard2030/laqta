"""YouTube captions-first transcript source (transcript_source ==
``youtube_subs_first``).

On locally-permitted YouTube sources, Pass 1 does NOT transcribe the full
video. Instead:

1. Fetch the platform's ready-made caption track (manual subs preferred,
   auto-generated captions as fallback) below a few seconds of I/O via a
   single yt-dlp call with ``skip_download`` — no Whisper on the long
   media, no full-video download.
2. Parse the VTT with the standard library only and strip the ROLLING
   duplication that auto-generated captions produce (each cue repeats the
   tail of the previous cue; only the novel suffix lines are new text).
3. Convert the cues into :class:`TranscriptSegment` rows whose start/end
   are the platform's REAL cue milliseconds, which the shared acoustic
   builder then groups into :class:`AtomicUtterance` objects.

Truthfulness notes (architectural rules):
- Cue timing comes from the platform, not from local VAD measurement; the
  utterance boundary for a gap that YouTube rolled mid-speech uses the
  gap midpoint exactly like the offline degraded mode. Pass 2 re-times
  all word ms locally on the winners, and clip boundaries are snapped to
  locally detected words — so no caption timestamp survives as-is into
  final clips.
- Caption text is UNTRUSTED DATA (rule: transcripts must not be able to
  issue instructions). It is stored as literal text and never executed
  or shell-interpolated anywhere.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from qatta.core.pipeline import PipelineError
from qatta.stages.s02_transcript.fast_pass import (
    TranscriptSegment,
    _clean_segments,
)

_CUE_TIME_RE = re.compile(r"^(?:(?P<h1>\d+):)?(?P<m1>\d+):(?P<s1>\d+)[.,](?P<ms1>\d{1,3})$")

_SKIP_PREFIXES = ("WEBVTT", "NOTE", "Kind:", "Language:", "STYLE", "REGION")


@dataclass(frozen=True)
class VttCue:
    """One parsed VTT cue with platform milliseconds."""

    start_ms: int
    end_ms: int
    lines: tuple[str, ...]


def parse_vtt_ms(token: str) -> int:
    """Parse ``HH:MM:SS.mmm`` / ``MM:SS.mmm`` (dot or comma) to ms."""
    match = _CUE_TIME_RE.match(token.strip())
    if not match:
        raise PipelineError(f"Unparseable VTT timestamp: {token!r}")
    hours = int(match.group("h1") or 0)
    minutes = int(match.group("m1"))
    seconds = int(match.group("s1"))
    ms_text = match.group("ms1").ljust(3, "0")
    return (hours * 3600 + minutes * 60 + seconds) * 1000 + int(ms_text)


def parse_vtt_cues(vtt_text: str) -> list[VttCue]:
    """Extract timed cues from a WebVTT document (stdlib only).

    Cue identifiers (the optional standalone line before the timing
    line) are ignored. Blocks that contain no timing line, NOTE blocks,
    style blocks and duplicated re-listings are skipped. Malformed
    timing lines abort loudly instead of guessing.
    """
    cues: list[VttCue] = []
    blocks = re.split(r"\n\s*\n", vtt_text.strip())
    for block in blocks:
        raw_lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not raw_lines or raw_lines[0].startswith(_SKIP_PREFIXES):
            continue
        timing_idx: int | None = None
        for idx, line in enumerate(raw_lines):
            if "-->" in line:
                timing_idx = idx
                break
        if timing_idx is None:
            continue
        start_token, _, end_token = raw_lines[timing_idx].partition("-->")
        start_ms = parse_vtt_ms(start_token.strip().split()[0])
        # Strip cue settings from the end timing ("align:start line:0").
        end_ms = parse_vtt_ms(end_token.strip().split()[0])
        text_lines = tuple(line for line in raw_lines[timing_idx + 1 :] if line.strip())
        if not text_lines:
            continue
        cues.append(VttCue(start_ms, max(start_ms, end_ms), text_lines))
    return cues


def _strip_markup(line: str) -> str:
    """Remove inline VTT markup, decode HTML and strip speaker indicators.

    Handles ``<c>``/``<00:00:00.000>`` style tags, HTML entities and the
    ``- Speaker:`` prefixes used by rolling caption tracks.
    """
    cleaned = re.sub(r"<[^>]*>", "", line)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"^\s*>>*\s*", "", cleaned)
    return cleaned.strip()


def dedup_rolling_cues(cues: list[VttCue]) -> list[VttCue]:
    """Collapse auto-caption rolling repetition into novel content.

    YouTube auto captions roll: cue *n* repeats the trailing lines of
    cue *n-1* and adds a new final line. For consecutive cues we drop
    every leading line of the current cue that duplicates the previous
    cue's trailing lines (longest suffix/prefix match); a cue whose
    lines are ALL repeats of the previous cue is skipped entirely.
    Manual caption tracks (and static duplicate listings) pass through
    unchanged or are deduplicated likewise.
    """
    novel: list[VttCue] = []
    previous_lines: tuple[str, ...] = ()
    for cue in cues:
        rendered = tuple(_strip_markup(line) for line in cue.lines)
        rendered = tuple(line for line in rendered if line)
        if not rendered:
            continue
        # Longest k such that previous cue ENDS with the current leading
        # k lines (rolling window overlap).
        keep_from = 0
        max_overlap = min(len(previous_lines), len(rendered))
        for k in range(max_overlap, 0, -1):
            if previous_lines[-k:] == rendered[:k]:
                keep_from = k
                break
        fresh = rendered[keep_from:]
        if fresh:
            novel.append(VttCue(cue.start_ms, cue.end_ms, fresh))
            previous_lines = rendered
    return novel


def segments_from_youtube_subs(
    vtt_text: str, total_ms: int | None = None
) -> list[TranscriptSegment]:
    """Turn a caption document into Pass-1 transcript segments.

    Cue text is joined per cue; timestamps come from the platform and
    are clamped to ``total_ms`` when provided (colliding clamped spans
    get minimal nonzero lengths via the shared cleaner).
    """
    cues = dedup_rolling_cues(parse_vtt_cues(vtt_text))
    # Clamp consecutive cue ends to eliminate rolling caption overlap
    clamped_cues: list[VttCue] = []
    for idx, cue in enumerate(cues):
        end_ms = cue.end_ms
        if idx + 1 < len(cues) and cues[idx + 1].start_ms > cue.start_ms:
            end_ms = min(end_ms, cues[idx + 1].start_ms)
        clamped_cues.append(VttCue(cue.start_ms, max(cue.start_ms + 100, end_ms), cue.lines))

    segments = [
        TranscriptSegment(
            start_ms=cue.start_ms,
            end_ms=cue.end_ms,
            text=" ".join(cue.lines),
        )
        for cue in clamped_cues
    ]
    if total_ms is not None:
        segments = _clean_segments(segments, total_ms)
    return segments


# ---------------------------------------------------------------------------
# yt-dlp fetch (skip-download): metadata + caption file only
# ---------------------------------------------------------------------------


def fetch_info_and_subs(
    source_url: str,
    work_dir: Path,
    sub_languages: list[str],
    timeout_seconds: float = 120.0,
) -> tuple[dict, Path | None]:
    """Fetch video metadata and the best caption VTT WITHOUT downloading
    the media (single yt-dlp pass, ``skip_download``).

    Returns ``(info_dict, vtt_path)``. ``vtt_path`` is ``None`` when the
    video genuinely has no caption track in the requested languages —
    callers must surface that honestly rather than fetching the media.

    Honest failures: missing yt-dlp, network failures, playlists, and
    unavailable captions raise actionable :class:`PipelineError`s.
    """
    try:
        import yt_dlp  # lazy: heavy and policy-relevant
    except ImportError as e:
        raise PipelineError(
            "youtube_subs_first requires yt-dlp installed in this "
            "environment (`pip install yt-dlp`). Nothing was fetched."
        ) from e

    target_dir = work_dir / "subtitles"
    target_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": sub_languages,
        "subtitlesformat": "vtt/best",
        "noplaylist": True,
        "quiet": True,
        "socket_timeout": int(timeout_seconds),
        "cachedir": False,
        "source_address": "0.0.0.0",
        "extractor_args": {"youtube": {"player_client": ["android", "ios", "web"]}},
        "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(source_url, download=True)
    except Exception as e:  # yt-dlp raises DownloadError etc.
        raise PipelineError(f"Caption fetch failed for {source_url}: {e}") from e

    if not info or info.get("_type") not in (None, "video"):
        raise PipelineError(
            "Caption fetch supports single videos only (playlists are "
            "rejected rather than silently truncated)."
        )

    video_id = info.get("id") or ""
    vtt_path = _locate_sub_file(target_dir, video_id)
    if vtt_path is None:
        available = sorted(
            set(info.get("subtitles") or {}) | set(info.get("automatic_captions") or {})
        )
        raise PipelineError(
            "No caption track found for the requested languages "
            f"({sub_languages}) on {source_url}. Track languages "
            f"available: {available[:20] or 'none'} — set "
            "QATTA_YOUTUBE_SUB_LANGUAGES or fall back to local Whisper. "
            "Nothing was downloaded."
        )
    return info, vtt_path


def _locate_sub_file(target_dir: Path, video_id: str) -> Path | None:
    """Deterministically pick the freshest VTT matching the video id."""
    if not video_id:
        return None
    candidates = sorted(target_dir.glob(f"{video_id}*.vtt"))
    if not candidates:
        return None
    # yt-dlp overwrites per language; prefer manual-looking bare lang
    # (shortest suffix) over auto variants for determinism.
    return min(candidates, key=lambda p: (len(p.stem), p.name))
