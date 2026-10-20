"""Tests for job queue, worker lifecycle, and audio extraction (PRD §5 FR-02 & FR-10)."""

import asyncio
import io
import json
import subprocess
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.repository import ProjectRepository
from app.schemas.jobs import JobStatus
from app.services.media.audio import (
    AudioExtractionError,
    JobCancelledError,
    build_audio_extraction_command,
    clean_intermediate_audio,
    extract_audio_16k,
)


@pytest.fixture
def tiny_mp4_bytes(tmp_path: Path) -> bytes:
    """Generate a tiny 1-second synthetic MP4 file containing video and audio."""
    fixture_path = tmp_path / "synthetic_tiny.mp4"
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


def test_command_construction() -> None:
    """Requirement: ffmpeg command must use argument arrays, mono, 16 kHz, pcm_s16le, no shell."""
    cmd = build_audio_extraction_command(
        ffmpeg_bin="/usr/bin/ffmpeg",
        input_path=Path("/tmp/input.mp4"),
        output_path=Path("/tmp/output.wav"),
    )
    expected = [
        "/usr/bin/ffmpeg",
        "-y",
        "-i",
        "/tmp/input.mp4",
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "/tmp/output.wav",
    ]
    assert cmd == expected
    assert "-vn" in cmd  # No video
    assert "pcm_s16le" in cmd  # 16-bit PCM WAV
    assert "1" in cmd  # Mono
    assert "16000" in cmd  # 16 kHz


def test_job_state_transitions(tmp_path: Path) -> None:
    """Requirement: SQLite transitions queued -> running -> succeeded / failed / cancelled."""
    test_db = tmp_path / "test_state.db"
    repo = ProjectRepository(db_path=test_db)
    proj = repo.create_project(name="State Test Project")

    # 1. Queued
    job = repo.create_job(project_id=proj.id, job_type="audio_extraction")
    assert job.status == JobStatus.QUEUED.value
    assert job.progress == 0.0

    # 2. Running
    updated = repo.update_job(
        job_id=job.id,
        status=JobStatus.RUNNING.value,
        stage="extracting_audio",
        progress=45.0,
        started_at="2026-10-18T05:00:00Z",
    )
    assert updated is not None
    assert updated.status == JobStatus.RUNNING.value
    assert updated.progress == 45.0
    assert updated.stage == "extracting_audio"

    # 3. Succeeded
    finished = repo.update_job(
        job_id=job.id,
        status=JobStatus.SUCCEEDED.value,
        stage="completed",
        progress=100.0,
        finished_at="2026-10-18T05:00:05Z",
        config_json=json.dumps({"sample_rate": 16000}),
    )
    assert finished is not None
    assert finished.status == JobStatus.SUCCEEDED.value
    assert finished.progress == 100.0
    assert finished.finished_at == "2026-10-18T05:00:05Z"
    assert "sample_rate" in (finished.config_json or "")


@pytest.mark.asyncio
async def test_missing_ffmpeg_failure(tmp_path: Path) -> None:
    """Requirement: Missing FFmpeg cleanly fails with explicit error code, never crashes."""
    dummy_input = tmp_path / "test.mp4"
    dummy_input.write_bytes(b"dummy")
    out_path = tmp_path / "out.wav"

    with pytest.raises(AudioExtractionError) as exc_info:
        await extract_audio_16k(
            input_path=dummy_input,
            output_path=out_path,
            ffmpeg_bin_override="/nonexistent/path/to/ffmpeg",
        )

    assert exc_info.value.error_code == "FFMPEG_NOT_FOUND"
    assert "FFmpeg is not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancellation_removes_partial_output(tmp_path: Path) -> None:
    """Requirement: Cancellation terminates subprocess and cleans intermediate file."""
    dummy_input = tmp_path / "input.mp4"
    dummy_input.write_bytes(b"dummy")
    out_path = tmp_path / "cancelled.wav"

    cancel_event = asyncio.Event()
    cancel_event.set()  # Pre-cancelled

    with pytest.raises(JobCancelledError):
        await extract_audio_16k(
            input_path=dummy_input,
            output_path=out_path,
            cancel_event=cancel_event,
        )

    assert not out_path.exists()


@pytest.mark.asyncio
async def test_corrupted_media_failure(tmp_path: Path) -> None:
    """Requirement: Corrupted media fails with FFMPEG_ERROR and bounded diagnostic stderr."""
    corrupted_input = tmp_path / "corrupted.mp4"
    corrupted_input.write_bytes(b"not a valid video bitstream header")
    out_path = tmp_path / "out.wav"

    with pytest.raises(AudioExtractionError) as exc_info:
        await extract_audio_16k(
            input_path=corrupted_input,
            output_path=out_path,
        )

    assert exc_info.value.error_code == "FFMPEG_ERROR"
    assert exc_info.value.diagnostic_logs is not None
    assert not out_path.exists()


def test_restart_recovery(tmp_path: Path) -> None:
    """Requirement: On restart, do not pretend running jobs resumed; mark interrupted/failed."""
    test_db = tmp_path / "test_restart.db"
    repo = ProjectRepository(db_path=test_db)
    proj = repo.create_project(name="Restart Test")

    # Simulate a job left in running state when process was killed
    job = repo.create_job(project_id=proj.id, job_type="audio_extraction")
    repo.update_job(job_id=job.id, status=JobStatus.RUNNING.value, stage="extracting")

    # Run recovery
    interrupted_count = repo.recover_interrupted_jobs()
    assert interrupted_count == 1

    recovered_job = repo.get_job(job.id)
    assert recovered_job is not None
    assert recovered_job.status == JobStatus.FAILED.value
    assert recovered_job.error_code == "INTERRUPTED_ON_RESTART"
    assert "interrupted by server shutdown/restart" in (recovered_job.error_message or "")
    assert "safely retried" in (recovered_job.error_message or "")


