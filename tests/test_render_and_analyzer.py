"""Tests for the two stages that produce the product.

The renderer turns a selected clip into the 1080×1920 MP4 the user exports,
and the analyser produces the acoustic signals the ranker scores on. Both
are pure enough to test without a model or a GPU.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from qatta.core.schema import AtomicUtterance, QattaManifest, WordToken
from qatta.stages.s03_multimodal.analyzer import (
    _silence_threshold,
    compute_utterance_acoustics,
)
from qatta.stages.s06_render.renderer import utterances_to_segments


def _utterance(
    u_id: str = "U_0001",
    text: str = "مرحبا",
    start_ms: int = 0,
    end_ms: int = 2000,
    with_words: bool = True,
) -> AtomicUtterance:
    words = (
        [
            WordToken(
                word=text.split()[0],
                start_ms=start_ms,
                end_ms=start_ms + 400,
                confidence=0.9,
                is_latin=False,
            )
        ]
        if with_words
        else []
    )
    return AtomicUtterance(
        u_id=u_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        words=words,
    )


# ---------------------------------------------------------------------------
# s06_render — utterances become caption segments
# ---------------------------------------------------------------------------


def test_utterances_become_segments_with_word_timings() -> None:
    segments = utterances_to_segments(
        [_utterance("U_0001", "الكلمة الأولى"), _utterance("U_0002", "الثانية", 2000, 4000)]
    )

    assert len(segments) == 2
    assert segments[0].id == "1"
    assert segments[0].text == "الكلمة الأولى"
    assert segments[0].start == 0.0
    assert segments[0].end == 2.0
    assert len(segments[0].words) == 1
    assert segments[0].words[0].word == "الكلمة"
    # The second segment starts where the first ended.
    assert segments[1].start == 2.0
    assert segments[1].end == 4.0


def test_utterances_without_words_produce_segments_without_words() -> None:
    segments = utterances_to_segments([_utterance(with_words=False)])

    assert len(segments) == 1
    assert segments[0].words == []


def test_empty_utterance_list_produces_no_segments() -> None:
    assert utterances_to_segments([]) == []


# ---------------------------------------------------------------------------
# s03_multimodal — the acoustic signals the ranker scores on
# ---------------------------------------------------------------------------


def _tone(seconds: float, sr: int, freq: float = 220.0, amplitude: float = 0.4) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amplitude * np.sin(2 * math.pi * freq * t)).astype(np.float32)


def test_acoustics_report_rms_and_pitch_for_a_tone() -> None:
    sr = 16000
    pcm = _tone(2.0, sr, freq=220.0, amplitude=0.5)
    utterance = _utterance("U_0001", "نغمة", 0, 2000)

    values = compute_utterance_acoustics(pcm, sr, utterance)

    assert values["rms"] > 0.1
    # A pure tone has (almost) no pitch variance.
    assert values["pitch_variance"] is None or values["pitch_variance"] < 50.0
    assert values["silence_ratio"] is not None
    assert 0.0 <= values["silence_ratio"] <= 1.0


def test_acoustics_detect_silence() -> None:
    sr = 16000
    pcm = np.zeros(sr * 2, dtype=np.float32)
    utterance = _utterance("U_0001", "صمت", 0, 2000)

    values = compute_utterance_acoustics(pcm, sr, utterance)

    assert values["rms"] == 0.0
    # A digitally silent clip must count as silent — it used to report 0.0,
    # which let a silent clip score as if it had speech.
    assert values["silence_ratio"] == 1.0


def test_acoustics_handle_an_empty_span() -> None:
    """An utterance outside the audio must not raise — it must degrade."""
    sr = 16000
    pcm = _tone(1.0, sr)
    utterance = _utterance("U_0001", "خارج", 5000, 6000)

    values = compute_utterance_acoustics(pcm, sr, utterance)

    assert values["rms"] == 0.0
    assert values["pitch_variance"] is None


def test_silence_threshold_scales_with_the_signal() -> None:
    """The threshold is relative to the signal, not a fixed constant."""
    quiet = np.array([0.001, 0.002, 0.001, 0.002], dtype=np.float32)
    loud = np.array([0.4, 0.5, 0.45, 0.5], dtype=np.float32)

    assert _silence_threshold(quiet) > 0.0
    assert _silence_threshold(loud) > _silence_threshold(quiet)


def test_the_stage_persists_the_measured_signals(tmp_path: Path) -> None:
    """The stage writes the measured signals back onto the utterances."""
    import wave

    from qatta.stages.s03_multimodal.analyzer import run_multimodal_stage

    sr = 16000
    pcm = _tone(2.0, sr, amplitude=0.3)
    wav_path = tmp_path / "audio_16k.wav"
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes((pcm * 32767).astype("<i2").tobytes())

    manifest = QattaManifest(
        project_id="proj_acoustics",
        source_path=str(wav_path),
        audio_16k_path=str(wav_path),
        duration_sec=2.0,
        atomic_utterances=[
            _utterance("U_0001", "أول", 0, 1000),
            _utterance("U_0002", "ثاني", 1000, 2000),
        ],
    )

    updated = run_multimodal_stage(manifest)

    for utterance in updated.atomic_utterances:
        assert utterance.audio_rms_norm is not None
        assert 0.0 <= utterance.audio_rms_norm <= 1.0
        assert utterance.silence_ratio is not None
        assert 0.0 <= utterance.silence_ratio <= 1.0
    # The loudest utterance is normalised to 1.0.
    assert max(u.audio_rms_norm or 0.0 for u in updated.atomic_utterances) == 1.0


@pytest.mark.parametrize("utterance_count", [0, 1, 5])
def test_manifest_round_trips_through_the_segments(utterance_count: int) -> None:
    """The manifest keeps its shape through the conversion."""
    utterances = [
        _utterance(f"U_{index:04d}", f"نص {index}", index * 1000, index * 1000 + 900)
        for index in range(1, utterance_count + 1)
    ]
    manifest = QattaManifest(
        project_id="proj_render",
        source_path="/tmp/source.mp4",
        duration_sec=30.0,
        atomic_utterances=utterances,
    )

    segments = utterances_to_segments(manifest.atomic_utterances)

    assert len(segments) == utterance_count
    assert [segment.id for segment in segments] == [
        str(index) for index in range(1, utterance_count + 1)
    ]
