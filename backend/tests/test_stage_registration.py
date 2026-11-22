"""The backend must not own a second stage list.

`qatta/core/runner.py` is the single source of truth for the pipeline. These
tests exercise the backend's real construction path and assert that it
registers exactly that pipeline — nothing missing, nothing extra. They are the
guard against silently wiring a future stage (`s07_render_learn`) or a stage
whose inputs do not exist yet (`s06_reframe_subs`).
"""

from __future__ import annotations

from app.core.config import settings
from app.jobs.manager import JobManager
from qatta.core.runner import stage_names
from qatta.core.schema import QattaManifest


def _orchestrator(project_id: str):
    """Build the backend orchestrator without touching a real media file."""
    project_dir = settings.get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest = QattaManifest(
        project_id=project_id,
        source_path=str(project_dir / "source.mp4"),
        duration_sec=1.0,
    )
    (project_dir / "qatta_manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return JobManager()._get_or_create_orchestrator(project_id)


def test_the_backend_registers_exactly_the_runner_pipeline() -> None:
    orchestrator = _orchestrator("registration-exact")

    assert set(orchestrator.registered_stages) == set(stage_names())


def test_the_backend_registers_only_s06_render_among_render_stages() -> None:
    orchestrator = _orchestrator("registration-render")

    render_family = {
        name for name in orchestrator.registered_stages if name.startswith(("s06", "s07"))
    }

    assert render_family == {"s06_render"}
    assert "s07_render_learn" not in orchestrator.registered_stages
    assert "s06_reframe_subs" not in orchestrator.registered_stages


def test_every_registered_stage_has_a_progress_percentage() -> None:
    """A stage without a percentage would show 0 while it does real work."""
    assert set(JobManager._PROGRESS_BY_STAGE) == set(stage_names())
