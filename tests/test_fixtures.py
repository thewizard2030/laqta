"""Fixture tests: the committed VTT sample must stay parseable.

`tests/fixtures/sample_captions.ar.vtt` is a real Arabic caption track with
`align`/`position` cue settings. It guards the WebVTT parsing path that the
YouTube captions-first flow relies on, and it keeps the committed fixture
honest: if the parser breaks on it, the test fails.
"""

from pathlib import Path

from qatta.stages.s02_transcript.youtube_subs import parse_vtt_cues, parse_vtt_ms

FIXTURE = Path(__file__).parent / "fixtures" / "sample_captions.ar.vtt"


def test_fixture_exists_and_is_webvtt() -> None:
    assert FIXTURE.is_file(), "the committed caption fixture is missing"
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0].strip()
    assert header == "WEBVTT"


def test_parses_cues_with_monotonic_timestamps() -> None:
    cues = parse_vtt_cues(FIXTURE.read_text(encoding="utf-8"))

    assert len(cues) > 10, "the fixture should contain a real caption track"
    for cue in cues:
        assert cue.end_ms > cue.start_ms
        assert cue.lines, "a cue without text is not a caption"
    # Cues must not run backwards.
    starts = [cue.start_ms for cue in cues]
    assert starts == sorted(starts)


def test_parses_arabic_text_verbatim() -> None:
    cues = parse_vtt_cues(FIXTURE.read_text(encoding="utf-8"))
    joined = " ".join(line for cue in cues for line in cue.lines)
    assert any("؀" <= ch <= "ۿ" for ch in joined), "expected Arabic script"


def test_timestamp_parser_handles_both_decimal_separators() -> None:
    assert parse_vtt_ms("00:00:01.500") == 1500
    assert parse_vtt_ms("00:00:01,500") == 1500
    assert parse_vtt_ms("01:02:03.004") == 3_723_004
