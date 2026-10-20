"""Caption generation from transcript timestamps (PRD §5 FR-08).

Pure Python text processing: no media processing, no subprocess execution,
and no dependency on FFmpeg. Produces editable SRT and ASS content from
transcript segments with either:

- word-level cues (when word timings exist AND pass reliability checks),
  optionally with ASS karaoke tags when the caller explicitly requests it, or
- segment-level cues with a plain no-karaoke fallback whenever word timings
  are missing or unreliable.

CUE TIMING (the part that decides whether captions match the speaker)
----------------------------------------------------------------------
Platform caption tracks publish *rolling* cues: a cue stays on screen for
roughly twice the interval until the next cue starts, so consecutive cues
overlap. The platform replaces the previous cue the moment the next one
starts, so the real display window of a cue is ``[cue.start, next.start)``.

Using the raw ``cue.end`` therefore paints two blocks of text at once and
keeps the previous (already-spoken) block on screen. Measured against a
local Whisper word-level re-timing of the same audio, the platform cue
STARTS line up with the real word boundaries while the cue ENDS do not.

So every cue window is resolved to ``min(cue.end, next_cue.start)`` before
anything else happens. For ordinary non-overlapping ASR segments this is a
no-op (``next.start >= cue.end``), and for rolling platform captions it
yields contiguous, non-overlapping windows that match the speech.

Long cues are then SPLIT into several shorter cues whose time is
distributed proportionally to their text length, so the caption changes
every couple of seconds and each block stays inside the safe area.

RTL / mixed Arabic-Latin policy (deliberate and honest):
- Text is kept in LOGICAL order exactly as produced by the ASR provider.
- We never manually reverse or reorder Arabic text; shaping and bidi layout
  are the renderer's job (libass uses HarfBuzz/FriBiDi internally).
- Unmodified libass (style Encoding 0..255) hardcodes an LTR paragraph
  direction for bidi (VSFilter compatibility), which renders multi-word
  Arabic lines in REVERSED word order. For cues containing Arabic script
  we therefore emit the documented libass extension "{\\fe-1}" (base
  direction autodetect, matching style Encoding -1) plus a leading
  U+200F RIGHT-TO-LEFT MARK per visual line, which pins the paragraph
  direction to RTL regardless of whether the line starts with Latin text.
  This combination was verified empirically with color-tagged test lines
  rendered through FFmpeg/libass (see docs/CAPTION_QA.md); it is NOT a
  claim of universal bidi correctness: PRD §11 Gate D still requires
  human visual review. See docs/CAPTION_QA.md for the manual checklist.
- SRT output never carries bidi control characters: it stays pure
  logical-order text for editing/round-tripping into other tools.

Security: transcript text is untrusted data. Characters that could alter
ASS override tags or SRT structure are neutralized; text is never executed.
"""

import html
import math
import re
from dataclasses import dataclass, field

from app.schemas.captions import (
    WARNING_TEXT_OVERFLOW,
    WARNING_TEXT_SPLIT,
    WARNING_WORD_TEXT_LOW_CONFIDENCE,
    WARNING_WORD_TIMINGS_LOW_CONFIDENCE,
    WARNING_WORD_TIMINGS_MISSING,
    WARNING_WORD_TIMINGS_UNRELIABLE,
    CaptionStyleSettings,
)
from app.schemas.transcription import TranscriptSegment

# Basic Multilingual Plane Arabic + supplement blocks (letters, digits,
# tatweel, Arabic presentation forms). Used only for diagnostics and for
# text metrics, never for reordering decisions.
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF_]+")

# Word timing trust defaults (FR-08: only karaoke "when timing quality permits")
DEFAULT_MIN_WORD_PROBABILITY = 0.5
# Share of low-confidence words that makes the whole word set unusable.
MAX_LOW_CONFIDENCE_RATIO = 0.5
_MAX_WORD_OVERLAP_SECONDS = 0.001  # tiny tolerance for float rounding

