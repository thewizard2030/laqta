"""One ordered pipeline, one registration point.

The stage list used to live inside the FastAPI job manager, which meant the
framework-free `qatta` package had no runnable pipeline of its own: the only
way to run a project end to end was over HTTP. Any second entry point (the
`laqta run` CLI) would have had to copy the order, and the two copies would
have drifted the first time a stage was added.

This module is that single source of truth. It owns:

- :data:`PIPELINE_STAGES` — the order, and the label each stage reports.
- :func:`register_default_stages` — attaching the real stages to an
  orchestrator.
- :func:`run_pipeline` — running them with cancellation, callbacks and
  measured timings.

It deliberately does **not** own progress percentages, database sync or
thumbnails: those are presentation and persistence concerns that belong to
the caller.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from qatta.core.pipeline import PipelineError, PipelineOrchestrator

__all__ = [
    "PIPELINE_STAGES",
    "PipelineCancelledError",
    "PipelineStage",
    "StageResult",
    "register_default_stages",
    "run_pipeline",
    "stage_names",
]


@dataclass(frozen=True)
class PipelineStage:
    """One stage in the pipeline.

    ``name`` is what the orchestrator registers and the manifest records;
    ``label`` is the short human-readable state a UI can show while the stage
    runs. The label is not a progress percentage — the runner reports real
    elapsed time instead of inventing one.
    """

    name: str
    label: str


#: The pipeline, in order. This is the only place the order is written down.
PIPELINE_STAGES: tuple[PipelineStage, ...] = (
    PipelineStage("s01_ingest", "ingesting_media"),
    PipelineStage("s02_transcript", "transcribing_audio"),
    PipelineStage("s03_multimodal", "analyzing_multimodal"),
    PipelineStage("s04_candidates", "generating_candidates"),
    PipelineStage("s05_ranking", "ranking_candidates"),
    PipelineStage("s05b_section_fetch", "fetching_clip_sections"),
    PipelineStage("s02b_fine_alignment", "aligning_clip_words"),
    PipelineStage("s06_render", "rendering_shorts"),
)


class PipelineCancelledError(PipelineError):
    """Raised at a stage boundary when the caller asked to stop.

    Cancellation is checked *between* stages, so a stage that is already
    running finishes first. That limitation is deliberate and documented: the
    alternative is killing a subprocess mid-write and leaving a truncated
    artefact behind.
    """

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class StageResult:
    """What actually happened to one stage in one run."""

    name: str
    label: str
    executed: bool
    skipped_cached: bool
    duration_ms: int

    @property
    def status(self) -> str:
        """A single word for logs and JSON events."""
        if self.skipped_cached:
            return "skipped"
        return "executed" if self.executed else "unknown"


def stage_names() -> tuple[str, ...]:
    """The pipeline order as plain names."""
    return tuple(stage.name for stage in PIPELINE_STAGES)


def register_default_stages(
    orchestrator: PipelineOrchestrator,
) -> PipelineOrchestrator:
    """Attach every real stage to ``orchestrator`` and return it.

    Imports are local so that importing this module stays cheap: the stage
    modules pull in heavy optional dependencies lazily themselves, and the CLI
    should be able to describe the pipeline without loading them.
    """
    from qatta.stages.s01_ingest import ingestor
    from qatta.stages.s02_transcript import fast_pass, fine_pass
    from qatta.stages.s03_multimodal import analyzer
    from qatta.stages.s04_candidates import generator
    from qatta.stages.s05_ranking import scorer
    from qatta.stages.s05b_section_fetch import section_fetch
    from qatta.stages.s06_render import renderer

    for module in (
        ingestor,
        fast_pass,
        fine_pass,
        analyzer,
        generator,
        scorer,
        section_fetch,
        renderer,
    ):
        module.register(orchestrator)
    return orchestrator


def _select_stages(
    requested: Iterable[str] | None,
    orchestrator: PipelineOrchestrator,
) -> tuple[PipelineStage, ...]:
    """Resolve the stages to run, failing *before* any work starts.

    The orchestrator raises on an unregistered stage, but only when it reaches
    that stage — by which point the earlier ones have already run and written
    artefacts. Validating the whole selection up front turns a half-finished
    project into a clean refusal.
    """
    by_name = {stage.name: stage for stage in PIPELINE_STAGES}
    if requested is None:
        selected = PIPELINE_STAGES
    else:
        names = list(requested)
        unknown = [name for name in names if name not in by_name]
        if unknown:
            raise PipelineError(
                f"Unknown pipeline stage(s): {', '.join(unknown)}. "
                f"Known stages: {', '.join(stage_names())}."
            )
        if not names:
            raise PipelineError("No stages were selected; nothing would run.")
        # Preserve pipeline order regardless of the order the caller used, so
        # a subset can never run out of order.
        selected = tuple(by_name[name] for name in stage_names() if name in set(names))

    registered = set(orchestrator.registered_stages)
    missing = [stage.name for stage in selected if stage.name not in registered]
    if missing:
        raise PipelineError(
            f"Stage(s) not registered on this orchestrator: {', '.join(missing)}. "
            "Call register_default_stages(orchestrator) first."
        )
    return selected


def run_pipeline(
    orchestrator: PipelineOrchestrator,
    *,
    stages: Sequence[str] | None = None,
    force: bool = False,
    on_stage_start: Callable[[PipelineStage], None] | None = None,
    on_stage_end: Callable[[PipelineStage, StageResult], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[StageResult]:
    """Run the pipeline (or a subset) and return what happened, stage by stage.

    Args:
        orchestrator: An orchestrator with its stages registered.
        stages: Optional subset of stage names. Order is always the pipeline
            order, never the caller's order.
        force: Re-run stages already recorded in ``completed_stages``.
        on_stage_start: Called before each stage runs.
        on_stage_end: Called after each stage with its measured result.
        should_cancel: Polled *between* stages. When it returns True the run
            stops with :class:`PipelineCancelledError`; the stage that is already
            running is allowed to finish.

    Returns:
        One :class:`StageResult` per stage that was attempted.
    """
    selected = _select_stages(stages, orchestrator)
    results: list[StageResult] = []

    for stage in selected:
        if should_cancel is not None and should_cancel():
            raise PipelineCancelledError(
                f"Cancelled before stage '{stage.name}'; "
                f"{len(results)} of {len(selected)} stage(s) completed.",
                stage=stage.name,
            )
        if on_stage_start is not None:
            on_stage_start(stage)

        started = time.monotonic()
        report = orchestrator.run_stage(stage.name, force=force)
        duration_ms = int((time.monotonic() - started) * 1000)

        result = StageResult(
            name=stage.name,
            label=stage.label,
            executed=bool(report.get("executed", False)),
            skipped_cached=bool(report.get("skipped_cached", False)),
            duration_ms=duration_ms,
        )
        results.append(result)
        if on_stage_end is not None:
            on_stage_end(stage, result)

    return results
