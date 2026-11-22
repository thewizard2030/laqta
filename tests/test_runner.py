"""The pipeline runner is the single source of truth for stage order.

These tests use a real :class:`PipelineOrchestrator` with fake stage functions
registered under the real stage names. The point is to prove the runner's
contract — order, caching, cancellation, upfront validation — without running
any media processing.
"""

from __future__ import annotations

import pytest

from qatta.core.pipeline import PipelineError, PipelineOrchestrator
from qatta.core.runner import (
    PIPELINE_STAGES,
    PipelineCancelledError,
    register_default_stages,
    run_pipeline,
    stage_names,
)
from qatta.core.schema import QattaManifest


def make_orchestrator(tmp_path, completed: tuple[str, ...] = ()) -> PipelineOrchestrator:
    """An orchestrator backed by a hand-written manifest (no ffprobe needed)."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    manifest = QattaManifest(
        project_id="proj",
        source_path=str(tmp_path / "source.mp4"),
        duration_sec=1.0,
        completed_stages=list(completed),
    )
    (work_dir / "qatta_manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return PipelineOrchestrator(project_id="proj", work_dir=work_dir)


def register_fakes(orchestrator, log: list[str], names=None) -> None:
    """Register a recording no-op stage under each pipeline stage name."""
    for name in names if names is not None else stage_names():

        def run(manifest: QattaManifest, _name: str = name) -> QattaManifest:
            log.append(_name)
            return manifest

        orchestrator.stage(name, run)


# ---------------------------------------------------------------------------
# The order itself
# ---------------------------------------------------------------------------


def test_the_stage_order_is_the_expected_one() -> None:
    assert stage_names() == (
        "s01_ingest",
        "s02_transcript",
        "s03_multimodal",
        "s04_candidates",
        "s05_ranking",
        "s05b_section_fetch",
        "s02b_fine_alignment",
        "s06_render",
    )


def test_every_stage_has_a_distinct_name_and_label() -> None:
    names = [stage.name for stage in PIPELINE_STAGES]
    labels = [stage.label for stage in PIPELINE_STAGES]
    assert len(names) == len(set(names))
    assert len(labels) == len(set(labels))
    assert all(label.strip() for label in labels)


def test_register_default_stages_registers_exactly_the_pipeline(tmp_path) -> None:
    """The backend and the CLI both go through this, so it must be complete."""
    orchestrator = make_orchestrator(tmp_path)

    register_default_stages(orchestrator)

    assert set(orchestrator.registered_stages) == set(stage_names())


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_the_pipeline_runs_every_stage_in_order(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    results = run_pipeline(orchestrator)

    assert log == list(stage_names())
    assert [result.name for result in results] == list(stage_names())
    assert all(result.executed for result in results)
    assert all(not result.skipped_cached for result in results)
    assert all(result.status == "executed" for result in results)
    assert orchestrator.manifest.completed_stages == list(stage_names())


def test_a_completed_stage_is_skipped_without_force(tmp_path) -> None:
    completed = ("s01_ingest", "s02_transcript")
    orchestrator = make_orchestrator(tmp_path, completed=completed)
    log: list[str] = []
    register_fakes(orchestrator, log)

    results = run_pipeline(orchestrator)

    assert log == list(stage_names()[2:])
    by_name = {result.name: result for result in results}
    for name in completed:
        assert by_name[name].skipped_cached is True
        assert by_name[name].executed is False
        assert by_name[name].status == "skipped"
    assert by_name["s03_multimodal"].status == "executed"


def test_force_reruns_a_completed_stage(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path, completed=("s01_ingest",))
    log: list[str] = []
    register_fakes(orchestrator, log)

    results = run_pipeline(orchestrator, stages=["s01_ingest"], force=True)

    assert log == ["s01_ingest"]
    assert results[0].executed is True
    assert results[0].skipped_cached is False


def test_the_runner_reports_measured_time_per_stage(tmp_path) -> None:
    """Durations are measured, not estimated — and land in the manifest."""
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    results = run_pipeline(orchestrator, stages=["s01_ingest"])

    assert results[0].duration_ms >= 0
    assert "s01_ingest" in orchestrator.manifest.stage_timings_ms


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_a_subset_keeps_pipeline_order_not_caller_order(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    run_pipeline(orchestrator, stages=["s06_render", "s01_ingest"])

    assert log == ["s01_ingest", "s06_render"]


def test_an_unknown_stage_is_refused_before_any_stage_runs(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    with pytest.raises(PipelineError) as caught:
        run_pipeline(orchestrator, stages=["s01_ingest", "s99_nope"])

    assert "s99_nope" in str(caught.value)
    assert log == []
    assert orchestrator.manifest.completed_stages == []


def test_an_unregistered_stage_is_refused_before_any_stage_runs(tmp_path) -> None:
    """Failing up front prevents a half-finished project."""
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log, names=["s01_ingest"])

    with pytest.raises(PipelineError) as caught:
        run_pipeline(orchestrator)

    assert "s02_transcript" in str(caught.value)
    assert "register_default_stages" in str(caught.value)
    assert log == []


def test_an_empty_selection_is_refused(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    register_fakes(orchestrator, [])

    with pytest.raises(PipelineError):
        run_pipeline(orchestrator, stages=[])


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancellation_stops_at_a_stage_boundary(tmp_path) -> None:
    """The stage that is running finishes; the next one never starts."""
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    def cancel_after_two() -> bool:
        return len(log) >= 2

    with pytest.raises(PipelineCancelledError) as caught:
        run_pipeline(orchestrator, should_cancel=cancel_after_two)

    assert log == ["s01_ingest", "s02_transcript"]
    assert caught.value.stage == "s03_multimodal"
    assert "2 of 8" in str(caught.value)
    assert orchestrator.manifest.completed_stages == ["s01_ingest", "s02_transcript"]


def test_a_stage_that_sets_the_cancel_flag_still_completes(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    cancelled = {"value": False}

    def first(manifest: QattaManifest) -> QattaManifest:
        log.append("s01_ingest")
        cancelled["value"] = True
        return manifest

    orchestrator.stage("s01_ingest", first)
    register_fakes(orchestrator, log, names=stage_names()[1:])

    with pytest.raises(PipelineCancelledError):
        run_pipeline(orchestrator, should_cancel=lambda: cancelled["value"])

    # The in-flight stage is recorded; nothing after it ran.
    assert log == ["s01_ingest"]
    assert orchestrator.manifest.completed_stages == ["s01_ingest"]


def test_cancellation_before_the_first_stage_runs_nothing(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    log: list[str] = []
    register_fakes(orchestrator, log)

    with pytest.raises(PipelineCancelledError) as caught:
        run_pipeline(orchestrator, should_cancel=lambda: True)

    assert log == []
    assert caught.value.stage == "s01_ingest"
    assert orchestrator.manifest.completed_stages == []


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def test_callbacks_fire_once_per_attempted_stage_in_order(tmp_path) -> None:
    orchestrator = make_orchestrator(tmp_path, completed=("s01_ingest",))
    log: list[str] = []
    register_fakes(orchestrator, log)
    started: list[str] = []
    ended: list[tuple[str, str]] = []

    run_pipeline(
        orchestrator,
        stages=["s01_ingest", "s02_transcript"],
        on_stage_start=lambda stage: started.append(stage.name),
        on_stage_end=lambda stage, result: ended.append((stage.name, result.status)),
    )

    # A cached stage still reports start and end — the caller needs to know
    # it was considered, not silently dropped.
    assert started == ["s01_ingest", "s02_transcript"]
    assert ended == [("s01_ingest", "skipped"), ("s02_transcript", "executed")]