_ASS_COLOR_HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")
_TAG_CHARS_RE = re.compile(r"[{}]")

# ---------------------------------------------------------------------------
# Text metrics
# ---------------------------------------------------------------------------
# The average horizontal advance of a character as a fraction of the ASS
# font size, measured by rendering sample lines through libass itself
# (the only renderer that matters) on the bundled Arabic-capable family.
# Arabic glyphs JOIN, so they are far narrower than Latin: a 30-character
# Arabic line at font size 80 measures ~570 px, i.e. ~0.24 em per
# character, not the ~0.5 em a Latin assumption would predict.
#
# Getting this wrong is what made captions overflow the 1080 px canvas
# before: an over-wide estimate shrinks the text, an under-wide estimate
# pushes it off the edge. The values below are measured + ~4% margin.
_ADVANCE_ARABIC = 0.25
_ADVANCE_LATIN = 0.31
_ADVANCE_SPACE = 0.28
# Bold synthesis widens the glyphs by roughly 10%.
_BOLD_ADVANCE_FACTOR = 1.10

# A cue shorter than this is not worth showing (a flash of text reads as
# a glitch), so it is merged into its neighbour.
_MIN_CUE_SECONDS = 0.35
# How long the last word of a karaoke cue stays highlighted when the
# speaker pauses before the next word.
_MAX_KARAOKE_HOLD_SECONDS = 0.8


