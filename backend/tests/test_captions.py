"""Unit tests for caption generation and rendering helpers (PRD §5 FR-08)."""

import pytest
from pydantic import ValidationError

from app.schemas.captions import (
    WARNING_TEXT_OVERFLOW,
    WARNING_TEXT_SPLIT,
    WARNING_WORD_TIMINGS_MISSING,
    CaptionStyleSettings,
)
from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.captions.generator import (
    build_cues,
    format_ass,
    format_srt,
    hex_to_ass_color,
    word_timings_reliable,
)
from app.services.rendering.render import escape_filter_path


def _segment(
    seg_id: str,
    start: float,
    end: float,
    text: str,
    words: list[WordTiming] | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(id=seg_id, start=start, end=end, text=text, words=words)


STYLE = CaptionStyleSettings(max_chars_per_line=25, max_lines=2)


# ---------------------------------------------------------------------------
# Word-timing reliability (FR-08 karaoke gate)
# ---------------------------------------------------------------------------


def test_word_timings_reliable_when_complete() -> None:
    words = [
        WordTiming(word="مرحبا", start=0.0, end=0.5),
        WordTiming(word="بالعالم", start=0.55, end=1.1),
    ]
    reliable, reason = word_timings_reliable([_segment("s1", 0.0, 1.2, "مرحبا بالعالم", words)])
    assert reliable is True
    assert reason is None


def test_word_timings_missing_triggers_fallback() -> None:
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, "مرحبا بالعالم من القاهرة")],
        clip_start_ms=0,
        clip_end_ms=4000,
        style=STYLE,
    )
    assert result.timing_granularity == "segment"
    assert result.karaoke_capable is False
    assert WARNING_WORD_TIMINGS_MISSING in result.warnings
    # Fallback cues reuse the transcript segment span; timing is never invented.
    assert result.cues[0].start == pytest.approx(0.0)
    assert result.cues[0].end == pytest.approx(2.0)
    assert all(not cue.words for cue in result.cues)


def test_word_timings_non_monotonic_triggers_fallback() -> None:
    words = [
        WordTiming(word="الثاني", start=1.5, end=1.9),
        WordTiming(word="الأول", start=0.0, end=0.5),
    ]
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, "الأول الثاني", words)],
        clip_start_ms=0,
        clip_end_ms=3000,
        style=STYLE,
    )
    assert result.timing_granularity == "segment"
    assert result.karaoke_capable is False


def test_low_confidence_words_trigger_fallback() -> None:
    words = [WordTiming(word="مرحبا", start=0.0, end=0.5, probability=0.2)]
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, "مرحبا", words)],
        clip_start_ms=0,
        clip_end_ms=3000,
        style=STYLE,
    )
    assert result.timing_granularity == "segment"


def test_invalid_word_bounds_trigger_fallback() -> None:
    words = [WordTiming(word="مرحبا", start=1.0, end=0.8)]  # inverted
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, "مرحبا", words)],
        clip_start_ms=0,
        clip_end_ms=3000,
        style=STYLE,
    )
    assert result.timing_granularity == "segment"


# ---------------------------------------------------------------------------
# Cue construction and wrapping
# ---------------------------------------------------------------------------


def test_word_cues_are_clipped_and_ordered() -> None:
    words = [
        WordTiming(word="hello", start=0.0, end=0.4),
        WordTiming(word="world", start=0.45, end=0.9),
        WordTiming(word="three", start=0.95, end=1.4),
    ]
    segments = [_segment("s1", 0.0, 1.5, "hello world three", words)]
    result = build_cues(
        segments=segments,
        clip_start_ms=500,
        clip_end_ms=1500,
        style=CaptionStyleSettings(max_chars_per_line=10, max_lines=2),
    )
    assert result.timing_granularity == "word"
    # Word "hello" (0.0-0.4 s source time) lies fully before the clip start.
    cue_words = [w.word for cue in result.cues for w in cue.words]
    assert "hello" not in cue_words
    assert "world" in cue_words and "three" in cue_words
    clip_len_s = 1500 / 1000.0
    for cue in result.cues:
        assert 0.0 <= cue.start < cue.end <= clip_len_s


def test_long_words_overflow_flagged_not_split() -> None:
    long_word = "كلمة-عربية-فائقة-الطول-دون-مسافات-إطلاقا-وغير-قابلة-للتقطيع"
    segments = [_segment("s1", 0.0, 2.0, long_word)]
    style = CaptionStyleSettings(max_chars_per_line=10, max_lines=2)
    result = build_cues(segments=segments, clip_start_ms=0, clip_end_ms=2500, style=style)
    assert any(len(line) > style.max_chars_per_line for cue in result.cues for line in cue.lines)
    assert WARNING_TEXT_OVERFLOW in result.warnings
    # The word is never split even though it overflows.
    assert any(long_word in line for cue in result.cues for line in cue.lines)


