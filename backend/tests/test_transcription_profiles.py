"""Tests for two-pass transcription performance profiles (docs/PERFORMANCE.md).

Validates:
- Profile defaults: fast/balanced/accurate model, compute type, beam, and
  word-timestamp policy (full-video alignment only under 'accurate').
- Explicit request overrides always win over profile defaults.
- Unknown profiles fail with an actionable error.
- The 'accurate' profile carries the "takes longer" warning.
"""

import pytest

from app.core.config import settings
from app.services.transcription.profiles import (
    PROFILE_KEYWORDS_WARNING,
    get_profile_names,
    resolve_transcription_profile,
)


def test_default_profile_is_fast_with_no_full_video_word_alignment() -> None:
    """Default profile: base model, int8, beam 1, and NO word alignment pass."""
    resolved = resolve_transcription_profile(None, settings=settings)
    assert resolved.config.name == "fast"
    assert resolved.config.model_size == settings.FAST_WHISPER_MODEL
    assert resolved.config.compute_type == "int8"
    assert resolved.config.beam_size == 1
    assert resolved.config.word_timestamps is False
    assert resolved.overrides_applied == {}


def test_profile_table_contains_expected_names() -> None:
    """All three advertised profiles must exist."""
    assert set(get_profile_names(settings)) == {"fast", "balanced", "accurate"}


def test_balanced_profile_uses_configured_bigger_model() -> None:
    resolved = resolve_transcription_profile("balanced")
    assert resolved.config.model_size == settings.BALANCED_WHISPER_MODEL
    assert resolved.config.word_timestamps is False
    assert resolved.config.beam_size == 1


def test_accurate_profile_enables_word_alignment_and_warns() -> None:
    """'accurate' runs the full-video word pass and warns about the cost."""
    resolved = resolve_transcription_profile("accurate")
    assert resolved.config.word_timestamps is True
    assert resolved.config.accuracy_warning == PROFILE_KEYWORDS_WARNING
    assert "longer" in resolved.config.accuracy_warning.lower()


def test_explicit_overrides_win_over_profile() -> None:
    resolved = resolve_transcription_profile(
        "fast",
        model_size="tiny",
        beam_size=5,
        word_timestamps=True,
        vad_filter=False,
        compute_type="float32",
    )
    assert resolved.config.model_size == "tiny"
    assert resolved.config.beam_size == 5
    assert resolved.config.word_timestamps is True
    assert resolved.config.vad_filter is False
    assert resolved.config.compute_type == "float32"
    assert resolved.overrides_applied["model_size"] == "tiny"


def test_unknown_profile_rejected() -> None:
    with pytest.raises(ValueError) as exc_info:
        resolve_transcription_profile("turbo-instant")
    assert "fast" in str(exc_info.value)
    assert "accurate" in str(exc_info.value)


def test_profile_schema_to_dict_round_trip() -> None:
    resolved = resolve_transcription_profile("balanced")
    data = resolved.to_dict()
    assert data["profile"] == "balanced"
    resolved2 = resolve_transcription_profile("fast", model_size="base")
    data2 = resolved2.to_dict()
    assert data2["explicit_overrides"] == {"model_size": "base"}
