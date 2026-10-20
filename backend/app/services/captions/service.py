"""High-level caption service orchestration (kept free of direct DB access).

Bridges stored transcript segments into caption files for both the HTTP
endpoint and the background render worker, so both paths use identical,
deterministic logic.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.core.logging import logger
from app.schemas.captions import (
    WARNING_NO_ARABIC_FONT,
    CaptionStyleSettings,
)
from app.schemas.transcription import TranscriptSegment
from app.services.captions.generator import (
    CaptionGenerationError,
    build_cues,
    write_caption_files,
)


@dataclass
class GeneratedCaptions:
    """Result of generating caption files for one candidate clip."""

    timing_granularity: str  # "word" or "segment" (truthful)
    karaoke_used: bool
    warnings: list[str] = field(default_factory=list)
    srt_path: str | None = None
    ass_path: str | None = None


def overlapping_segments(
    segments: list[TranscriptSegment],
    start_ms: int,
    end_ms: int,
) -> list[TranscriptSegment]:
    """Return segments that intersect the candidate time window."""
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    return [seg for seg in segments if seg.end > start_s and seg.start < end_s]


def generate_candidate_captions(
    captions_dir: Path,
    candidate_id: str,
    start_ms: int,
    end_ms: int,
    segments: list[TranscriptSegment],
    style: CaptionStyleSettings,
    formats: tuple[str, ...] = ("srt", "ass"),
) -> GeneratedCaptions:
    """Generate SRT/ASS files for a candidate's time window.

    Applies the FR-08 no-karaoke rule automatically: karaoke is only used
    with reliable word timings AND the user opt-in (``style.karaoke``).
    """
    ov_segments = overlapping_segments(segments, start_ms, end_ms)
    if not ov_segments:
        raise CaptionGenerationError(
            "The candidate range contains no transcript segments; captions cannot be generated."
        )

    result = build_cues(
        segments=ov_segments,
        clip_start_ms=start_ms,
        clip_end_ms=end_ms,
        style=style,
    )
    enable_karaoke = bool(style.karaoke and result.karaoke_capable)
    written = write_caption_files(
        output_dir=captions_dir,
        candidate_id=candidate_id,
        result=result,
        style=style,
        formats=formats,
        enable_karaoke=enable_karaoke,
    )

    warnings = list(result.warnings)
    font_warning = arabic_font_warning(result.arabic_text_present)
    if font_warning:
        warnings.append(font_warning)

    return GeneratedCaptions(
        timing_granularity=result.timing_granularity,
        karaoke_used=enable_karaoke,
        warnings=warnings,
        srt_path=written.get("srt_path"),
        ass_path=written.get("ass_path"),
    )


def arabic_font_warning(arabic_text_used: bool) -> str | None:
    """Detect missing Arabic-capable fonts and suggest local alternatives.

    Uses fc-list (a bounded subprocess, argument array, 3 s timeout). This is
    a best-effort hint from fontconfig; the renderer's own fallback may still
    differ, which is why manual visual QA remains mandatory.
    """
    if not arabic_text_used:
        return None
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return None  # fontconfig absent; do not claim a problem we cannot see
    try:
        res = subprocess.run(
            [fc_list, ":lang=ar", "family"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if res.returncode == 0 and not (res.stdout or "").strip():
            logger.warning("fc-list reports no Arabic-capable fonts installed.")
            return WARNING_NO_ARABIC_FONT
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"Font availability check failed: {e}")
    return None