class CaptionGenerationError(Exception):
    """Raised when caption content cannot be produced safely."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CaptionWord:
    """A single timed word inside a cue (times are clip-relative seconds)."""

    word: str
    start: float
    end: float


@dataclass
class CaptionCue:
    """One caption cue covering a continuous time span (clip-relative)."""

    start: float
    end: float
    lines: list[str]
    words: list[CaptionWord] = field(default_factory=list)


@dataclass
class CaptionBuildResult:
    """Cues plus honest metadata about which timing path was used."""

    cues: list[CaptionCue]
    timing_granularity: str  # "word" or "segment"
    # True only when reliable word timings exist. Callers combine this with
    # the explicit user karaoke opt-in before emitting \\k tags.
    karaoke_capable: bool
    warnings: list[str]
    arabic_text_present: bool
    hashtags_present: bool


# ---------------------------------------------------------------------------
# Word timing reliability (FR-08: no-karaoke fallback when missing/unreliable)
# ---------------------------------------------------------------------------


def word_timings_reliable(
    segments: list[TranscriptSegment],
    min_probability: float = DEFAULT_MIN_WORD_PROBABILITY,
    max_low_confidence_ratio: float = MAX_LOW_CONFIDENCE_RATIO,
) -> tuple[bool, str | None]:
    """Assess whether word timings are present and self-consistent.

    Returns (reliable, reason). ``reason`` is None when reliable.

    Checks:
    1. Every segment carries a non-empty words list.
    2. Every word has a valid 0 <= start < end ordering.
    3. Words inside a segment are (mostly) monotonic in time.
    4. Where provided, MOST word probabilities are >= min_probability.

    Note on (4): a low word probability means "this word may have been
    mis-transcribed", NOT "this timing is wrong". Arabic ASR word
    probabilities are poorly calibrated — a strict per-word gate disabled
    karaoke for virtually every Arabic clip. The gate is therefore on the
    RATIO of low-confidence words: a handful of odd words is normal and
    still leaves the timing usable, while a majority of low-confidence
    words means the whole word set is suspect.
    """
    words: list[tuple[float, float, float | None]] = []
    low_confidence = 0
    scored = 0
    for seg in segments:
        if not seg.words:
            return False, "missing_words"
        for w in seg.words:
            if w.end <= w.start or w.start < 0.0 or w.end < 0.0:
                return False, "invalid_word_bounds"
            if w.probability is not None:
                scored += 1
                if w.probability < min_probability:
                    low_confidence += 1
            words.append((w.start, w.end, w.probability))
        # Monotonicity within the segment (small float tolerance allowed).
        for i in range(1, len(seg.words)):
            if seg.words[i].start + _MAX_WORD_OVERLAP_SECONDS < seg.words[i - 1].start:
                return False, "non_monotonic"
    if scored and low_confidence / scored > max_low_confidence_ratio:
        return False, "low_confidence"
    return True, None


def count_low_confidence_words(
    segments: list[TranscriptSegment],
    min_probability: float = DEFAULT_MIN_WORD_PROBABILITY,
) -> tuple[int, int]:
    """Return (low-confidence word count, scored word count)."""
    low = 0
    scored = 0
    for seg in segments:
        for w in seg.words or []:
            if w.probability is None:
                continue
            scored += 1
            if w.probability < min_probability:
                low += 1
    return low, scored


def _timing_reason_warning(reason: str) -> str:
    if reason == "missing_words" or reason == "invalid_word_bounds":
        return WARNING_WORD_TIMINGS_MISSING
    if reason == "low_confidence":
        return WARNING_WORD_TIMINGS_LOW_CONFIDENCE
    return WARNING_WORD_TIMINGS_UNRELIABLE


# ---------------------------------------------------------------------------
# Cue construction
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    return min(value, hi)


def _normalize_window(text: str) -> str:
    """Neutralize characters that could attack ASS/SRT structure.

    Transcript data is untrusted (AGENTS.md): override tags must never be
    injectable through cue text. HTML entities are decoded FIRST (platform
    caption tracks ship ``&gt;&gt;`` etc. verbatim) and only then are the
    tag characters neutralized, so an entity cannot smuggle a brace in.
    """
    text = html.unescape(text)
    # Strip speaker turn markers and chevron prefixes (e.g., '>>', '>')
    text = re.sub(r"^\s*>>*\s*", "", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = _TAG_CHARS_RE.sub(lambda m: "(" if m.group() == "{" else ")", text)
    return re.sub(r"\s+", " ", text).strip()


def _char_advance(ch: str, font_size: int, bold: bool = False) -> float:
    if ch == " ":
        advance = font_size * _ADVANCE_SPACE
    elif _ARABIC_RE.match(ch):
        advance = font_size * _ADVANCE_ARABIC
    else:
        advance = font_size * _ADVANCE_LATIN
    if bold:
        advance *= _BOLD_ADVANCE_FACTOR
    return advance


def text_width_px(text: str, font_size: int, bold: bool = False) -> float:
    """Estimated rendered width of ``text`` in ASS PlayRes pixels.

    Deterministic approximation of the font advance; used to keep every
    caption line inside the horizontal safe area instead of guessing a
    character count that only works for one language and font size.
    """
    return sum(_char_advance(ch, font_size, bold) for ch in text)


def line_budget(style: CaptionStyleSettings) -> tuple[float, int]:
    """Return (max line width in px, max characters) for one caption line."""
    usable_width = max(120.0, style.play_res_x - 2 * style.margin_h)
    return usable_width, style.max_chars_per_line


def _wrap_words(
    words: list[str],
    style: CaptionStyleSettings,
) -> list[str]:
    """Wrap words into balanced lines that fit the safe area.

    A word is never split. Lines are balanced towards an even width so the
    caption reads as a tidy block instead of one full line plus a stub.
    The hard width limit is always respected; a single word that is wider
    than the limit overflows honestly (and is flagged by the caller).
    """
    if not words:
        return []
    max_width_px, max_chars = line_budget(style)
    font_size = style.font_size

    widths = [text_width_px(w, font_size, style.bold) for w in words]
    space_w = font_size * _ADVANCE_SPACE * (1.10 if style.bold else 1.0)
    total_width = sum(widths) + space_w * max(0, len(words) - 1)

    lines_needed = max(1, math.ceil(total_width / max_width_px - 1e-9))
    if max_chars > 0:
        lines_needed = max(lines_needed, math.ceil(len(words) / max_chars))
    target_width = total_width / lines_needed

    lines: list[str] = []
    current: list[str] = []
    current_width = 0.0
    current_chars = 0
    for idx, word in enumerate(words):
        gap = space_w if current else 0.0
        candidate = current_width + gap + widths[idx]
        candidate_chars = current_chars + (1 if current else 0) + len(word)
        too_wide = candidate > max_width_px
        too_many_chars = max_chars > 0 and candidate_chars > max_chars
        unbalanced = candidate > target_width * 1.4
        if current and (too_wide or too_many_chars or unbalanced):
            lines.append(" ".join(current))
            current = []
            current_width = 0.0
            current_chars = 0
            candidate = widths[idx]
            candidate_chars = len(word)
        current.append(word)
        current_width = candidate
        current_chars = candidate_chars
    if current:
        lines.append(" ".join(current))
    return lines


def _partition_words_balanced(words: list[str], groups: int) -> list[list[str]]:
    """Split words into ``groups`` chunks of roughly equal character count."""
    if groups <= 1 or not words:
        return [list(words)]
    total_chars = sum(len(w) for w in words)
    target = total_chars / groups

    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    remaining_groups = groups
    for idx, word in enumerate(words):
        remaining_words = len(words) - idx
        current.append(word)
        current_chars += len(word)
        groups_left = remaining_groups - len(chunks)
        words_left = remaining_words - 1
        if len(chunks) < groups - 1 and (current_chars >= target or words_left <= groups_left - 1):
            chunks.append(current)
            current = []
            current_chars = 0
    if current:
        chunks.append(current)
    return chunks


def _split_into_cues(
    words: list[str],
    style: CaptionStyleSettings,
) -> list[list[str]]:
    """Split a cue's text into display cues of at most ``max_lines`` lines."""
    if not words:
        return []
    lines = _wrap_words(words, style)
    if len(lines) <= style.max_lines:
        return [lines]

    group_count = math.ceil(len(lines) / style.max_lines)
    chunks = _partition_words_balanced(words, group_count)
    cues: list[list[str]] = []
    for chunk in chunks:
        chunk_lines = _wrap_words(chunk, style)
        if not chunk_lines:
            continue
        # A chunk should never need more than max_lines; if the balanced
        # split still overflows, keep the lines as they are (honest) rather
        # than dropping text.
        cues.append(chunk_lines)
    return cues


