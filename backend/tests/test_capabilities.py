"""Tests for GET /api/capabilities."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.schemas.capabilities import BinaryCapability, FFmpegCapability


def test_get_capabilities(client: TestClient) -> None:
    """Verify capabilities endpoint returns status 200 and valid schema."""
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    data = response.json()

    assert data["app_name"] == "Laqta"
    assert data["local_only"] is True
    assert "ffmpeg" in data
    assert "ffprobe" in data
    assert "asr" in data
    assert "llm" in data
    assert "hardware" in data
    assert "storage" in data

    # FFmpeg detection structure
    assert isinstance(data["ffmpeg"]["available"], bool)
    assert isinstance(data["ffmpeg"]["has_libass"], bool)
    if data["ffmpeg"]["available"]:
        assert data["ffmpeg"]["path"] is not None
        assert data["ffmpeg"]["version"] is not None

    # Storage structure
    assert "data_dir" in data["storage"]
    assert isinstance(data["storage"]["exists"], bool)
    assert isinstance(data["storage"]["writable"], bool)


def test_capabilities_when_ffmpeg_missing(client: TestClient) -> None:
    """Verify capabilities endpoint gracefully handles missing FFmpeg without crashing."""
    mock_missing_ffmpeg = FFmpegCapability(
        available=False,
        path=None,
        version=None,
        has_libass=False,
        details="FFmpeg binary not found",
    )
    with patch("app.services.media.probe.detect_ffmpeg", return_value=mock_missing_ffmpeg):
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["ffmpeg"]["available"] is False
        assert data["ffmpeg"]["path"] is None
        assert data["ffmpeg"]["has_libass"] is False


def test_capabilities_when_ffprobe_missing(client: TestClient) -> None:
    """Verify capabilities endpoint gracefully handles missing FFprobe without crashing."""
    mock_missing_ffprobe = BinaryCapability(
        available=False,
        path=None,
        version=None,
        details="FFprobe binary not found",
    )
    with patch("app.services.media.probe.detect_ffprobe", return_value=mock_missing_ffprobe):
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["ffprobe"]["available"] is False