def test_clean_intermediate_wav_safety(tmp_path: Path) -> None:
    """Requirement: Never delete original input; only clean intermediate WAV when configured."""
    temp_dir = tmp_path / "projects" / "p1" / "temp" / "j1"
    temp_dir.mkdir(parents=True)
    temp_wav = temp_dir / "audio_16k.wav"
    temp_wav.write_bytes(b"RIFF dummy wav")

    media_dir = tmp_path / "projects" / "p1" / "media"
    media_dir.mkdir(parents=True)
    original_media = media_dir / "original.mp4"
    original_media.write_bytes(b"mp4 content")

    # With clean enabled
    original_setting = settings.CLEAN_INTERMEDIATE_WAV
    try:
        settings.CLEAN_INTERMEDIATE_WAV = True

        # Intermediate WAV in temp/ is deleted
        cleaned = clean_intermediate_audio(temp_wav)
        assert cleaned is True
        assert not temp_wav.exists()

        # Original media in media/ is NEVER deleted
        media_cleaned = clean_intermediate_audio(original_media)
        assert media_cleaned is False
        assert original_media.exists()
    finally:
        settings.CLEAN_INTERMEDIATE_WAV = original_setting


def test_audio_extraction_integration_e2e(
    client: TestClient,
    tiny_mp4_bytes: bytes,
) -> None:
    """Integration test: upload real tiny MP4, enqueue audio extraction, verify 16 kHz mono WAV."""
    # 1. Create project
    res_proj = client.post("/api/projects", json={"name": "Audio Integration Project"})
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]

    # 2. Upload media
    files = {"file": ("integration_clip.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}
    res_upload = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res_upload.status_code == 201
    media_id = res_upload.json()["id"]

    # 3. Submit audio extraction job
    res_job = client.post(f"/api/media/{media_id}/audio-extraction-jobs")
    assert res_job.status_code == 201
    job_data = res_job.json()
    job_id = job_data["id"]
    assert job_data["status"] in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
    assert job_data["media_id"] == media_id
    assert job_data["project_id"] == project_id

    # 4. Poll until job completes (with timeout)
    max_wait_seconds = 10
    start_time = time.time()
    final_job: dict | None = None

    while time.time() - start_time < max_wait_seconds:
        res_poll = client.get(f"/api/jobs/{job_id}")
        assert res_poll.status_code == 200
        current = res_poll.json()
        if current["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            final_job = current
            break
        time.sleep(0.2)

    assert final_job is not None, "Job timed out during integration test"
    assert final_job["status"] == JobStatus.SUCCEEDED.value
    assert final_job["progress"] == 100.0
    assert final_job["stage"] == "completed"

    # 5. Verify output file exists and is valid 16 kHz mono WAV
    cfg = json.loads(final_job["config_json"])
    wav_path = Path(cfg["output_wav_path"])
    assert wav_path.exists()
    assert wav_path.stat().st_size > 0

    # Probe extracted WAV using Python's standard wave library
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1  # Strictly mono
        assert wf.getframerate() == 16000  # Strictly 16 kHz
        assert wf.getsampwidth() == 2  # 16-bit PCM (2 bytes/sample)
        assert wf.getnframes() > 0

    # Probe extracted WAV with ffprobe to verify codec
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,channels,sample_rate",
        "-of",
        "json",
        str(wav_path),
    ]
    probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    probe_info = json.loads(probe_res.stdout)
    audio_stream = probe_info["streams"][0]
    assert audio_stream["codec_name"] == "pcm_s16le"
    assert audio_stream["channels"] == 1
    assert audio_stream["sample_rate"] == "16000"

    # 6. Verify original source media was NOT deleted
    media_asset = client.get(f"/api/media/{media_id}").json()
    assert media_asset["id"] == media_id

    # 7. List project jobs
    res_list = client.get(f"/api/projects/{project_id}/jobs")
    assert res_list.status_code == 200
    jobs_list = res_list.json()
    assert len(jobs_list) >= 1
    assert any(j["id"] == job_id for j in jobs_list)


def test_cancel_job_endpoint(client: TestClient, tiny_mp4_bytes: bytes) -> None:
    """Test cancellation endpoint on a job."""
    # Create project and upload media
    proj = client.post("/api/projects", json={"name": "Cancel Test Project"}).json()
    files = {"file": ("clip.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}
    media = client.post(f"/api/projects/{proj['id']}/media", files=files).json()

    # Submit job
    job = client.post(f"/api/media/{media['id']}/audio-extraction-jobs").json()

    # Cancel job
    cancel_res = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancel_res.status_code == 200
    cancelled_job = cancel_res.json()
    assert cancelled_job["status"] in {JobStatus.CANCELLED.value, JobStatus.SUCCEEDED.value}


def test_clear_project_jobs_endpoint(client: TestClient, tiny_mp4_bytes: bytes) -> None:
    """Test clearing historical jobs for a project."""
    proj = client.post("/api/projects", json={"name": "Clear Jobs Test"}).json()
    files = {"file": ("clip.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}
    media = client.post(f"/api/projects/{proj['id']}/media", files=files).json()

    # Create job and cancel it so it's historical
    job = client.post(f"/api/media/{media['id']}/audio-extraction-jobs").json()
    client.post(f"/api/jobs/{job['id']}/cancel")

    # Clear jobs
    clear_res = client.delete(f"/api/projects/{proj['id']}/jobs")
    assert clear_res.status_code == 200
    assert "deleted_count" in clear_res.json()

    # Verify list is empty
    list_res = client.get(f"/api/projects/{proj['id']}/jobs")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 0