def test_long_segment_text_is_split_not_overflowed() -> None:
    """A long segment is split into several cues instead of overflowing.

    Splitting keeps every line inside the safe area, so the cue no longer
    overflows; the split itself is disclosed through WARNING_TEXT_SPLIT.
    A genuinely unbreakable overflow (one huge word) still raises
    WARNING_TEXT_OVERFLOW - see the test above.
    """
    text = " ".join(["بطيء"] * 30)
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, text)],
        clip_start_ms=0,
        clip_end_ms=2500,
        style=STYLE,
    )
    assert WARNING_TEXT_SPLIT in result.warnings
    assert WARNING_TEXT_OVERFLOW not in result.warnings
    assert len(result.cues) > 1
    for cue in result.cues:
        for line in cue.lines:
            assert len(line) <= STYLE.max_chars_per_line


def test_mixed_arabic_latin_text_stays_logical_order() -> None:
    text = "الاستاذ احمد قال مرحبا with CONTRIBUTING.md من Cairo"
    segments = [_segment("s1", 0.0, 2.0, text)]
    result = build_cues(segments=segments, clip_start_ms=0, clip_end_ms=2500, style=STYLE)
    reconstructed = " ".join(" ".join(cue.lines) for cue in result.cues)
    normalized = " ".join(reconstructed.split())
    assert normalized == " ".join(text.split())  # token order preserved verbatim
    assert result.arabic_text_present is True


def test_cues_outside_clip_window_are_dropped() -> None:
    segments = [
        _segment("before", 0.0, 1.0, "قبل القص"),
        _segment("inside", 2.0, 3.0, "داخل القص"),
        _segment("after", 6.0, 7.0, "بعد القص"),
    ]
    result = build_cues(segments=segments, clip_start_ms=1500, clip_end_ms=4500, style=STYLE)
    texts = " ".join(" ".join(c.lines) for c in result.cues)
    assert "داخل القص" in texts
    # 'before' (0-1 s) is fully outside; 'after' (6-7 s) beyond the clip end.
    assert "قبل القص" not in texts
    assert "بعد القص" not in texts


# ---------------------------------------------------------------------------
# ASS/SRT serialization
# ---------------------------------------------------------------------------


def _word_cue_segments() -> list[TranscriptSegment]:
    return [
        _segment(
            "s1",
            0.0,
            1.0,
            "مرحبا بالعالم",
            [
                WordTiming(word="مرحبا", start=0.0, end=0.5),
                WordTiming(word="بالعالم", start=0.5, end=1.0),
            ],
        )
    ]


def test_srt_timestamp_format_and_numbering() -> None:
    result = build_cues(
        segments=_word_cue_segments(), clip_start_ms=0, clip_end_ms=2000, style=STYLE
    )
    srt = format_srt(result.cues)
    lines = srt.split("\n")
    assert lines[0] == "1"
    assert " --> " in lines[1]
    assert lines[1].startswith("00:00:00,000")  # comma milliseconds per SRT spec
    assert lines[2] == "مرحبا بالعالم"


def test_ass_header_and_colors() -> None:
    assert hex_to_ass_color("#FF00FF") == "&H00FF00FF"  # &H00 BB GG RR
    assert hex_to_ass_color("#000000") == "&H00000000"

    style = CaptionStyleSettings(
        font_name="Noto Sans Arabic", font_size=72, foreground_color="#FFD700"
    )
    result = build_cues(
        segments=_word_cue_segments(), clip_start_ms=0, clip_end_ms=2000, style=style
    )
    ass = format_ass(result.cues, style)
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Laqta,Noto Sans Arabic,72,&H0000D7FF," in ass
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    assert dialogue
    # Dialogue text is the 10th comma field (maxsplit=9 keeps commas in text).
    text_field = dialogue[0].split(",", 9)[-1]
    # Arabic cue: RTL bidi prefix (libass \fe-1 autodetect + RLM), then text.
    assert text_field == ("{\\fe-1}" + "\u200fمرحبا بالعالم")
    assert "ScriptType: v4.00+" in ass


def test_ass_karaoke_centiseconds_math() -> None:
    style = CaptionStyleSettings(karaoke=True)
    result = build_cues(
        segments=_word_cue_segments(), clip_start_ms=0, clip_end_ms=2000, style=style
    )
    assert result.karaoke_capable
    ass = format_ass(result.cues, style, enable_karaoke=True)
    # word 1: 0.0-0.5 s -> \k50; word 2 gets the remaining cue duration (0.5 s).
    tags = [part for part in ass.splitlines() if "{\\k50}" in part]
    assert tags
    assert ass.count("{\\k50}") == 2