def _distribute_time(
    window_start: float,
    window_end: float,
    weights: list[int],
) -> list[tuple[float, float]]:
    """Split a time window into sub-windows proportional to ``weights``."""
    total = sum(weights)
    if total <= 0 or len(weights) == 0:
        return [(window_start, window_end)]
    span = max(0.0, window_end - window_start)
    out: list[tuple[float, float]] = []
    cursor = window_start
    for idx, weight in enumerate(weights):
        if idx == len(weights) - 1:
            out.append((cursor, window_end))
            break
        end = cursor + span * (weight / total)
        out.append((cursor, end))
        cursor = end
    return out


def _resolve_cue_windows(
    segments: list[TranscriptSegment],
    clip_start_ms: int,
    clip_end_ms: int,
) -> list[tuple[float, float, str]]:
    """Resolve transcript segments into non-overlapping clip-relative windows.

    Each cue's window ends where the NEXT cue starts (rolling platform
    captions) and is clamped to the clip window. Returns a list of
    ``(start_sec, end_sec, text)`` tuples in chronological order.
    """
    ordered = sorted(segments, key=lambda s: (s.start, s.end))
    clip_start = clip_start_ms / 1000.0
    clip_end = clip_end_ms / 1000.0

    windows: list[tuple[float, float, str]] = []
    for idx, seg in enumerate(ordered):
        raw_end = seg.end
        if idx + 1 < len(ordered):
            # Rolling captions: the platform replaces a cue when the next
            # one starts, so the visible window ends at the next start.
            raw_end = min(raw_end, ordered[idx + 1].start)
        # Avoid stale cues from before the cut: if the segment started before
        # clip_start, discard it if only a small tail (< 0.8s or < 35% of the segment)
        # overlaps into the clip.
        if seg.start < clip_start:
            overlap = raw_end - clip_start
            total_seg_len = max(0.1, seg.end - seg.start)
            if overlap < 0.8 or (overlap / total_seg_len) < 0.35:
                continue
        start = max(seg.start, clip_start)
        end = min(raw_end, clip_end)
        text = _normalize_window(seg.text)
        if end - start <= 0.0 or not text:
            continue
        windows.append((start, end, text))
    return windows


