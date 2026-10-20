"""Tests for the caption timing and layout rules (PRD §5 FR-08).

These cover the behaviour that was fixed after a real render showed
captions that did not match the speaker:

- Platform rolling captions publish overlapping cue windows; the generator
  must resolve them to contiguous, non-overlapping windows.
- Long cues must be split into several readable cues with the time
  distributed proportionally to the text length.
- Lines must be sized from the real font advance so they never spill out
  of the horizontal safe area.
- Karaoke ``\\k`` tags must be inline (one line of words), not one word
  per line.
"""

import pytest

from app.schemas.captions import WARNING_TEXT_SPLIT, CaptionStyleSettings
from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.captions.generator import (
    build_cues,
    format_ass,
    format_srt,
    text_width_px,
)


def _segment(
    seg_id: str,
    start: float,
    end: float,
    text: str,
    words: list[WordTiming] | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(id=seg_id, start=start, end=end, text=text, words=words)


# ---------------------------------------------------------------------------
# Rolling caption windows
# ---------------------------------------------------------------------------


def test_overlapping_cue_windows_are_resolved_to_non_overlapping_spans() -> None:
    """A platform cue stays visible past the next cue's start.

    The next cue replaces it, so the effective window of a cue is
    [start, next_start). Without this the renderer paints two blocks of
    text at once and keeps the already-spoken block on screen.
    """
    segments = [
        _segment("a", 0.0, 13.5, "النص الأول طويل جدا"),
        _segment("b", 9.1, 18.2, "النص الثاني طويل جدا"),
        _segment("c", 15.8, 22.5, "النص الثالث طويل جدا"),
    ]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=30000, style=CaptionStyleSettings()
    )
    spans = [(cue.start, cue.end) for cue in result.cues]
    for (s1, e1), (s2, _e2) in zip(spans, spans[1:], strict=False):
        assert e1 <= s2 + 1e-6, f"cues overlap: {s1}-{e1} then {s2}"
    # The first cue now ends where the second one starts.
    assert spans[0][1] == pytest.approx(9.1, abs=0.05)
    assert spans[1][1] == pytest.approx(15.8, abs=0.05)


def test_non_overlapping_segments_keep_their_own_end() -> None:
    """Ordinary ASR segments are untouched by the rolling-cue rule."""
    segments = [
        _segment("a", 0.0, 2.0, "اول"),
        _segment("b", 2.0, 4.0, "ثاني"),
    ]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=5000, style=CaptionStyleSettings()
    )
    assert result.cues[0].end == pytest.approx(2.0)
    assert result.cues[1].start == pytest.approx(2.0)


def test_cue_fully_before_the_clip_start_is_dropped() -> None:
    segments = [
        _segment("a", 0.0, 5.0, "قبل القص"),
        _segment("b", 5.0, 8.0, "داخل القص"),
    ]
    result = build_cues(
        segments=segments, clip_start_ms=5000, clip_end_ms=8000, style=CaptionStyleSettings()
    )
    texts = " ".join(" ".join(c.lines) for c in result.cues)
    assert "قبل القص" not in texts
    assert "داخل القص" in texts


# ---------------------------------------------------------------------------
# Cue splitting
# ---------------------------------------------------------------------------


def test_long_text_is_split_into_several_cues_with_distributed_time() -> None:
    text = " ".join(["كلمة"] * 60)
    result = build_cues(
        segments=[_segment("s1", 0.0, 12.0, text)],
        clip_start_ms=0,
        clip_end_ms=15000,
        style=CaptionStyleSettings(max_chars_per_line=24, max_lines=2, font_size=90),
    )
    assert len(result.cues) > 1
    assert WARNING_TEXT_SPLIT in result.warnings
    # The sub-cues tile the original window without gaps or overlaps.
    assert result.cues[0].start == pytest.approx(0.0)
    assert result.cues[-1].end == pytest.approx(12.0)
    for prev, nxt in zip(result.cues, result.cues[1:], strict=False):
        assert prev.end == pytest.approx(nxt.start, abs=1e-6)
    # Every word is preserved, in order.
    reconstructed = " ".join(" ".join(c.lines) for c in result.cues)
    assert reconstructed.split() == text.split()


def test_each_cue_stays_within_the_configured_line_budget() -> None:
    text = " ".join(["كلمة"] * 60)
    style = CaptionStyleSettings(max_chars_per_line=24, max_lines=2, font_size=90)
    result = build_cues(
        segments=[_segment("s1", 0.0, 12.0, text)], clip_start_ms=0, clip_end_ms=15000, style=style
    )
    for cue in result.cues:
        assert len(cue.lines) <= style.max_lines
        for line in cue.lines:
            assert len(line) <= style.max_chars_per_line


# ---------------------------------------------------------------------------
# Font metrics / safe area
# ---------------------------------------------------------------------------


def test_line_width_fits_the_horizontal_safe_area() -> None:
    """Every produced line must stay inside the horizontal safe area."""
    style = CaptionStyleSettings(font_size=110, margin_h=60, play_res_x=1080)
    usable = style.play_res_x - 2 * style.margin_h
    text = " ".join(["وهنا نص عربي طويل"] * 12)
    result = build_cues(
        segments=[_segment("s1", 0.0, 12.0, text)],
        clip_start_ms=0,
        clip_end_ms=15000,
        style=style,
    )
    assert result.cues
    for cue in result.cues:
        for line in cue.lines:
            assert text_width_px(line, style.font_size, style.bold) <= usable


