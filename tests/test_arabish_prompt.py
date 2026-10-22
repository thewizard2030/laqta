"""The language prior must follow the language.

The Arablish prompt describes an Egyptian Arabic podcast. On Arabic or
auto-detected audio it helps. On audio that is explicitly **not** Arabic it
does the opposite: Whisper starts producing Arabic text for English speech
and the transcript degrades into repetition.

These tests pin that behaviour, because it was found by the benchmark rather
than by a unit test — the ranking looked broken until the cause was the
prompt.
"""

from __future__ import annotations

import pytest

from qatta.core.config import QattaSettings
from qatta.stages.s02_transcript.fast_pass import should_use_arabish_prompt


@pytest.fixture()
def settings() -> QattaSettings:
    return QattaSettings(_env_file=None)


@pytest.mark.parametrize("profile", ["ar-EG-mixed", "ar", "ar-EG"])
def test_arabic_keeps_the_prior(profile: str, settings: QattaSettings) -> None:
    assert should_use_arabish_prompt(profile, settings) is True


@pytest.mark.parametrize("profile", ["en", "en-US", "en-GB"])
def test_english_does_not_get_the_arabic_prior(profile: str, settings: QattaSettings) -> None:
    assert should_use_arabish_prompt(profile, settings) is False


def test_auto_detection_keeps_the_prior(settings: QattaSettings) -> None:
    """Unknown language: the mixed prior is the safer default."""
    assert should_use_arabish_prompt("", settings) is True
    assert should_use_arabish_prompt("mixed", settings) is True


def test_the_prior_can_be_switched_off(settings: QattaSettings) -> None:
    settings.arabish_initial_prompt = False

    assert should_use_arabish_prompt("ar-EG-mixed", settings) is False
    assert should_use_arabish_prompt("", settings) is False