def build_cues(
    segments: list[TranscriptSegment],
    clip_start_ms: int,
    clip_end_ms: int,
    style: CaptionStyleSettings,
    *,
    allow_word_cues: bool = True,
    min_word_probability: float = DEFAULT_MIN_WORD_PROBABILITY,
) -> CaptionBuildResult:
    """Build clip-relative caption cues from transcript segments.

    Word-cue path: segments are chunked into display-safe cues sized by
    max characters per line and max stacked lines. The karaoke flag is never
    invented: without reliable timings the fallback path applies.
    """
    if clip_end_ms <= clip_start_ms:
        raise CaptionGenerationError("Clip window is empty (end must be after start).")
    if len(segments) == 0:
        raise CaptionGenerationError("No transcript segments overlap the clip window.")

    warnings: list[str] = []
    text_all = " ".join(seg.text for seg in segments)
    arabic_present = bool(_ARABIC_RE.search(text_all))
    hashtags_present = bool(_HASHTAG_RE.search(text_all))

    reliable, reason = word_timings_reliable(segments, min_word_probability)
    want_words = allow_word_cues and reliable
    if allow_word_cues and not reliable and reason:
        warnings.append(_timing_reason_warning(reason))
    elif want_words:
        # A few low-confidence words do not invalidate the timing, but the
        # user should know those words may be misspelled.
        low, scored = count_low_confidence_words(segments, min_word_probability)
        if scored and low:
            warnings.append(WARNING_WORD_TEXT_LOW_CONFIDENCE.format(low=low, total=scored))

    cues: list[CaptionCue] = []
    granularity = "word" if want_words else "segment"
    overflow_any = False
    split_any = False
    clip_len = _clip_len(clip_start_ms, clip_end_ms)

    if want_words:
        cues, overflow_any, split_any = _build_word_cues(
            segments, clip_start_ms, clip_end_ms, style, clip_len
        )
    else:
        cues, overflow_any, split_any = _build_segment_cues(
            segments, clip_start_ms, clip_end_ms, style, clip_len
        )

    # Honest overflow detection over the final cue set (covers both paths,
    # including single words longer than the line budget).
    overflow_any = overflow_any or any(
        len(line) > style.max_chars_per_line for cue in cues for line in cue.lines
    )
    if overflow_any:
        warnings.append(WARNING_TEXT_OVERFLOW)
    elif split_any:
        # The text was too long for a single cue and was split into several
        # shorter cues so it stays inside the safe area. Disclose it: the
        # timing was distributed proportionally to the text length.
        warnings.append(WARNING_TEXT_SPLIT)

    cues.sort(key=lambda c: (c.start, c.end))
    return CaptionBuildResult(
        cues=cues,
        timing_granularity=granularity,
        karaoke_capable=want_words,
        warnings=warnings,
        arabic_text_present=arabic_present,
        hashtags_present=hashtags_present,
    )


