"""Tests for media import, signature validation, and ffprobe processing."""

import io
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.media.probe import MediaProbeError


@pytest.fixture
def project_id(client: TestClient) -> str:
    """Fixture providing a clean project for media tests."""
    res = client.post("/api/projects", json={"name": "Media Test Project"})
    assert res.status_code == 201
    return res.json()["id"]


@pytest.fixture
def tiny_mp4_bytes(tmp_path: Path) -> bytes:
    """Generate a tiny 1-second synthetic MP4 file for happy path testing."""
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


def test_upload_invalid_extension(client: TestClient, project_id: str) -> None:
    """Requirement: reject files with disallowed extensions."""
    file_content = b"fake executable content"
    files = {
        "file": ("malicious_payload.exe", io.BytesIO(file_content), "application/octet-stream")
    }

    res = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res.status_code == 400
    assert "Unsupported file extension" in res.json()["detail"]


def test_upload_fake_media_rejected(client: TestClient, project_id: str) -> None:
    """Requirement: reject fake media files where extension does not match binary headers.

    Extensions alone are not trusted; magic bytes must match a valid container.
    """
    fake_content = b"This is plain text pretending to be a video clip."
    files = {"file": ("fake_video.mp4", io.BytesIO(fake_content), "video/mp4")}

    res = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "File signature does not match" in detail or "Invalid file content" in detail
    assert "extensions" in detail.lower()


def test_upload_path_traversal_attempt(
    client: TestClient,
    project_id: str,
    tiny_mp4_bytes: bytes,
) -> None:
    """Requirement: client-supplied path traversal attempts must be neutralized.

    Files must be stored strictly in server-generated, project-isolated directories.
    """
    traversal_filename = "../../../../etc/cron.d/malicious_job.mp4"
    files = {"file": (traversal_filename, io.BytesIO(tiny_mp4_bytes), "video/mp4")}

    res = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res.status_code == 201
    media = res.json()

    # Original filename basename is preserved safely without directory components
    assert media["original_name"] == "malicious_job.mp4"
    assert ".." not in media["original_name"]

    # File on disk is strictly located inside the project media directory
    media_dir = settings.get_project_media_dir(project_id)
    stored_files = list(media_dir.glob("*.mp4"))
    assert len(stored_files) >= 1
    for f in stored_files:
        assert f.is_relative_to(media_dir)


def test_upload_oversized(
    client: TestClient,
    project_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement: files exceeding MAX_UPLOAD_SIZE_BYTES must be rejected and cleaned up."""
    # Set limit to 50 bytes for test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 50)

    # Valid MP4 header but 200 bytes total
    data = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 180
    files = {"file": ("oversized.mp4", io.BytesIO(data), "video/mp4")}

    res = client.post(f"/api/projects/{project_id}/media", files=files)
    assert res.status_code == 413
    assert "exceeds maximum allowed upload size" in res.json()["detail"]

    # Verify no leaked partial file remains
    media_dir = settings.get_project_media_dir(project_id)
    assert list(media_dir.glob("*.mp4")) == []


def test_upload_missing_ffmpeg(
    client: TestClient,
    project_id: str,
    tiny_mp4_bytes: bytes,
) -> None:
    """Requirement: missing FFprobe reports a clean 503 error without crashing."""
    files = {"file": ("valid.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}

    with patch(
        "app.api.routes.projects.probe_media_file",
        side_effect=MediaProbeError("FFprobe is not installed on this system. Cannot probe media."),
    ):
        res = client.post(f"/api/projects/{project_id}/media", files=files)
        assert res.status_code == 503
        assert "FFprobe is not installed" in res.json()["detail"]


def test_upload_happy_path(
    client: TestClient,
    project_id: str,
    tiny_mp4_bytes: bytes,
) -> None:
    """Requirement: upload valid video, probe streams, save to DB, and query via API."""
    files = {"file": ("real_clip.mp4", io.BytesIO(tiny_mp4_bytes), "video/mp4")}

    upload_res = client.post(f"/api/projects/{project_id}/media", files=files)
    assert upload_res.status_code == 201
    media = upload_res.json()

    assert media["id"].startswith("med_")
    assert media["project_id"] == project_id
    assert media["original_name"] == "real_clip.mp4"
    assert media["duration_ms"] >= 900  # ~1000 ms
    assert media["width"] == 160
    assert media["height"] == 120
    assert media["video_codec"] == "mpeg4"
    assert media["audio_codec"] == "aac"
    assert media["status"] == "ready"

    # Verify project details query contains this media asset
    proj_res = client.get(f"/api/projects/{project_id}")
    assert proj_res.status_code == 200
    proj_data = proj_res.json()
    assert proj_data["media_count"] == 1
    assert proj_data["media_assets"][0]["id"] == media["id"]

    # Verify GET /api/media/{media_id} endpoint
    media_get_res = client.get(f"/api/media/{media['id']}")
    assert media_get_res.status_code == 200
    assert media_get_res.json()["id"] == media["id"]