def test_arabic_is_narrower_than_latin_at_the_same_font_size() -> None:
    """Arabic letters join, so they must be measured narrower than Latin."""
    arabic = text_width_px("مضطربة", 100, bold=True)
    latin = text_width_px("abcdefg", 100, bold=True)
    assert arabic < latin


# ---------------------------------------------------------------------------
# Karaoke rendering
# ---------------------------------------------------------------------------


def _karaoke_segments() -> list[TranscriptSegment]:
    return [
        _segment(
            "s1",
            0.0,
            2.0,
            "مرحبا بالعالم",
            [
                WordTiming(word="مرحبا", start=0.0, end=0.5),
                WordTiming(word="بالعالم", start=0.5, end=1.2),
                WordTiming(word="اليوم", start=1.2, end=2.0),
            ],
        )
    ]


def test_karaoke_tags_stay_inline_instead_of_one_word_per_line() -> None:
    """An earlier revision emitted one \\N-separated line per word."""
    style = CaptionStyleSettings(max_chars_per_line=30, max_lines=2, karaoke=True)
    result = build_cues(
        segments=_karaoke_segments(), clip_start_ms=0, clip_end_ms=3000, style=style
    )
    ass = format_ass(result.cues, style, enable_karaoke=True)
    dialogue = [ln for ln in ass.splitlines() if ln.startswith("Dialogue: 0,")]
    assert dialogue
    text_field = dialogue[0].split(",", 9)[-1]
    # A single visual line holds all three words.
    assert text_field.count("\\N") == 0
    assert "مرحبا" in text_field and "بالعالم" in text_field and "اليوم" in text_field
    assert "{\\k" in text_field


def test_karaoke_highlight_colour_is_the_primary_colour() -> None:
    style = CaptionStyleSettings(
        karaoke=True, foreground_color="#FFFFFF", highlight_color="#00F2FE"
    )
    result = build_cues(
        segments=_karaoke_segments(), clip_start_ms=0, clip_end_ms=3000, style=style
    )
    ass = format_ass(result.cues, style, enable_karaoke=True)
    style_line = [ln for ln in ass.splitlines() if ln.startswith("Style:")][0]
    # &H00BBGGRR: #00F2FE -> &H00FEF200
    assert "&H00FEF200,&H00FFFFFF," in style_line


def test_low_confidence_words_do_not_disable_karaoke_on_their_own() -> None:
    """A handful of odd words must not switch the whole pass off.

    Arabic ASR word probabilities are poorly calibrated: a strict per-word
    gate disabled the word highlight for virtually every Arabic clip.
    """
    words = [
        WordTiming(word="اول", start=0.0, end=0.4, probability=0.9),
        WordTiming(word="ثاني", start=0.4, end=0.8, probability=0.3),
        WordTiming(word="ثالث", start=0.8, end=1.2, probability=0.2),
        WordTiming(word="رابع", start=1.2, end=1.6, probability=0.8),
    ]
    segments = [_segment("s1", 0.0, 1.6, "اول ثاني ثالث رابع", words)]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=2000, style=CaptionStyleSettings()
    )
    assert result.timing_granularity == "word"
    assert result.karaoke_capable is True


def test_mostly_low_confidence_words_still_fall_back() -> None:
    words = [
        WordTiming(word="a", start=0.0, end=0.4, probability=0.1),
        WordTiming(word="b", start=0.4, end=0.8, probability=0.1),
        WordTiming(word="c", start=0.8, end=1.2, probability=0.9),
    ]
    segments = [_segment("s1", 0.0, 1.2, "a b c", words)]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=2000, style=CaptionStyleSettings()
    )
    assert result.timing_granularity == "segment"
    assert result.karaoke_capable is False


# ---------------------------------------------------------------------------
# Text hygiene
# ---------------------------------------------------------------------------


def test_html_entities_in_platform_captions_are_decoded() -> None:
    """YouTube caption tracks ship ``&gt;&gt;`` verbatim."""
    segments = [_segment("s1", 0.0, 2.0, "ليه مش هنحارب &gt;&gt; في الايام")]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=3000, style=CaptionStyleSettings()
    )
    text = " ".join(" ".join(c.lines) for c in result.cues)
    assert "&gt;" not in text
    assert ">>" in text


def test_srt_cue_numbers_and_timestamps_stay_contiguous() -> None:
    segments = [
        _segment("a", 0.0, 13.5, "النص الأول"),
        _segment("b", 9.1, 18.2, "النص الثاني"),
    ]
    result = build_cues(
        segments=segments, clip_start_ms=0, clip_end_ms=30000, style=CaptionStyleSettings()
    )
    srt = format_srt(result.cues)
    blocks = [b for b in srt.strip().split("\n\n") if b]
    assert [b.splitlines()[0] for b in blocks] == [str(i + 1) for i in range(len(blocks))]