def _build_segment_cues(
    segments: list[TranscriptSegment],
    clip_start_ms: int,
    clip_end_ms: int,
    style: CaptionStyleSettings,
    clip_len: float,
) -> tuple[list[CaptionCue], bool, bool]:
    """Segment-level cues (no word timings available)."""
    cues: list[CaptionCue] = []
    overflow_any = False
    split_any = False

    for start, end, text in _resolve_cue_windows(segments, clip_start_ms, clip_end_ms):
        words = text.split(" ")
        display = _split_into_cues(words, style)
        if len(display) > 1:
            split_any = True
        weights = [sum(len(w) for line in lines for w in line.split(" ")) for lines in display]
        windows = _distribute_time(start, end, weights)
        for lines, (win_start, win_end) in zip(display, windows, strict=False):
            if win_end - win_start <= 0.0:
                continue
            cues.append(
                CaptionCue(
                    start=_clamp(win_start - clip_start_ms / 1000.0, 0.0, clip_len),
                    end=_clamp(win_end - clip_start_ms / 1000.0, 0.0, clip_len),
                    lines=lines,
                )
            )
    return cues, overflow_any, split_any


def _build_word_cues(
    segments: list[TranscriptSegment],
    clip_start_ms: int,
    clip_end_ms: int,
    style: CaptionStyleSettings,
    clip_len: float,
) -> tuple[list[CaptionCue], bool, bool]:
    """Word-level cues with karaoke-ready word timings."""
    cues: list[CaptionCue] = []
    overflow_any = False
    split_any = False
    clip_start = clip_start_ms / 1000.0

    for seg in sorted(segments, key=lambda s: (s.start, s.end)):
        if not seg.words:
            continue
        relative: list[tuple[str, float, float]] = []
        for w in seg.words:
            ws = _clamp(w.start - clip_start, 0.0, clip_len)
            we = _clamp(w.end - clip_start, 0.0, clip_len)
            if we <= ws:
                continue
            relative.append((_normalize_window(w.word), ws, we))
        if not relative:
            continue

        # Group words into display cues of at most max_lines lines. The
        # grouping is driven by the rendered width, so a cue never holds
        # more text than fits the safe area.
        groups: list[list[tuple[str, float, float]]] = []
        current: list[tuple[str, float, float]] = []
        current_width = 0.0
        max_width_px, max_chars = line_budget(style)
        for word, ws, we in relative:
            word_width = text_width_px(word, style.font_size, style.bold)
            gap = (
                style.font_size * _ADVANCE_SPACE * (1.10 if style.bold else 1.0) if current else 0.0
            )
            candidate_lines = len(_wrap_words([w for w, _, _ in current] + [word], style))
            if current and (
                current_width + gap + word_width > max_width_px
                or candidate_lines > style.max_lines
                or (max_chars > 0 and len(current) + 1 > max_chars * style.max_lines)
            ):
                groups.append(current)
                current = []
                current_width = 0.0
            current.append((word, ws, we))
            current_width += gap + word_width
        if current:
            groups.append(current)

        if len(groups) > 1:
            split_any = True

        # Karaoke duration of a word runs until the NEXT word starts, so a
        # pause between words keeps the last word highlighted.
        for group_idx, group in enumerate(groups):
            lines = _wrap_words([w for w, _, _ in group], style)
            if not lines:
                continue
            first_word = group[0]
            last_word = group[-1]
            if group_idx + 1 < len(groups):
                next_start = groups[group_idx + 1][0][1]
            else:
                next_start = max(last_word[2], min(seg.end - clip_start, clip_len))
            hold_end = min(next_start, last_word[2] + _MAX_KARAOKE_HOLD_SECONDS)
            cue_end = max(hold_end, last_word[1] + 0.01)
            cues.append(
                CaptionCue(
                    start=_clamp(first_word[1], 0.0, clip_len),
                    end=_clamp(cue_end, 0.0, clip_len),
                    lines=lines,
                    words=[CaptionWord(word=w, start=s, end=e) for w, s, e in group],
                )
            )
    return cues, overflow_any, split_any


def _clip_len(start_ms: int, end_ms: int) -> float:
    return (end_ms - start_ms) / 1000.0


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------


