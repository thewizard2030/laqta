"""Tests for transcription subsystem (PRD §5 FR-03, §8, §10, and §11 Gate B).

Validates:
- Typed TranscriptionProvider interface & FakeTranscriptionProvider fixtures.
- Truthful reporting of timing granularity ('word' vs 'segment').
- Arabic and English transcript handling.
- Lazy model loading & uninstalled package diagnostics.
- Cooperative cancellation mid-transcription.
- E2E transcription job flow with audio extraction and SQLite persistence.
- Preservation of historical transcripts across multiple runs/models.
- Opt-in real Whisper test skipped by default so CI does not download model weights.
"""

import asyncio
import io
import os
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.jobs import JobStatus
from app.services.media.audio import JobCancelledError
from app.services.transcription.base import TranscriptionError
from app.services.transcription.fake_provider import FakeTranscriptionProvider
from app.services.transcription.faster_whisper_provider import (
    FasterWhisperProvider,
    is_faster_whisper_installed,
)


@pytest.fixture
def tiny_mp4_bytes(tmp_path: Path) -> bytes:
    """Generate a tiny 1-second synthetic MP4 file containing video and audio."""
    fixture_path = tmp_path / "synthetic_tiny_transcription.mp4"
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


@pytest.mark.asyncio
async def test_fake_provider_word_level_english(tmp_path: Path) -> None:
    """Requirement: report word timings and truthful timing granularity ('word')."""
    dummy_audio = tmp_path / "dummy.wav"
    dummy_audio.write_bytes(b"dummy wav data")

    provider = FakeTranscriptionProvider()
    assert provider.is_available() is True

    result = await provider.transcribe(
        audio_path=dummy_audio,
        language="en",
        model_size="base",
        word_timestamps=True,
    )

    assert result.language == "en"
    assert result.provider == "fake"
    assert result.model == "base"
    assert result.word_timestamps_available is True
    assert result.timing_granularity == "word"
    assert len(result.segments) > 0
    assert "Laqta" in result.text

    # Verify first segment has word timings
    seg = result.segments[0]
    assert seg.start >= 0.0
    assert seg.end > seg.start
    assert seg.words is not None
    assert len(seg.words) > 0
    for w in seg.words:
        assert w.word
        assert w.end >= w.start
        assert w.probability is not None


@pytest.mark.asyncio
async def test_fake_provider_arabic_segment_level(tmp_path: Path) -> None:
    """Requirement: truthful timing granularity ('segment') when words disabled."""
    dummy_audio = tmp_path / "dummy_ar.wav"
    dummy_audio.write_bytes(b"dummy wav data")

    provider = FakeTranscriptionProvider()
    result = await provider.transcribe(
        audio_path=dummy_audio,
        language="ar",
        model_size="base",
        word_timestamps=False,
    )

    assert result.language == "ar"
    assert result.word_timestamps_available is False
    assert result.timing_granularity == "segment"
    assert "لقطّة" in result.text  # Laqta in Arabic
    assert len(result.segments) > 0
    # Words should not be present when word_timestamps=False
    for seg in result.segments:
        assert seg.words is None


@pytest.mark.asyncio
async def test_fake_provider_cancellation(tmp_path: Path) -> None:
    """Requirement: cooperative cancellation handling."""
    dummy_audio = tmp_path / "dummy.wav"
    dummy_audio.write_bytes(b"dummy wav data")

    cancel_event = asyncio.Event()
    cancel_event.set()  # Pre-cancelled

    provider = FakeTranscriptionProvider()
    with pytest.raises(JobCancelledError):
        await provider.transcribe(
            audio_path=dummy_audio,
            cancel_event=cancel_event,
        )


@pytest.mark.asyncio
async def test_faster_whisper_uninstalled_diagnostics(tmp_path: Path) -> None:
    """Requirement: actionable errors for missing packages."""
    dummy_audio = tmp_path / "dummy.wav"
    dummy_audio.write_bytes(b"dummy wav data")

    provider = FasterWhisperProvider()
    with patch(
        "app.services.transcription.faster_whisper_provider.is_faster_whisper_installed",
        return_value=False,
    ):
        assert provider.is_available() is False
        with pytest.raises(TranscriptionError) as exc_info:
            await provider.transcribe(audio_path=dummy_audio)

        assert exc_info.value.error_code == "PACKAGE_NOT_INSTALLED"
        assert "pip install" in exc_info.value.message


def test_faster_whisper_lazy_loading() -> None:
    """Requirement: models loaded lazily and never at API import time."""
    from app.services.transcription.faster_whisper_provider import _LOADED_MODELS

    # Simply importing the provider must NOT populate the model cache
    assert len(_LOADED_MODELS) == 0


