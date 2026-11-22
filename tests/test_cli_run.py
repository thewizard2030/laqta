"""Tests for `laqta run` — the headless entry point to the same pipeline.

Every test uses fake stage functions: the point is the CLI contract (events,
exit codes, upfront refusal), not media processing. The pipeline itself is
covered by tests/test_runner.py.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from qatta.cli import app
from qatta.core.pipeline import PipelineError
from qatta.core.runner import PipelineCancelledError, stage_names
from qatta.core.schema import QattaManifest

runner = CliRunner()


def make_project(tmp_path, completed: tuple[str, ...] = ()):
    """A source file plus a matching manifest, so no ffprobe is needed."""
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not real media")
    work = tmp_path / "work"
    work.mkdir()
    manifest = QattaManifest(
        project_id="proj",
        source_path=str(source.resolve()),
        duration_sec=1.0,
        completed_stages=list(completed),
    )
    (work / "qatta_manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return source, work


@pytest.fixture()
def fake_stages(monkeypatch):
    """Replace real stage registration with recording no-ops."""
    log: list[str] = []

    def register(orchestrator):
        for name in stage_names():

            def run(manifest: QattaManifest, _name: str = name) -> QattaManifest:
                log.append(_name)
                return manifest

            orchestrator.stage(name, run)
        return orchestrator

    monkeypatch.setattr("qatta.core.runner.register_default_stages", register)
    return log


def events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def invoke(source, work, *extra: str):
    return runner.invoke(
        app,
        [
            "run",
            str(source),
            "--project-id",
            "proj",
            "--work-dir",
            str(work),
            *extra,
        ],
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_json_run_emits_ordered_ndjson_with_real_timings(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path)

    result = invoke(source, work, "--json")

    assert result.exit_code == 0, result.stdout
    parsed = events(result.stdout)
    assert parsed[0]["event"] == "run_start"
    assert parsed[-1]["event"] == "run_end"

    starts = [event for event in parsed if event["event"] == "stage_start"]
    ends = [event for event in parsed if event["event"] == "stage_end"]
    assert [event["stage"] for event in starts] == list(stage_names())
    assert [event["stage"] for event in ends] == list(stage_names())
    assert [event["index"] for event in starts] == list(range(1, 9))
    assert all(event["total"] == 8 for event in starts)

    for event in ends:
        assert event["status"] == "executed"
        assert isinstance(event["duration_ms"], int)
        assert event["duration_ms"] >= 0
        assert isinstance(event["stage_timings_ms"], int)
        assert event["stage_timings_ms"] >= event["duration_ms"]

    assert parsed[-1]["executed"] == 8
    assert parsed[-1]["skipped"] == 0
    assert fake_stages == list(stage_names())


def test_a_stage_subset_keeps_pipeline_order(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path)

    result = invoke(source, work, "--json", "--stages", "s06_render,s01_ingest")

    assert result.exit_code == 0, result.stdout
    assert fake_stages == ["s01_ingest", "s06_render"]
    starts = [event for event in events(result.stdout) if event["event"] == "stage_start"]
    assert [event["stage"] for event in starts] == ["s01_ingest", "s06_render"]
    assert all(event["total"] == 2 for event in starts)


def test_a_cached_stage_is_reported_as_skipped(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path, completed=("s01_ingest",))

    result = invoke(source, work, "--json", "--stages", "s01_ingest")

    assert result.exit_code == 0, result.stdout
    assert fake_stages == []
    end = next(event for event in events(result.stdout) if event["event"] == "stage_end")
    assert end["status"] == "skipped"


def test_force_reruns_a_cached_stage(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path, completed=("s01_ingest",))

    result = invoke(source, work, "--json", "--stages", "s01_ingest", "--force")

    assert result.exit_code == 0, result.stdout
    assert fake_stages == ["s01_ingest"]
    end = next(event for event in events(result.stdout) if event["event"] == "stage_end")
    assert end["status"] == "executed"


def test_human_output_summarises_the_run(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path)

    result = invoke(source, work)

    assert result.exit_code == 0, result.stdout
    assert "Done." in result.stdout
    assert "executed" in result.stdout
    assert "Manifest:" in result.stdout


# ---------------------------------------------------------------------------
# Refusals — before any work starts
# ---------------------------------------------------------------------------


def test_a_missing_source_is_refused(tmp_path, fake_stages) -> None:
    _, work = make_project(tmp_path)
    missing = tmp_path / "absent.mp4"

    result = invoke(missing, work, "--json")

    assert result.exit_code == 1
    error = next(event for event in events(result.stdout) if event["event"] == "error")
    assert "does not exist" in error["message"]
    assert fake_stages == []


def test_a_url_is_refused_with_a_pointer_to_the_policy(tmp_path, fake_stages) -> None:
    _, work = make_project(tmp_path)

    result = runner.invoke(
        app,
        ["run", "https://example.com/v.mp4", "--project-id", "proj", "--work-dir", str(work)],
    )

    assert result.exit_code == 1
    assert "local file" in result.stdout
    assert fake_stages == []


def test_an_unknown_stage_is_refused(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path)

    result = invoke(source, work, "--json", "--stages", "s01_ingest,s99_nope")

    assert result.exit_code == 1
    parsed = events(result.stdout)
    assert not any(event["event"] == "stage_start" for event in parsed)
    error = next(event for event in parsed if event["event"] == "error")
    assert "s99_nope" in error["message"]
    assert fake_stages == []


def test_an_empty_stage_selection_is_refused(tmp_path, fake_stages) -> None:
    source, work = make_project(tmp_path)

    result = invoke(source, work, "--json", "--stages", " , ")

    assert result.exit_code == 1
    assert fake_stages == []


def test_reusing_a_project_id_for_another_source_is_refused(tmp_path, fake_stages) -> None:
    _, work = make_project(tmp_path)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"different media")

    result = invoke(other, work, "--json")

    assert result.exit_code == 1
    error = next(event for event in events(result.stdout) if event["event"] == "error")
    assert "already tracks" in error["message"]
    assert fake_stages == []


# ---------------------------------------------------------------------------
# Failure and interruption
# ---------------------------------------------------------------------------


def test_a_stage_failure_exits_one_and_reports_it(tmp_path, monkeypatch) -> None:
    source, work = make_project(tmp_path)

    def register(orchestrator):
        def boom(manifest: QattaManifest) -> QattaManifest:
            raise PipelineError("simulated stage failure")

        orchestrator.stage("s01_ingest", boom)

    monkeypatch.setattr("qatta.core.runner.register_default_stages", register)

    result = invoke(source, work, "--json", "--stages", "s01_ingest")

    assert result.exit_code == 1
    error = next(event for event in events(result.stdout) if event["event"] == "error")
    assert "simulated stage failure" in error["message"]


def test_a_cancelled_run_exits_130(tmp_path, fake_stages, monkeypatch) -> None:
    source, work = make_project(tmp_path)

    def cancelled(*_args, **_kwargs):
        raise PipelineCancelledError(
            "Cancelled before stage 's02_transcript'.", stage="s02_transcript"
        )

    monkeypatch.setattr("qatta.core.runner.run_pipeline", cancelled)

    result = invoke(source, work, "--json")

    assert result.exit_code == 130
    event = next(event for event in events(result.stdout) if event["event"] == "cancelled")
    assert event["stage"] == "s02_transcript"


def test_an_immediate_interrupt_exits_130(tmp_path, fake_stages, monkeypatch) -> None:
    source, work = make_project(tmp_path)

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("qatta.core.runner.run_pipeline", interrupted)

    result = invoke(source, work, "--json")

    assert result.exit_code == 130
    event = next(event for event in events(result.stdout) if event["event"] == "cancelled")
    assert "last completed stage" in event["message"]