def _fmt_srt_ts(seconds: float) -> str:
    """SRT timestamp: HH:MM:SS,mmm (note the comma)."""
    ms = int(round(seconds * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _fmt_ass_ts(seconds: float) -> str:
    """ASS timestamp: H:MM:SS.cc (centiseconds)."""
    centis = int(round(seconds * 100))
    hours, rem = divmod(centis, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def hex_to_ass_color(hex_color: str) -> str:
    """Convert '#RRGGBB' to ASS '&H00BBGGRR' (alpha 00 = fully opaque)."""
    match = _ASS_COLOR_HEX_RE.match(hex_color.strip().upper().replace(" ", ""))
    if not match:
        raise CaptionGenerationError(f"Invalid color '{hex_color}'. Expected '#RRGGBB'.")
    rr, gg, bb = match.group(1)[:2], match.group(1)[2:4], match.group(1)[4:6]
    return f"&H00{bb}{gg}{rr}"


ASS_ALIGNMENT = {"bottom": 2, "middle": 5, "top": 8}


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def format_srt(cues: list[CaptionCue]) -> str:
    """Serialize cues into valid SRT-1 UTF-8 content."""
    blocks: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        text = "\n".join(cue.lines)
        blocks.append(f"{idx}\n{_fmt_srt_ts(cue.start)} --> {_fmt_srt_ts(cue.end)}\n{text}")
    return "\n\n".join(blocks) + "\n"


def format_ass(
    cues: list[CaptionCue],
    style: CaptionStyleSettings,
    *,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    enable_karaoke: bool = False,
) -> str:
    """Serialize cues into a single-style ASS subtitle file (PlayRes fixed).

    Karaoke is emitted only when ``enable_karaoke`` is True AND every cue
    carries timings; otherwise plain dialogue lines are produced
    (clean no-karaoke fallback per FR-08).
    """
    if play_res_x <= 0 or play_res_y <= 0:
        raise CaptionGenerationError("PlayRes dimensions must be positive.")

    header = [
        "[Script Info]",
        "; Generated by Laqta caption generator (PRD FR-08).",
        "; Text is stored in logical order; bidi shaping is performed by libass.",
        "; Arabic output requires manual visual QA before any correctness claim.",
        "Title: Laqta Captions",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "WrapStyle: 2",  # explicit manual wrapping; we control line breaks
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
    ]
    karaoke_active = enable_karaoke and all(cue.words for cue in cues)

    # ASS karaoke paints the ALREADY SPOKEN part of the line with
    # PrimaryColour and the part still to come with SecondaryColour. So in
    # karaoke mode PrimaryColour is the highlight colour and
    # SecondaryColour is the plain text colour; without karaoke the
    # PrimaryColour is simply the text colour.
    if karaoke_active:
        primary_colour = hex_to_ass_color(style.highlight_color)
        secondary_colour = hex_to_ass_color(style.foreground_color)
    else:
        primary_colour = hex_to_ass_color(style.foreground_color)
        secondary_colour = hex_to_ass_color(style.foreground_color)

    style_line = (
        "Style: Laqta,"
        f"{style.font_name},{style.font_size},"
        f"{primary_colour},"
        f"{secondary_colour},"
        f"{hex_to_ass_color(style.outline_color)},"
        "&H00000000,"  # back colour (unused, no box)
        f"{-1 if style.bold else 0},0,0,0,100,100,0,0,1,"  # bold + plain
        f"{style.outline_width:.1f},{style.shadow_depth},"  # outline + shadow
        f"{ASS_ALIGNMENT[style.position]},"
        f"{style.margin_h},{style.margin_h},{style.margin_v},1"
    )
    header.append(style_line)
    header += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    for cue in cues:
        text = _build_event_text(cue, karaoke_active)
        events.append(
            f"Dialogue: 0,{_fmt_ass_ts(cue.start)},{_fmt_ass_ts(cue.end)},Laqta,,0,0,0,,{text}"
        )
    return "\n".join(header + events) + "\n"


_RLM = "\u200f"  # RIGHT-TO-LEFT MARK: strong RTL, invisible to libass
_RTL_DIR_TAG = r"{\fe-1}"  # documented libass extension: bidi autodetect mode


def _build_event_text(
    cue: CaptionCue,
    karaoke_active: bool,
) -> str:
    r"""Build one Dialogue text field, safe against override-tag injection.

    RTL handling: with a plain style Encoding, libass hardcodes an LTR base
    direction, which visually reverses the word order of multi-word Arabic
    lines. For cues containing Arabic script we emit the documented libass
    "{\fe-1}" extension (base-direction autodetect) once per event and a
    leading RLM on every visual line (each \N-separated line is its own bidi
    paragraph), pinning RTL even for lines that start with Latin text.

    Karaoke: the ``\k`` tags are emitted INLINE, word after word, inside
    the same visual line. Only real line breaks use ``\N`` — putting every
    word on its own line (as an earlier revision did) produced a vertical
    word list instead of a caption.
    """
    if karaoke_active and cue.words:
        # Pair the rendered tokens with the timed words. The cue lines were
        # produced FROM these very words, so the pairing is positional; a
        # text-based fallback covers the rare case where normalization
        # changed a token.
        tokens: list[tuple[str, list[str]]] = [(line, line.split(" ")) for line in cue.lines]
        flat: list[str] = [tok for _, toks in tokens for tok in toks]
        words = list(cue.words)
        if len(flat) == len(words):
            pairs = list(zip(flat, words, strict=True))
        else:
            pairs = []
            cursor = 0
            for tok in flat:
                found = None
                for idx in range(cursor, len(words)):
                    if words[idx].word == tok:
                        found = words[idx]
                        cursor = idx + 1
                        break
                if found is None:
                    found = words[cursor] if cursor < len(words) else words[-1]
                    cursor = min(cursor + 1, len(words) - 1)
                pairs.append((tok, found))

        # Karaoke duration of a word runs until the NEXT word starts, so a
        # pause between two words keeps the first one highlighted.
        durations: list[float] = []
        for idx, (_tok, word) in enumerate(pairs):
            if idx + 1 < len(pairs):
                durations.append(max(0.0, pairs[idx + 1][1].start - word.start))
            else:
                durations.append(max(0.0, cue.end - word.start))

        visible_lines: list[str] = []
        pos = 0
        for _line, toks in tokens:
            parts: list[str] = []
            for _tok in toks:
                if pos >= len(pairs):
                    break
                word_text, _word = pairs[pos]
                dur = durations[pos]
                parts.append(f"{{\\k{max(1, int(round(dur * 100)))}}}{word_text}")
                pos += 1
            visible_lines.append(" ".join(parts))
    else:
        visible_lines = list(cue.lines)

    has_arabic = _ARABIC_RE.search("\\N".join(visible_lines))
    if has_arabic:
        prefixed = [f"{_RLM}{line}" for line in visible_lines]
        return _RTL_DIR_TAG + ("\\N".join(prefixed))
    # Text is pre-normalized (no braces, no newlines) by _normalize_window.
    return "\\N".join(visible_lines)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def write_caption_files(
    output_dir,
    candidate_id: str,
    result: CaptionBuildResult,
    style: CaptionStyleSettings,
    formats: tuple[str, ...] = ("srt", "ass"),
    enable_karaoke: bool = False,
) -> dict[str, str]:
    """Write SRT/ASS files to a project directory. Returns {format: path}.

    Never overwrites existing useful content silently: callers decide what to
    do about overwrite (the captions endpoint regenerates explicitly).
    """

    from pathlib import Path  # local import to keep module import shell-free

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    if "srt" in formats:
        srt_path = out_dir / f"{candidate_id}.srt"
        srt_path.write_text(format_srt(result.cues), encoding="utf-8")
        written["srt_path"] = str(srt_path)
    if "ass" in formats:
        ass_path = out_dir / f"{candidate_id}.ass"
        ass_path.write_text(
            format_ass(
                result.cues,
                style,
                play_res_x=style.play_res_x,
                play_res_y=style.play_res_y,
                enable_karaoke=enable_karaoke,
            ),
            encoding="utf-8",
        )
        written["ass_path"] = str(ass_path)
    return written
