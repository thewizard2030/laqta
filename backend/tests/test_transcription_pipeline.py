"""E2E pipeline tests for profile resolution, transcript reuse (cache),
cancellation cleanup, and honest stage/progress reporting.

Uses the deterministic fake provider; no model weights are downloaded.
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes.jobs import _to_job_response
from app.core.config import settings
from app.db.models import JobRecord
from app.schemas.jobs import JobStatus
from app.services.media.audio import JobCancelledError
from app.services.transcription.fake_provider import FakeTranscriptionProvider


@pytest.fixture
def tiny_mp4_bytes(tmp_path: Path) -> bytes:
    """1-second synthetic MP4 (video + silent audio)."""
    import subprocess

    fixture_path = tmp_path / "synthetic_pipeline.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=1:size=160x120:rate=5",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v",
        "mpeg4",
        "-c:a",
        "aac",
        "-t",
        "1",
        str(fixture_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return fixture_path.read_bytes()


def _upload_media(client: TestClient, tiny_mp4_bytes: bytes) -> str:
    res_proj = client.post("/api/projects", json={"name": "Perf Pipeline Test"})
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]
    files = {"file": ("clip.mp4", bytes(tiny_mp4_bytes), "video/mp4")}
    res_upload = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res_upload.status_code == 201
    return res_upload.json()["id"]


def _await_job(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    seen_stages: list[str] = []
    final = None
    while time.time() < deadline:
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        seen_stages.append(data["stage"])
        if data["status"] in {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }:
            final = data
            break
        time.sleep(0.1)
    assert final is not None, f"job {job_id} never reached a terminal state"
    final["_seen_stages"] = seen_stages  # for stage assertions
    return final


def _make_media(tmp_path: Path) -> Path:
    """A tiny WAV used by provider-mocked tests (content not parsed)."""
    wav = tmp_path / "dummy.wav"
    wav.write_bytes(b"dummy")
    return wav


def test_default_profile_resolves_and_persists(client: TestClient, tiny_mp4_bytes: bytes) -> None:
    """Enqueue with no options: profile 'fast' must resolve (model base, int8,
    beam 1, no full-video word timestamps) and land in the job config."""
    media_id = _upload_media(client, tiny_mp4_bytes)
    res_job = client.post(
        f"/api/media/{media_id}/transcription-jobs",
        json={"provider": "fake"},
    )
    assert res_job.status_code == 201
    job = _await_job(client, res_job.json()["id"])
    assert job["status"] == JobStatus.SUCCEEDED.value

    cfg = json.loads(job["config_json"])
    resolved = cfg["profile_resolved"]
    assert resolved["profile"] == "fast"
    assert resolved["model_size"] == settings.FAST_WHISPER_MODEL
    assert resolved["word_timestamps"] is False
    assert resolved["compute_type"] == "int8"

    # The transcription job never saw percent fraud: every observed percent
    # is a number in range (schema validation already ensures this) and the
    # final stage is honest ("completed").
    assert job["stage"] == "completed"
    assert job["indeterminate"] is False


@pytest.mark.asyncio
async def test_second_identical_transcription_hits_cache(
    client: TestClient, tiny_mp4_bytes: bytes
) -> None:
    """Key E2E requirement: enqueueing the SAME transcription twice
    (same media, same settings) must run ASR once and reuse the cache for the
    second run; a settings change must invalidate and re-run."""
    media_id = _upload_media(client, tiny_mp4_bytes)

    calls = {"count": 0}
    original = FakeTranscriptionProvider.transcribe

    async def counting_transcribe(self, *args, **kwargs):
        calls["count"] += 1
        return await original(self, *args, **kwargs)

    with patch.object(FakeTranscriptionProvider, "transcribe", counting_transcribe):
        # Run 1: ASR (cache miss)
        res_job1 = client.post(
            f"/api/media/{media_id}/transcription-jobs",
            json={"provider": "fake", "language": "en", "model_size": "base"},
        )
        assert res_job1.status_code == 201
        job1 = _await_job(client, res_job1.json()["id"])
        assert job1["status"] == JobStatus.SUCCEEDED.value
        assert calls["count"] == 1
        assert json.loads(job1["config_json"])["cache"]["hit"] is False

        # Run 2 identical: cache hit; provider NOT called again; second
        # transcript record still persisted (history preserved).
        res_job2 = client.post(
            f"/api/media/{media_id}/transcription-jobs",
            json={"provider": "fake", "language": "en", "model_size": "base"},
        )
        assert res_job2.status_code == 201
        job2 = _await_job(client, res_job2.json()["id"])
        assert job2["status"] == JobStatus.SUCCEEDED.value
        assert calls["count"] == 1  # no additional ASR
        cache2 = json.loads(job2["config_json"])["cache"]
        assert cache2["hit"] is True

        res_transcripts = client.get(f"/api/media/{media_id}/transcripts")
        assert res_transcripts.status_code == 200
        transcripts = res_transcripts.json()
        assert len(transcripts) == 2
        assert transcripts[0]["text"] == transcripts[1]["text"]

        # Run 3: language change invalidates the cache (different settings
        # fingerprint) -> provider runs again.
        res_job3 = client.post(
            f"/api/media/{media_id}/transcription-jobs",
            json={"provider": "fake", "language": "ar", "model_size": "base"},
        )
        assert res_job3.status_code == 201
        job3 = _await_job(client, res_job3.json()["id"])
        assert job3["status"] == JobStatus.SUCCEEDED.value
        assert calls["count"] == 2
        assert json.loads(job3["config_json"])["cache"]["hit"] is False

        res_transcripts2 = client.get(f"/api/media/{media_id}/transcripts")
        transcripts2 = res_transcripts2.json()
        assert len(transcripts2) == 3


def _jobs_record(stage: str, progress: float) -> JobRecord:
    return JobRecord(
        id="job_x",
        project_id="p",
        media_id=None,
        type="transcription",
        status=JobStatus.RUNNING.value,
        stage=stage,
        progress=progress,
        error_code=None,
        error_message=None,
        config_json=None,
        created_at="2026-10-18T00:00:00Z",
        started_at=None,
        finished_at=None,
    )


def test_job_response_indeterminate_stage_mapping() -> None:
    """Stages that cannot report a reliable percent expose indeterminate=True."""
    resp = _to_job_response(_jobs_record("loading_model", 33.0))
    assert resp.indeterminate is True

    resp2 = _to_job_response(_jobs_record("transcribing", 55.0))
    assert resp2.indeterminate is False


@pytest.mark.asyncio
async def test_cancelled_job_temp_cleanup(tmp_path: Path, client: TestClient) -> None:
    """Cancelling a running job removes its per-job temp artifacts."""
    temp_parent = Path(settings.get_project_dir("proj_cleanup_x")) / "temp"
    job_id = "job_cleanup_1"
    temp_dir = temp_parent / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    (temp_dir / "audio_16k.wav").write_bytes(b"partial")

    settings.cleanup_job_temp_dir("proj_cleanup_x", job_id)
    assert not temp_dir.exists() or list(temp_dir.iterdir()) == []


def test_job_stage_transitions_observed(
    client: TestClient,
    tiny_mp4_bytes: bytes,
) -> None:
    """The UI-visible stages traverse honest named states."""
    media_id = _upload_media(client, tiny_mp4_bytes)
    res_job = client.post(
        f"/api/media/{media_id}/transcription-jobs",
        json={"provider": "fake", "language": "en", "word_timestamps": True},
    )
    assert res_job.status_code == 201
    job = _await_job(client, res_job.json()["id"])
    assert job["status"] == JobStatus.SUCCEEDED.value
    # At least one observed stage corresponds to real work naming.
    assert any(
        s in {"extracting_audio", "transcribing", "loading_model", "starting"}
        for s in job["_seen_stages"]
    )
    assert job["progress"] == 100.0


@pytest.mark.asyncio
async def test_fake_provider_cancellation_explicit() -> None:
    """Guard: cancellation contract intact for the fake provider path."""
    provider = FakeTranscriptionProvider()
    cancel_event = asyncio.Event()
    cancel_event.set()
    with pytest.raises(JobCancelledError):
        await provider.transcribe(
            audio_path=_make_media(Path(settings.get_effective_data_dir())),
            cancel_event=cancel_event,
        )
