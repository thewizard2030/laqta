"""Tests for the scoring stage — the product's central claim.

The Clip Potential Score is what Laqta promises: an *explainable* ranking.
These tests pin the behaviour that makes the claim true:

- the score is a bounded, weighted sum of measured signals
- a missing signal redistributes its weight instead of counting as zero
- an unknown archetype is an error, not a silent default
- the signals are deterministic functions of the measured analytics
"""

from __future__ import annotations

import pytest

from qatta.core.pipeline import PipelineError
from qatta.stages.s05_ranking.scorer import (
    ARCHETYPE_WEIGHTS,
    _signal_functions,
    check_duration,
    compute_cps,
)


def test_every_archetype_has_weights() -> None:
    assert ARCHETYPE_WEIGHTS
    for archetype, weights in ARCHETYPE_WEIGHTS.items():
        assert weights, f"{archetype} has no weights"
        assert all(weight >= 0 for weight in weights.values())


def test_a_perfect_candidate_scores_100() -> None:
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    score, _ = compute_cps(
        archetype,
        standalone_clarity=10.0,
        hook_strength=10.0,
        story_payoff=10.0,
        value_originality=10.0,
        audio_dynamics=10.0,
        visual_composition=10.0,
        boundary_precision=10.0,
    )

    assert score == 100.0


def test_a_zero_candidate_scores_0() -> None:
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    score, _ = compute_cps(
        archetype,
        standalone_clarity=0.0,
        hook_strength=0.0,
        story_payoff=0.0,
        value_originality=0.0,
        audio_dynamics=0.0,
        visual_composition=0.0,
        boundary_precision=0.0,
    )

    assert score == 0.0


def test_the_score_is_always_bounded() -> None:
    """Out-of-range component values must not escape the 0-100 range."""
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    score, _ = compute_cps(
        archetype,
        standalone_clarity=50.0,
        hook_strength=50.0,
        story_payoff=50.0,
        value_originality=50.0,
        audio_dynamics=50.0,
        visual_composition=50.0,
        boundary_precision=50.0,
    )

    assert 0.0 <= score <= 100.0


def test_a_missing_signal_redistributes_its_weight() -> None:
    """An unmeasured signal must not count as zero.

    The weights are renormalised over the measured components, so dropping a
    component changes the *mix*, not the score of a perfect candidate.
    """
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    score_without, effective = compute_cps(
        archetype,
        standalone_clarity=10.0,
        hook_strength=10.0,
        story_payoff=10.0,
        value_originality=10.0,
        audio_dynamics=10.0,
        visual_composition=None,
        boundary_precision=10.0,
    )

    assert "visual_composition" not in effective
    assert sum(effective.values()) == pytest.approx(1.0)
    assert score_without == 100.0


def test_the_effective_weights_sum_to_one() -> None:
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    _, effective = compute_cps(
        archetype,
        standalone_clarity=7.0,
        hook_strength=7.0,
        story_payoff=7.0,
        value_originality=7.0,
        audio_dynamics=7.0,
        visual_composition=7.0,
        boundary_precision=7.0,
    )

    assert sum(effective.values()) == pytest.approx(1.0)


def test_an_unknown_archetype_is_an_error() -> None:
    with pytest.raises(PipelineError) as excinfo:
        compute_cps(
            "not-an-archetype",
            standalone_clarity=5.0,
            hook_strength=5.0,
            story_payoff=5.0,
            value_originality=5.0,
            audio_dynamics=5.0,
            visual_composition=5.0,
            boundary_precision=5.0,
        )

    assert "not-an-archetype" in str(excinfo.value)


def test_a_higher_signal_raises_the_score() -> None:
    archetype = next(iter(ARCHETYPE_WEIGHTS))
    low, _ = compute_cps(
        archetype,
        standalone_clarity=2.0,
        hook_strength=2.0,
        story_payoff=2.0,
        value_originality=2.0,
        audio_dynamics=2.0,
        visual_composition=2.0,
        boundary_precision=2.0,
    )
    high, _ = compute_cps(
        archetype,
        standalone_clarity=8.0,
        hook_strength=8.0,
        story_payoff=8.0,
        value_originality=8.0,
        audio_dynamics=8.0,
        visual_composition=8.0,
        boundary_precision=8.0,
    )

    assert high > low


# ---------------------------------------------------------------------------
# The deterministic signals
# ---------------------------------------------------------------------------


class _Row:
    """A minimal stand-in for an utterance analytics row."""

    def __init__(
        self,
        text: str,
        audio_rms_norm: float = 0.5,
        pause_after_ms: int = 0,
        pitch_variance: float | None = 0.0,
    ) -> None:
        self.text = text
        self.audio_rms_norm = audio_rms_norm
        self.pause_after_ms = pause_after_ms
        self.pitch_variance = pitch_variance


def test_signals_are_bounded_and_deterministic() -> None:
    rows = [
        _Row("مقدمة قصيرة", audio_rms_norm=0.4, pause_after_ms=600),
        _Row("الجزء المهم من الحل", audio_rms_norm=0.8, pause_after_ms=200),
    ]

    first = _signal_functions(rows)
    second = _signal_functions(rows)

    assert first == second, "the signals must be deterministic"
    for name, value in first.items():
        assert 0.0 <= value <= 10.0, f"{name} escaped the 0-10 range: {value}"


def test_a_longer_pause_after_the_hook_raises_the_hook_signal() -> None:
    short = _signal_functions([_Row("بداية", pause_after_ms=0)])
    long = _signal_functions([_Row("بداية", pause_after_ms=2000)])

    assert long["hook_strength"] > short["hook_strength"]


def test_a_longer_pause_at_the_end_raises_the_payoff_signal() -> None:
    rows = [_Row("نص", pause_after_ms=0)]
    short = _signal_functions(rows)

    rows[-1].pause_after_ms = 2000
    long = _signal_functions(rows)

    assert long["story_payoff"] > short["story_payoff"]


def test_more_loudness_variation_raises_the_audio_dynamics_signal() -> None:
    flat = _signal_functions([_Row("أ", audio_rms_norm=0.5), _Row("ب", audio_rms_norm=0.5)])
    varied = _signal_functions([_Row("أ", audio_rms_norm=0.9), _Row("ب", audio_rms_norm=0.1)])

    assert varied["audio_dynamics"] > flat["audio_dynamics"]


def test_boundary_precision_is_a_fixed_measured_default() -> None:
    """The boundary signal is not a heuristic — it is the measured value."""
    signals = _signal_functions([_Row("نص")])

    assert signals["boundary_precision"] == 7.5


# ---------------------------------------------------------------------------
# The duration gate
# ---------------------------------------------------------------------------


def test_the_duration_gate_rejects_a_too_short_clip() -> None:
    class _Candidate:
        clip_id = "cand_1"
        duration_sec = 3.0

    from qatta.core.config import QattaSettings

    settings = QattaSettings(_env_file=None)
    ok, reasons = check_duration(_Candidate(), settings)  # type: ignore[arg-type]

    assert ok is False
    assert reasons, "a refusal must explain itself"


def test_the_duration_gate_accepts_a_normal_clip() -> None:
    class _Candidate:
        clip_id = "cand_1"
        duration_sec = 40.0

    from qatta.core.config import QattaSettings

    settings = QattaSettings(_env_file=None)
    ok, reasons = check_duration(_Candidate(), settings)  # type: ignore[arg-type]

    assert ok is True
    assert not reasons
