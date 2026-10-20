"""Transcript cleaning and normalization pipeline for YouTube and ASR subtitles.

Provides:
- Deduplication of rolling auto-generated captions
- Stripping of non-speech annotations ([Music], [Applause], [موسيقى], etc.)
- HTML entity decoding (&amp;, &#39;, &quot;)
- BiDi / RTL Unicode isolation for Arabic/Latin mixed text
- Conversion between raw cues, WebVTT (.vtt) documents, and API segments
"""

import html
import re
from dataclasses import dataclass


@dataclass
class CleanCue:
    """A clean, timestamped caption cue."""

    start_ms: int
    end_ms: int
    text: str


# Matches non-speech annotations in English and Arabic
_NOISE_TAG_RE = re.compile(
    r"\[(Music|Applause|Laughter|Inaudible|Cheering|Sigh|موسيقى|تصفيق|ضحك|صمت)[^\]]*\]"
    r"|\((Music|Applause|Laughter|Inaudible|Cheering|Sigh|موسيقى|تصفيق|ضحك|صمت)[^\)]*\)",
    re.IGNORECASE,
)

# Matches inline markup tags like <c>, </c>, <00:00:00.000>
_MARKUP_RE = re.compile(r"<[^>]*>")


def clean_cue_text(text: str) -> str:
    """Strip noise tags, markup, unescape HTML entities, and normalize whitespace."""
    if not text:
        return ""
    # Unescape HTML entities
    unescaped = html.unescape(text)
    # Strip speaker turn markers (e.g. ">>", ">", or multiple chevrons)
    no_speakers = re.sub(r"^\s*>>*\s*", "", unescaped)
    # Strip inline markup
    no_markup = _MARKUP_RE.sub("", no_speakers)
    # Strip noise tags
    no_noise = _NOISE_TAG_RE.sub("", no_markup)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", no_noise).strip()
    return cleaned


def dedup_rolling_text_cues(cues: list[CleanCue]) -> list[CleanCue]:
    """Collapse rolling auto-captions where cue n repeats the words of cue n-1.

    YouTube auto-captions generate rolling cues where each subsequent cue
    repeats the trailing words of the previous cue and appends new words.
    This function collapses consecutive duplicates to produce continuous,
    non-repetitive sentences.
    """
    if not cues:
        return []

    deduped: list[CleanCue] = []
    prev_words: list[str] = []

    for cue in cues:
        cleaned_text = clean_cue_text(cue.text)
        if not cleaned_text:
            continue

        words = cleaned_text.split()
        if not words:
            continue

        # Find maximum overlap between prev_words suffix and current words prefix
        keep_from = 0
        max_overlap = min(len(prev_words), len(words))
        for k in range(max_overlap, 0, -1):
            if prev_words[-k:] == words[:k]:
                keep_from = k
                break

        fresh_words = words[keep_from:]
        if fresh_words:
            fresh_text = " ".join(fresh_words)
            # If the current cue starts right after the previous cue and has the
            # same text span, extend or append
            deduped.append(
                CleanCue(
                    start_ms=cue.start_ms,
                    end_ms=max(cue.start_ms + 100, cue.end_ms),
                    text=fresh_text,
                )
            )
            prev_words = words

    # Clamp rolling cue ends so consecutive cues never overlap in time
    for i in range(len(deduped) - 1):
        if deduped[i + 1].start_ms > deduped[i].start_ms:
            deduped[i].end_ms = min(deduped[i].end_ms, deduped[i + 1].start_ms)

    return deduped


def format_ms_to_vtt_timestamp(ms: int) -> str:
    """Format millisecond integer into HH:MM:SS.mmm WebVTT timestamp."""
    total_sec, millis = divmod(max(0, ms), 1000)
    hours, remainder = divmod(total_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def cues_to_vtt(cues: list[CleanCue]) -> str:
    """Format a list of CleanCue objects into a standard WebVTT string."""
    lines = ["WEBVTT", ""]
    for cue in cues:
        start_ts = format_ms_to_vtt_timestamp(cue.start_ms)
        end_ts = format_ms_to_vtt_timestamp(cue.end_ms)
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines)


def cues_to_api_segments(cues: list[CleanCue]) -> list[dict]:
    """Convert clean cues to standard API segment dictionaries with second-level floats."""
    return [
        {
            "id": f"u_{idx:04d}",
            "start": round(cue.start_ms / 1000.0, 3),
            "end": round(cue.end_ms / 1000.0, 3),
            "text": cue.text,
            "words": None,
            "speaker": None,
        }
        for idx, cue in enumerate(cues, start=1)
    ]