def test_transcription_media_not_found(client: TestClient) -> None:
    """Verify enqueuing a transcription job for a non-existent media asset returns 404."""
    res = client.post(
        "/api/media/non-existent-media-id/transcription-jobs",
        json={"model_size": "base"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_transcription_e2e_and_preserve_history(
    client: TestClient,
    tiny_mp4_bytes: bytes,
) -> None:
    """Requirement:
    - Audio extraction stage executes seamlessly.
    - Persist transcript data in validated schema.
    - Preserve previous successful transcripts when retrying with a different model.
    """
    # 1. Create project & upload media
    res_proj = client.post("/api/projects", json={"name": "Transcription Test Project"})
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]

    files = {"file": ("tiny_clip.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}
    res_upload = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res_upload.status_code == 201
    media_id = res_upload.json()["id"]

    # 2. Enqueue first transcription job (English, fake provider, base model)
    res_job1 = client.post(
        f"/api/media/{media_id}/transcription-jobs",
        json={
            "model_size": "base",
            "language": "en",
            "word_timestamps": True,
            "provider": "fake",
        },
    )
    assert res_job1.status_code == 201
    job1_data = res_job1.json()
    job1_id = job1_data["id"]

    # Poll until job 1 completes
    max_wait = 10
    start = time.time()
    job1_final = None
    while time.time() - start < max_wait:
        res = client.get(f"/api/jobs/{job1_id}")
        assert res.status_code == 200
        cur = res.json()
        if cur["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            job1_final = cur
            break
        time.sleep(0.2)

    assert job1_final is not None
    assert job1_final["status"] == JobStatus.SUCCEEDED.value
    assert job1_final["progress"] == 100.0

    # Retrieve transcripts list for this media
    res_transcripts = client.get(f"/api/media/{media_id}/transcripts")
    assert res_transcripts.status_code == 200
    transcripts_list = res_transcripts.json()
    assert len(transcripts_list) == 1

    t1 = transcripts_list[0]
    assert t1["language"] == "en"
    assert t1["model"] == "base"
    assert t1["timing_granularity"] == "word"
    assert t1["word_timestamps_available"] is True
    assert len(t1["segments"]) > 0

    # Retrieve single transcript by ID
    res_t1 = client.get(f"/api/transcripts/{t1['id']}")
    assert res_t1.status_code == 200
    assert res_t1.json()["id"] == t1["id"]
    assert res_t1.json()["text"] == t1["text"]

    # 3. Enqueue second job for the same media with different model (Arabic, tiny)
    res_job2 = client.post(
        f"/api/media/{media_id}/transcription-jobs",
        json={
            "model_size": "tiny",
            "language": "ar",
            "word_timestamps": False,
            "provider": "fake",
        },
    )
    assert res_job2.status_code == 201
    job2_id = res_job2.json()["id"]

    start = time.time()
    job2_final = None
    while time.time() - start < max_wait:
        res = client.get(f"/api/jobs/{job2_id}")
        assert res.status_code == 200
        cur = res.json()
        if cur["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            job2_final = cur
            break
        time.sleep(0.2)

    assert job2_final is not None
    assert job2_final["status"] == JobStatus.SUCCEEDED.value

    # 4. Verify BOTH transcripts are preserved (history preservation requirement)
    res_transcripts_updated = client.get(f"/api/media/{media_id}/transcripts")
    assert res_transcripts_updated.status_code == 200
    all_transcripts = res_transcripts_updated.json()
    assert len(all_transcripts) == 2

    # The most recent should be the Arabic one
    latest_t = all_transcripts[0]
    older_t = all_transcripts[1]
    assert latest_t["language"] == "ar"
    assert latest_t["model"] == "tiny"
    assert latest_t["timing_granularity"] == "segment"
    assert latest_t["word_timestamps_available"] is False

    assert older_t["id"] == t1["id"]
    assert older_t["language"] == "en"
    assert older_t["model"] == "base"


@pytest.mark.skipif(
    not os.environ.get("QATTA_TEST_REAL_WHISPER"),
    reason="Opt-in test requiring real faster-whisper model weights; CI must not download weights",
)
@pytest.mark.asyncio
async def test_opt_in_real_whisper_integration(tmp_path: Path) -> None:
    """Opt-in integration test verifying real faster-whisper inference if weights are present."""
    if not is_faster_whisper_installed():
        pytest.skip("faster-whisper is not installed")

    # Generate synthetic 16 kHz WAV audio file
    wav_path = tmp_path / "real_test.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=mono:sample_rate=16000",
        "-t",
        "1",
        str(wav_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    provider = FasterWhisperProvider()
    target_model = os.environ.get("QATTA_TEST_WHISPER_MODEL", "base")
    result = await provider.transcribe(
        audio_path=wav_path,
        model_size=target_model,
        language="en",
    )
    assert result.provider == "faster-whisper"
    assert result.model == target_model
    assert isinstance(result.segments, list)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg unavailable; synthetic audio fixture cannot be generated",
)
def test_decode_audio_to_float32_pyav19_metadata_errors_bypass(tmp_path: Path) -> None:
    """_decode_audio_to_float32 must not hit faster-whisper's broken decode path.

    faster-whisper 1.2.1 passes `metadata_errors=` to av.open, which PyAV >= 14
    (the only wheels built for Python 3.14) removed. Our provider decodes via
    av.AudioResampler itself and passes an ndarray, so this regression cannot
    recur even if `model.transcribe` falls back to file input.
    """
    from app.services.transcription.faster_whisper_provider import (
        _decode_audio_to_float32,
        is_faster_whisper_installed,
    )

    if not is_faster_whisper_installed():
        # Helper is independent of faster-whisper, but skip keeps intent clear
        # for environments where the feature under repair is absent.
        pytest.skip("faster-whisper context not installed")

    audio_path = tmp_path / "sine_44k1_stereo.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:duration=2",
        "-ac",
        "2",
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    audio = _decode_audio_to_float32(audio_path)
    assert audio.dtype.name == "float32"
    # Frame-boundary trimming by the resampler loses a few samples (~2 for 2 s
    # at 44.1 kHz); 31,984 measured live with PyAV 19 on this exact fixture.
    assert len(audio) in range(31000, 33000), f"unexpected length {len(audio)}"
    assert 0.02 < float(audio.max()) <= 1.0, "sine tone must decode at audible level"


def test_find_local_whisper_snapshot(tmp_path: Path) -> None:
    """find_local_whisper_snapshot finds models across direct, custom, and HF paths."""
    from app.services.transcription.faster_whisper_provider import find_local_whisper_snapshot

    # 1. Non-existent model returns None without throwing
    assert find_local_whisper_snapshot("non_existent_model_xyz", [tmp_path]) is None

    # 2. Direct folder with model.bin
    direct_model = tmp_path / "custom_model"
    direct_model.mkdir()
    (direct_model / "model.bin").write_bytes(b"dummy")
    found = find_local_whisper_snapshot(str(direct_model))
    assert found == str(direct_model)

    # 3. HF-style snapshots directory in custom_dir
    custom_root = tmp_path / "whisper_cache"
    repo_dir = custom_root / "models--Systran--faster-whisper-tiny"
    snap_dir = repo_dir / "snapshots" / "abc12345"
    snap_dir.mkdir(parents=True)
    (snap_dir / "model.bin").write_bytes(b"dummy")

    found_custom = find_local_whisper_snapshot("tiny", [custom_root])
    assert found_custom == str(snap_dir)


@pytest.mark.asyncio
async def test_load_whisper_model_prioritizes_local_snapshot(tmp_path: Path) -> None:
    """load_whisper_model must load directly from local snapshot if present."""
    from unittest.mock import MagicMock, patch

    from app.services.transcription.faster_whisper_provider import (
        _LOADED_MODELS,
        load_whisper_model,
    )

    mock_whisper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_whisper_cls.return_value = mock_instance

    snap_dir = tmp_path / "snapshots" / "snap_01"
    snap_dir.mkdir(parents=True)
    (snap_dir / "model.bin").write_bytes(b"dummy")

    with (
        patch("faster_whisper.WhisperModel", mock_whisper_cls),
        patch(
            "app.services.transcription.faster_whisper_provider.find_local_whisper_snapshot",
            return_value=str(snap_dir),
        ),
    ):
        # Clear model cache for this key
        cache_key = ("test_snap_model", "cpu", "int8")
        _LOADED_MODELS.pop(cache_key, None)

        loaded = await load_whisper_model(
            model_size="test_snap_model",
            device="cpu",
            compute_type="int8",
            download_root=tmp_path,
        )

        assert loaded is mock_instance
        # Must pass the direct snapshot path string, bypassing online download_model
        assert mock_whisper_cls.call_args[1]["model_size_or_path"] == str(snap_dir)


@pytest.mark.asyncio
async def test_load_whisper_model_download_failure_diagnostics(tmp_path: Path) -> None:
    """When model is missing and network download fails, raises MODEL_DOWNLOAD_FAILED."""
    from unittest.mock import MagicMock, patch

    from app.services.transcription.faster_whisper_provider import (
        _LOADED_MODELS,
        load_whisper_model,
    )

    err = "LocalEntryNotFoundError: 403 Forbidden: None."
    mock_whisper_cls = MagicMock(side_effect=Exception(err))

    with (
        patch("faster_whisper.WhisperModel", mock_whisper_cls),
        patch(
            "app.services.transcription.faster_whisper_provider.find_local_whisper_snapshot",
            return_value=None,
        ),
    ):
        cache_key = ("missing_model_403", "cpu", "int8")
        _LOADED_MODELS.pop(cache_key, None)

        with pytest.raises(TranscriptionError) as exc_info:
            await load_whisper_model(
                model_size="missing_model_403",
                device="cpu",
                compute_type="int8",
                download_root=tmp_path,
            )

        assert exc_info.value.error_code == "MODEL_DOWNLOAD_FAILED"
        assert "pre-download" in str(exc_info.value.message).lower()


def test_v1_models_endpoint_returns_ok() -> None:
    """GET /v1/models probe route returns 200 with empty list to silence local probe 404 noise."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert data["data"] == []
