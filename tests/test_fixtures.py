"""Fixture tests: the committed synthetic VTT sample must stay parseable.

`tests/fixtures/sample_captions_synthetic.ar.vtt` is an original, synthetic
Arabic technical caption track with `align:start position:100%` cue settings,
mixed Arabic/English terms, numbers, and rolling-caption overlap. It guards the
WebVTT parsing path that the YouTube captions-first flow relies on, and it
keeps the committed fixture honest: if the parser breaks on it, the test fails.
"""

from pathlib import Path

from qatta.stages.s02_transcript.youtube_subs import (
    dedup_rolling_cues,
    parse_vtt_cues,
    parse_vtt_ms,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_captions_synthetic.ar.vtt"


def test_fixture_exists_and_is_webvtt() -> None:
    assert FIXTURE.is_file(), "the committed synthetic caption fixture is missing"
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0].strip()
    assert header == "WEBVTT"


def test_parses_cues_with_monotonic_timestamps() -> None:
    cues = parse_vtt_cues(FIXTURE.read_text(encoding="utf-8"))

    assert len(cues) > 10, "the fixture should contain a multi-cue caption track"
    for cue in cues:
        assert cue.end_ms > cue.start_ms
        assert cue.lines, "a cue without text is not a caption"
        for line in cue.lines:
            assert "align:start" not in line
            assert "position:100%" not in line
    # Cues must not run backwards.
    starts = [cue.start_ms for cue in cues]
    assert starts == sorted(starts)


def test_parses_arabic_and_mixed_technical_text_verbatim() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "align:start position:100%" in raw
    cues = parse_vtt_cues(raw)
    joined = " ".join(line for cue in cues for line in cue.lines)
    assert any("\u0600" <= ch <= "\u06ff" for ch in joined), "expected Arabic script"
    assert any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in joined), "expected Latin terms"
    assert any(ch.isdigit() for ch in joined), "expected digits"

    deduped = dedup_rolling_cues(cues)
    assert len(deduped) >= len(cues) - 2
    assert len(deduped) > 10


def test_timestamp_parser_handles_both_decimal_separators() -> None:
    assert parse_vtt_ms("00:00:01.500") == 1500
    assert parse_vtt_ms("00:00:01,500") == 1500
    assert parse_vtt_ms("01:02:03.004") == 3_723_004