def test_karaoke_not_used_when_user_opted_out() -> None:
    style = CaptionStyleSettings(karaoke=False)
    result = build_cues(
        segments=_word_cue_segments(), clip_start_ms=0, clip_end_ms=2000, style=style
    )
    assert result.karaoke_capable is True  # timings are fine, but…
    ass = format_ass(result.cues, style, enable_karaoke=False)
    assert "{\\k" not in ass  # …the plain no-karaoke fallback applies


def test_overrides_cannot_be_injected_via_transcript() -> None:
    malicious_text = "سلام {\\i1}evil} و{\\fsoff}meso"
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, malicious_text)],
        clip_start_ms=0,
        clip_end_ms=2500,
        style=STYLE,
    )
    ass = format_ass(result.cues, STYLE)
    dialogue = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    for line in dialogue:
        text_field = line.split(",", 9)[-1]
        # The generator itself may prepend its own RTL bidi marker prefix;
        # nothing else from the transcript survives as an ASS tag.
        assert text_field.startswith("{\\fe-1}")
        remainder = text_field.removeprefix("{\\fe-1}")
        assert "{" not in remainder.replace("\u200f", "") and "}" not in remainder


# ---------------------------------------------------------------------------
# RTL bidi paragraph control (libass base direction)
# ---------------------------------------------------------------------------


def _dialogue_text_fields(ass: str) -> list[str]:
    return [line.split(",", 9)[-1] for line in ass.splitlines() if line.startswith("Dialogue: 0,")]


_RLM = "\u200f"
_RTL_PREFIX = "{\\fe-1}"


def test_arabic_cues_get_rtl_bidi_prefix_per_line() -> None:
    text = "مرحبا HELLO واخيرا THREE"
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, text)],
        clip_start_ms=0,
        clip_end_ms=2500,
        style=CaptionStyleSettings(max_chars_per_line=12, max_lines=2),
    )
    ass = format_ass(result.cues, STYLE)
    fields = _dialogue_text_fields(ass)
    assert fields
    for field in fields:
        # Event switches libass to base-direction autodetect ...
        assert field.startswith(_RTL_PREFIX + _RLM)
        # ... and every visual line starts with the strong RTL mark, even
        # lines whose first strong character is Latin ('HELLO', 'THREE').
        for line in field.removeprefix(_RTL_PREFIX).split("\\N"):
            assert line.startswith(_RLM)
            assert "مرحبا" in line or "HELLO" in line or "واخيرا" in line or "THREE" in line


def test_latin_only_cues_have_no_bidi_marks() -> None:
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, "hello world again")],
        clip_start_ms=0,
        clip_end_ms=2500,
        style=STYLE,
    )
    ass = format_ass(result.cues, STYLE)
    for field in _dialogue_text_fields(ass):
        assert "{\\fe-1}" not in field
        assert _RLM not in field


def test_srt_output_has_no_bidi_control_characters() -> None:
    text = "مرحبا بالعالم with THREE"
    result = build_cues(
        segments=[_segment("s1", 0.0, 2.0, text)],
        clip_start_ms=0,
        clip_end_ms=2500,
        style=STYLE,
    )
    srt = format_srt(result.cues)
    assert _RLM not in srt
    assert "{\\fe-1}" not in srt
    assert "\u202b" not in srt  # no embedding controls either
    # Logical word order is untouched in the SRT payload.
    assert "مرحبا بالعالم with THREE" in srt


def test_arabic_karaoke_cue_rtl_and_timing_tags_coexist() -> None:
    style = CaptionStyleSettings(max_chars_per_line=25, max_lines=2, karaoke=True)
    result = build_cues(
        segments=_word_cue_segments(), clip_start_ms=0, clip_end_ms=2000, style=style
    )
    ass = format_ass(result.cues, style, enable_karaoke=True)
    fields = _dialogue_text_fields(ass)
    assert len(fields) == 1
    assert fields[0].startswith("{\\fe-1}" + _RLM)
    # Karaoke tags still carry the expected durations, one word per line.
    assert "{\\k50}مرحبا" in fields[0]
    assert "{\\k50}بالعالم" in fields[0]


def test_invalid_colors_raise() -> None:
    with pytest.raises(ValidationError):
        CaptionStyleSettings(foreground_color="red")
    with pytest.raises(ValidationError):
        CaptionStyleSettings(outline_color="#12G34F")


def test_path_escaping_for_filtergraph() -> None:
    escaped = escape_filter_path("/tmp/a b/file:1,2[x]'y.ass")
    assert "\\:" in escaped
    assert "\\," in escaped
    assert "\\[" in escaped and "\\]" in escaped
    assert "\\'" in escaped
