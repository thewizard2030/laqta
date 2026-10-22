"""Tests for the three scoring gates.

The gates run *before* any score is computed: a candidate that fails one is
vetoed and never ranked. They are what makes "explainable" more than a
label — every outcome is recorded in the candidate's evidence log, including
the reason for a rejection.
"""

from __future__ import annotations

import pytest

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import (
    AtomicUtterance,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)
from qatta.stages.s05_ranking.scorer import (
    GateContext,
    _find_utterance,
    heal_dangling_context,
    is_dangling,
)


def _utterance(u_id: str, text: str, start_ms: int, end_ms: int) -> AtomicUtterance:
    return AtomicUtterance(
        u_id=u_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        audio_rms_norm=0.5,
    )


def _manifest(utterances: list[AtomicUtterance]) -> QattaManifest:
    return QattaManifest(
        project_id="proj_gates",
        source_path="/tmp/source.mp4",
        duration_sec=60.0,
        atomic_utterances=utterances,
    )


def _candidate(
    clip_id: str = "cand_1",
    start_u_id: str = "U_0002",
    end_u_id: str = "U_0003",
    start_ms: int = 10000,
    end_ms: int = 40000,
) -> ClipCandidate:
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id=start_u_id,
        end_u_id=end_u_id,
        start_ms=start_ms,
        end_ms=end_ms,
        duration_sec=(end_ms - start_ms) / 1000.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=0.0,
            archetype="STORY",
            standalone_clarity=0.0,
            hook_strength=0.0,
            story_payoff=0.0,
            value_originality=0.0,
            audio_dynamics=0.0,
            boundary_precision=0.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
    )


# ---------------------------------------------------------------------------
# The dangling-context detector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "عشان كده نقدر نعمل كذا",
        "عشان كدا الموضوع بقى اوضح",
        "النقطة التانية إننا بنشرح ده",
        "زي ما قلتلك بالظبط",
        "و ده سبب المشكلة",
    ],
)
def test_a_clip_starting_with_a_connector_is_dangling(text: str) -> None:
    assert is_dangling(_utterance("U_0001", text, 0, 1000)) is True


@pytest.mark.parametrize(
    "text",
    [
        "النقطة الأولى إننا بنشرح الموضوع",
        "ده اللي حصل في تجربة الأمس",
        "مقدمة بسيطة عن الموضوع",
    ],
)
def test_a_clip_starting_cleanly_is_not_dangling(text: str) -> None:
    assert is_dangling(_utterance("U_0001", text, 0, 1000)) is False


def test_the_dangling_check_ignores_leading_whitespace_and_case() -> None:
    assert is_dangling(_utterance("U_0001", "  عشان كده نكمل", 0, 1000)) is True


# ---------------------------------------------------------------------------
# The healer
# ---------------------------------------------------------------------------


def test_the_healer_shifts_the_start_back_across_a_dangling_utterance() -> None:
    manifest = _manifest(
        [
            _utterance("U_0001", "مقدمة عن الموضوع", 0, 5000),
            _utterance("U_0002", "عشان كده نكمل الشرح", 5000, 10000),
            _utterance("U_0003", "الخلاصة المهمة", 10000, 20000),
        ]
    )
    settings = QattaSettings(_env_file=None)
    gate_ctx = GateContext(manifest, settings)
    proposal = _candidate(start_u_id="U_0002", end_u_id="U_0003", start_ms=5000, end_ms=20000)

    healed, evidence, still_dangling = heal_dangling_context(manifest, proposal, gate_ctx, settings)

    assert healed.start_u_id == "U_0001"
    assert healed.start_ms == 0
    assert evidence, "a heal must be recorded in the evidence log"
    assert still_dangling is False


def test_the_healer_leaves_a_clean_candidate_alone() -> None:
    manifest = _manifest(
        [
            _utterance("U_0001", "مقدمة عن الموضوع", 0, 5000),
            _utterance("U_0002", "النقطة الرئيسية", 5000, 10000),
            _utterance("U_0003", "الخلاصة", 10000, 15000),
        ]
    )
    settings = QattaSettings(_env_file=None)
    gate_ctx = GateContext(manifest, settings)
    proposal = _candidate(start_u_id="U_0002", end_u_id="U_0003", start_ms=5000, end_ms=15000)

    healed, _, still_dangling = heal_dangling_context(manifest, proposal, gate_ctx, settings)

    assert healed.start_u_id == "U_0002"
    assert still_dangling is False


def test_a_candidate_without_context_is_resolved_by_a_remix_flag() -> None:
    """A dangling start with no earlier context is flagged, not silently kept.

    The gate cannot heal it, so it raises a HookRemix: the hook moves inside
    the clip, the gate reads as resolved, and the evidence line says exactly
    what happened.
    """
    manifest = _manifest(
        [
            _utterance("U_0001", "عشان كده نكمل", 0, 5000),
            _utterance("U_0002", "الشرح", 5000, 10000),
        ]
    )
    settings = QattaSettings(_env_file=None)
    gate_ctx = GateContext(manifest, settings)
    proposal = _candidate(start_u_id="U_0001", end_u_id="U_0002", start_ms=0, end_ms=10000)

    healed, evidence, still_dangling = heal_dangling_context(manifest, proposal, gate_ctx, settings)

    assert still_dangling is False
    assert healed.hook_remix.enabled is True
    assert healed.hook_remix.hook_u_id is not None
    assert healed.hook_remix.context_preserved is False
    assert evidence, "the remix must be recorded in the evidence log"
    assert "HookRemix" in evidence[0]


# ---------------------------------------------------------------------------
# The index helpers
# ---------------------------------------------------------------------------


def test_finding_an_unknown_utterance_is_an_error() -> None:
    manifest = _manifest([_utterance("U_0001", "نص", 0, 1000)])
    settings = QattaSettings(_env_file=None)
    gate_ctx = GateContext(manifest, settings)

    with pytest.raises(PipelineError) as excinfo:
        _find_utterance(gate_ctx.by_u_id, "U_9999")

    assert "U_9999" in str(excinfo.value)


def test_the_gate_context_indexes_by_id_and_ordinal() -> None:
    manifest = _manifest(
        [
            _utterance("U_0002", "ثاني", 5000, 10000),
            _utterance("U_0001", "أول", 0, 5000),
        ]
    )
    settings = QattaSettings(_env_file=None)
    gate_ctx = GateContext(manifest, settings)

    # The context sorts by start time, not by the manifest order.
    assert gate_ctx.ordered[0].u_id == "U_0001"
    assert gate_ctx.ordinal["U_0001"] == 0
    assert gate_ctx.utterance_at(0).u_id == "U_0001"
    assert gate_ctx.utterance_at(99) is None
