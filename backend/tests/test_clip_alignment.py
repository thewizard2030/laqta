"""Tests for Pass B clip alignment: offset conversion, absolute timestamps,
consistency validation, and the failure contract (never silently discard a
transcript).

The real faster-whisper model is mocked; these tests validate the pure
offset logic and error paths, not model quality.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.media.audio import JobCancelledError
from app.services.transcription.alignment import (
    align_clip_words,
    convert_words_to_absolute,
    validate_word_absolute_timings,
)
from app.services.transcription.base import TranscriptionError


def _word(token: str, start: float, end: float, probability: float | None = 0.9):
    return SimpleNamespace(word=token, start=start, end=end, probability=probability)


def _segment(start: float, text: str, words):
    return SimpleNamespace(start=start, text=text, words=words)


class _FakeWhisperModel:
    """Mimics the faster-whisper transcribe generator surface."""

    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, language=None, beam_size=5, word_timestamps=True, **kwargs):
        info = SimpleNamespace(
            language="en" if language in (None, "en") else language,
            language_probability=0.97,
            duration=3.0,
        )
        return (iter(self._segments), info)


@pytest.fixture
def dummy_clip_audio(tmp_path: Path, monkeypatch) -> Path:
    """Writable 16 kHz-ish audio stub whose decode is mocked."""
    path = tmp_path / "clip.wav"
    path.write_bytes(b"RIFF0000WAVE")
    monkeypatch.setattr(
        "app.services.transcription.alignment._decode_audio_to_float32",
        lambda audio_path, max_duration_sec=None: __import__("numpy").zeros(48000, dtype="float32"),
    )
    return path


@pytest.mark.asyncio
async def test_convert_words_to_absolute_preserves_offset() -> None:
    """Local clip times map to absolute times via the single clip offset."""
    converted = convert_words_to_absolute(
        [("hello", 0.25, 0.5, 0.8), ("world", 0.5, 1.25, 0.7)], clip_start_sec=95.0
    )
    assert [(w.word, w.start, w.end) for w in converted] == [
        ("hello", 95.25, 95.5),
        ("world", 95.5, 96.25),
    ]
    assert converted[0].probability == 0.8


def test_validate_word_absolute_timings_rejects_bad_data() -> None:
    good = [WordTiming(word="hi", start=10.0, end=10.4)]
    clip_start, clip_end = 10.0, 15.0
    assert validate_word_absolute_timings(good, clip_start, clip_end) is None

    empty: list[WordTiming] = []
    assert validate_word_absolute_timings(empty, clip_start, clip_end) == "no_words_detected"

    reversed_word = [WordTiming(word="hi", start=12.0, end=11.0)]
    assert (
        validate_word_absolute_timings(reversed_word, clip_start, clip_end) == "invalid_word_bounds"
    )

    outside = [WordTiming(word="hi", start=9.0, end=9.4)]
    assert (
        validate_word_absolute_timings(outside, clip_start, clip_end) == "word_outside_clip_range"
    )

    non_monotonic = [
        WordTiming(word="a", start=14.0, end=14.5),
        WordTiming(word="b", start=12.0, end=12.5),
    ]
    assert (
        validate_word_absolute_timings(non_monotonic, clip_start, clip_end) == "non_monotonic_words"
    )


@pytest.mark.asyncio
async def test_align_clip_words_returns_absolute_timestamps(
    dummy_clip_audio: Path, monkeypatch
) -> None:
    """Aligned words carry absolute source timestamps (offset added once)."""
    clip_start_ms = 40_000  # clip starts at 40 s
    segments = [_segment(0.5, "one two", [_word("one", 0.5, 0.9), _word("two", 1.0, 1.6)])]

    monkeypatch.setattr(
        "app.services.transcription.alignment.load_whisper_model",
        _make_async_loader(_FakeWhisperModel(segments)),
    )
    aligned = await align_clip_words(
        clip_audio_path=dummy_clip_audio,
        clip_start_ms=clip_start_ms,
        clip_duration_ms=30_000,
        language="en",
    )

    assert aligned.word_count == 2
    assert aligned.clip_start_sec == pytest.approx(40.0)
    words = aligned.words
    assert words[0].start == pytest.approx(40.5)
    assert words[0].end == pytest.approx(40.9)
    assert words[1].start == pytest.approx(41.0)
    assert words[1].end == pytest.approx(41.6)
    assert aligned.segments[0].text == "one two"
    assert aligned.language == "en"


@pytest.mark.asyncio
async def test_align_clip_words_raises_when_no_words(dummy_clip_audio: Path, monkeypatch) -> None:
    """No speech detected => explicit error, NOT an empty transcript."""
    segments = [_segment(0.5, ".", [])]
    monkeypatch.setattr(
        "app.services.transcription.alignment.load_whisper_model",
        _make_async_loader(_FakeWhisperModel(segments)),
    )
    with pytest.raises(TranscriptionError) as exc_info:
        await align_clip_words(
            clip_audio_path=dummy_clip_audio,
            clip_start_ms=1000,
            clip_duration_ms=30_000,
        )
    assert "no_words_detected" in exc_info.value.error_code.lower() or (
        "no_words" in exc_info.value.error_code
    )


@pytest.mark.asyncio
async def test_align_clip_words_propagates_cancellation(
    dummy_clip_audio: Path, monkeypatch
) -> None:
    cancel_event = asyncio.Event()
    cancel_event.set()

    def _never_called(model_size, compute_type=None):
        raise AssertionError("model must not load for pre-cancelled alignment")

    monkeypatch.setattr(
        "app.services.transcription.alignment.load_whisper_model",
        _never_called,
    )
    with pytest.raises(JobCancelledError):
        await align_clip_words(
            clip_audio_path=dummy_clip_audio,
            clip_start_ms=0,
            clip_duration_ms=5_000,
            cancel_event=cancel_event,
        )


@pytest.mark.asyncio
async def test_align_clip_words_missing_audio(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError) as exc_info:
        await align_clip_words(
            clip_audio_path=tmp_path / "missing.wav",
            clip_start_ms=0,
            clip_duration_ms=5_000,
        )
    assert exc_info.value.error_code == "AUDIO_NOT_FOUND"


@pytest.mark.asyncio
async def test_align_clip_words_groups_segments_on_long_pause(
    dummy_clip_audio: Path, monkeypatch
) -> None:
    """A >1 s pause produces a new aligned segment (caption-friendly)."""
    segments = [
        _segment(
            0.0,
            "a b c d",
            [
                _word("a", 0.0, 0.2),
                _word("b", 0.3, 0.5),
                _word("c", 5.0, 5.2),
                _word("d", 5.3, 5.5),
            ],
        )
    ]
    monkeypatch.setattr(
        "app.services.transcription.alignment.load_whisper_model",
        _make_async_loader(_FakeWhisperModel(segments)),
    )
    aligned = await align_clip_words(
        clip_audio_path=dummy_clip_audio,
        clip_start_ms=0,
        clip_duration_ms=30_000,
    )
    assert len(aligned.segments) == 2
    assert aligned.segments[0].text == "a b"
    assert aligned.segments[1].text == "c d"


def _make_async_loader(model):
    async def _loader(model_size, *args, **kwargs):
        return model

    return _loader


def test_transcript_segment_still_type_checked(tmp_path: Path) -> None:
    """Guard: alignment uses the validated TranscriptSegment schema."""
    seg = TranscriptSegment(
        id="s",
        start=0.0,
        end=1.0,
        text="x",
        words=[WordTiming(word="x", start=0, end=1)],
    )
    assert seg.words[0].word == "x"
