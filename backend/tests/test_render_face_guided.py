"""Face-guided framing in the backend render job (Phase 5 wiring).

The detector and the renderer are tested where they live; these tests cover the
glue that only exists in the backend: reading the solved trajectory from the
manifest, rebasing it onto the *record's* clip bounds, and recording the
outcome in the render config so a centred fallback is never mistaken for a pan.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.jobs import job_manager
from app.schemas.rendering import LayoutMode
from app.services.rendering.render import (
    SUPPORTED_LAYOUTS,
    build_render_command,
    probe_render_environment,
)
from qatta.core.schema import (
    ClipCandidate,
    CPSBreakdown,
    CropKeyframe,
    HookRemixVariant,
    QattaManifest,
    ShotFraming,
    VetoGates,
)
from tests.test_render import (
    FFMPEG_BIN,
    _await_terminal,
    _create_project_media_transcript_candidate,
    _environment_ready,
    _post_render,
)


def _candidate(clip_id: str, trajectory: list[ShotFraming] | None) -> ClipCandidate:
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=1000,
        end_ms=3000,
        duration_sec=2.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=80.0,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=18.0,
            hook_strength=18.0,
            story_payoff=16.0,
            value_originality=14.0,
            audio_dynamics=8.0,
            boundary_precision=6.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
        crop_trajectory=trajectory or [],
    )


def _trajectory() -> list[ShotFraming]:
    return [
        ShotFraming(
            shot_index=0,
            start_ms=1000,
            end_ms=3000,
            layout="SINGLE_SPEAKER",
            keyframes=[
                CropKeyframe(timestamp_ms=1000, center_x=0.2),
                CropKeyframe(timestamp_ms=2000, center_x=0.5),
                CropKeyframe(timestamp_ms=3000, center_x=0.8),
            ],
        )
    ]


def _write_manifest(project_id: str, candidate: ClipCandidate) -> Path:
    project_dir = settings.get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest = QattaManifest(
        project_id=project_id,
        source_path="/tmp/source.mp4",
        duration_sec=10.0,
        candidates=[candidate],
    )
    manifest_path = project_dir / "qatta_manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest_path


def _new_project_id() -> str:
    return f"proj_face_{uuid.uuid4().hex[:10]}"


def test_face_guided_is_a_real_supported_layout() -> None:
    assert LayoutMode.FACE_GUIDED.value == "face_guided"
    assert "face_guided" in SUPPORTED_LAYOUTS


def test_face_guided_command_pans_with_the_supplied_trajectory(tmp_path: Path) -> None:
    argv = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="face_guided",
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=True,
        caption_format="none",
        start_ms=1000,
        duration_ms=2000,
        crop_trajectory=[(0, 0.2), (1000, 0.5), (2000, 0.8)],
    )

    filtergraph = argv[argv.index("-vf") + 1]
    assert "crop=w=606:h=1080" in filtergraph
    assert "x=" in filtergraph


def test_the_manifest_trajectory_is_rebased_onto_the_record_bounds() -> None:
    project_id = _new_project_id()
    _write_manifest(project_id, _candidate("clip_face", _trajectory()))

    points, reason = job_manager._resolve_crop_trajectory(
        project_id=project_id,
        clip_id="clip_face",
        layout="face_guided",
        clip_start_ms=1000,
        clip_end_ms=3000,
    )

    assert reason is None
    assert points == [(0, 0.2), (1000, 0.5), (2000, 0.8)]


def test_a_trimmed_clip_rebases_against_the_record_not_the_manifest() -> None:
    # The user trimmed the candidate to 1500..2500 after the pipeline ran; the
    # pan must line up with the -ss/-t the renderer actually uses.
    project_id = _new_project_id()
    _write_manifest(project_id, _candidate("clip_face", _trajectory()))

    points, reason = job_manager._resolve_crop_trajectory(
        project_id=project_id,
        clip_id="clip_face",
        layout="face_guided",
        clip_start_ms=1500,
        clip_end_ms=2500,
    )

    assert reason is None
    # The 1000 ms keyframe is before the new start, so it clamps to t=0; the
    # camera is where it stood at source 1000 when the trimmed clip opens.
    assert points == [(0, 0.2), (500, 0.5), (1000, 0.8)]


def test_a_non_face_guided_render_never_reads_a_trajectory() -> None:
    points, reason = job_manager._resolve_crop_trajectory(
        project_id=_new_project_id(),
        clip_id="clip_face",
        layout="center_crop",
        clip_start_ms=0,
        clip_end_ms=1000,
    )

    assert points == []
    assert reason is None


@pytest.mark.parametrize(
    ("setup", "expected_reason"),
    [
        ("no_manifest", "no_manifest"),
        ("missing_candidate", "candidate_missing_from_manifest"),
        ("no_trajectory", "no_trajectory"),
    ],
)
def test_an_explicit_request_with_nothing_to_follow_records_why(
    setup: str, expected_reason: str
) -> None:
    project_id = _new_project_id()
    if setup == "missing_candidate":
        _write_manifest(project_id, _candidate("clip_other", _trajectory()))
    elif setup == "no_trajectory":
        _write_manifest(project_id, _candidate("clip_face", None))

    points, reason = job_manager._resolve_crop_trajectory(
        project_id=project_id,
        clip_id="clip_face",
        layout="face_guided",
        clip_start_ms=0,
        clip_end_ms=1000,
    )

    assert points == []
    assert reason == expected_reason


def test_a_render_with_a_solved_trajectory_records_the_pan(client: TestClient, tmp_path: Path):
    if not _environment_ready(probe_render_environment()):
        pytest.skip("ffmpeg with libass, a software H.264 encoder and AAC is unavailable")

    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    # The fixture clip is 100..1900 ms in source time.
    _write_manifest(
        project.id,
        _candidate(
            candidate.id,
            [
                ShotFraming(
                    shot_index=0,
                    start_ms=0,
                    end_ms=2000,
                    layout="SINGLE_SPEAKER",
                    keyframes=[
                        CropKeyframe(timestamp_ms=100, center_x=0.3),
                        CropKeyframe(timestamp_ms=1900, center_x=0.7),
                    ],
                )
            ],
        ),
    )

    job_id = _post_render(client, candidate.id, layout="face_guided", overwrite=True)
    job = _await_terminal(client, job_id)
    assert job["status"] == "succeeded", job

    cfg = json.loads(job["config_json"])
    assert cfg["render"]["layout"] == "face_guided"
    assert cfg["render"]["trajectory_points"] == 2
    assert cfg["render"]["framing_fallback"] is None


def test_a_render_without_a_manifest_falls_back_and_says_so(client: TestClient, tmp_path: Path):
    if not _environment_ready(probe_render_environment()):
        pytest.skip("ffmpeg with libass, a software H.264 encoder and AAC is unavailable")

    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    # No qatta_manifest.json is written for this project.

    job_id = _post_render(client, candidate.id, layout="face_guided", overwrite=True)
    job = _await_terminal(client, job_id)
    assert job["status"] == "succeeded", job

    cfg = json.loads(job["config_json"])
    assert cfg["render"]["layout"] == "face_guided"
    assert cfg["render"]["trajectory_points"] == 0
    assert cfg["render"]["framing_fallback"] == "no_manifest"


# ---------------------------------------------------------------------------
# Pipeline opt-in: the trajectory has to be solved before a render can use it.
# ---------------------------------------------------------------------------


def _job_record(**overrides):
    from types import SimpleNamespace

    fields = {
        "id": "job_test",
        "project_id": "proj_test",
        "media_id": None,
        "type": "pipeline",
        "status": "queued",
        "stage": "queued",
        "progress": 0.0,
        "config_json": None,
        "error_code": None,
        "error_message": None,
        "created_at": "2026-01-01T00:00:00Z",
        "started_at": None,
        "finished_at": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_the_pipeline_endpoint_forwards_the_opt_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.repository import ProjectRepository

    project = ProjectRepository().create_project(f"pipeline-opt-in-{uuid.uuid4().hex[:8]}")
    captured: dict = {}

    async def fake_submit_job(*, project_id, job_type, media_id=None, config=None):
        captured.update(project_id=project_id, job_type=job_type, config=config)
        return _job_record(project_id=project_id)

    monkeypatch.setattr(job_manager, "submit_job", fake_submit_job)

    resp = client.post(
        f"/api/projects/{project.id}/pipeline-jobs",
        json={"face_guided_framing": True},
    )

    assert resp.status_code == 201, resp.text
    assert captured["config"] == {"face_guided_framing": True}


def test_the_pipeline_endpoint_defaults_to_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.repository import ProjectRepository

    project = ProjectRepository().create_project(f"pipeline-default-{uuid.uuid4().hex[:8]}")
    captured: dict = {}

    async def fake_submit_job(*, project_id, job_type, media_id=None, config=None):
        captured.update(project_id=project_id, job_type=job_type, config=config)
        return _job_record(project_id=project_id)

    monkeypatch.setattr(job_manager, "submit_job", fake_submit_job)

    resp = client.post(f"/api/projects/{project.id}/pipeline-jobs")

    assert resp.status_code == 201, resp.text
    assert captured["config"] is None


def test_the_pipeline_job_threads_the_opt_in_into_core_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    captured: dict = {}

    def fake_orchestrator(project_id, media_id=None, *, settings_override=None):
        captured["settings"] = settings_override
        raise RuntimeError("stop before any stage runs")

    monkeypatch.setattr(job_manager, "_get_or_create_orchestrator", fake_orchestrator)

    job = _job_record(config_json=json.dumps({"face_guided_framing": True}))
    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(job_manager._execute_pipeline(job, asyncio.Event()))

    assert captured["settings"] is not None
    assert captured["settings"].face_guided_framing is True


def test_a_pipeline_without_the_opt_in_keeps_the_default_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    captured: dict = {}

    def fake_orchestrator(project_id, media_id=None, *, settings_override=None):
        captured["settings"] = settings_override
        raise RuntimeError("stop before any stage runs")

    monkeypatch.setattr(job_manager, "_get_or_create_orchestrator", fake_orchestrator)

    job = _job_record(config_json=None)
    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(job_manager._execute_pipeline(job, asyncio.Event()))

    assert captured["settings"] is None
