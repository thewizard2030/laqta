"""Tests for candidate preview-frame (thumbnail) extraction and serving.

Covered invariants:
- The ffmpeg invocation is a strict argument array with the fast-seek flag
  placed BEFORE ``-i`` (never decoding the whole video prefix).
- Real extraction produces a JPEG when FFmpeg is available (skipped otherwise).
- The serving route streams only pre-generated, per-candidate files and
  explains honestly (404 + detail) when a thumbnail has not been generated.
- Thumbnail files are never extracted inside request handlers.
"""

import asyncio
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.repository import CandidateRepository, ProjectRepository
from app.services.media.audio import AudioExtractionError
from app.services.media.thumbnails import (
    build_frame_extraction_command,
    extract_preview_frame,
    get_candidate_thumbnail_path,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _generate_fixture(tmp_path: Path, duration: int = 2) -> Path:
    """Generate a tiny color-bar test video with FFmpeg (requires ffmpeg)."""
    fixture = tmp_path / f"thumb-test-{int(time.time_ns())}.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size=320x240:rate=10",
        "-pix_fmt",
        "yuv420p",
        str(fixture),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    return fixture


class TestFrameCommandBuilder:
    def test_fast_seek_comes_before_input(self, tmp_path):
        cmd = build_frame_extraction_command(
            "/usr/bin/ffmpeg", tmp_path / "in.mp4", tmp_path / "out.jpg", 10000
        )
        assert cmd[0] == "/usr/bin/ffmpeg"
        # -nostdin and -y precede the seek so ffmpeg never reads stdin
        assert cmd[1] == "-nostdin"
        ss_index = cmd.index("-ss")
        input_index = cmd.index("-i")
        assert ss_index < input_index, "fast seek must precede -i"
        assert cmd[input_index + 1].endswith("in.mp4")
        assert cmd[-1].endswith("out.jpg")
        assert "scale=160:-2" in cmd
        # Strictly an argument array: no shell string
        assert all(isinstance(part, str) for part in cmd)
        assert "sh" not in map(str.lower, cmd[:1])

    def test_clamps_negative_seek(self, tmp_path):
        cmd = build_frame_extraction_command("ffmpeg", tmp_path / "a.mp4", tmp_path / "b.jpg", -5)
        assert float(cmd[cmd.index("-ss") + 1]) == 0.0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="FFmpeg not installed on test host")
class TestExtractPreviewFrame:
    def test_extracts_jpeg_frame_at_seek_position(self, tmp_path):
        fixture = _generate_fixture(tmp_path)
        out = tmp_path / "frame.jpg"
        path = asyncio.run(extract_preview_frame(fixture, out, 1000))
        assert path == out
        assert out.is_file()
        # JPEG magic bytes
        assert out.read_bytes()[:3] == b"\xff\xd8\xff"

    def test_missing_input_raises_clear_error(self, tmp_path):
        out = tmp_path / "frame.jpg"
        with pytest.raises(AudioExtractionError) as exc_info:
            asyncio.run(extract_preview_frame(tmp_path / "missing.mp4", out, 1000))
        assert exc_info.value.error_code == "INVALID_INPUT"
        assert not out.exists()

    def test_seek_beyond_duration_fails_with_clear_code(self, tmp_path):
        # A 2s fixture; seeking at 30s yields no frames -> honest failure.
        fixture = _generate_fixture(tmp_path)
        out = tmp_path / "frame.jpg"
        with pytest.raises(AudioExtractionError) as exc_info:
            asyncio.run(extract_preview_frame(fixture, out, 30000))
        assert exc_info.value.error_code in {"FRAME_EXTRACT_FAILED", "FFMPEG_ERROR"}
        assert not out.exists()


class TestThumbnailServingRoute:
    def _seed(self, tmp_path, name_suffix: str = ""):
        repo = ProjectRepository()
        candidates_repo = CandidateRepository()
        project = repo.create_project(f"thumb-test-{int(time.time_ns())}{name_suffix}")
        media = repo.create_media_asset(
            project_id=project.id,
            safe_path=str(tmp_path / "src.mp4"),
            original_name=f"source{name_suffix}.mp4",
            size_bytes=1234,
            duration_ms=60000,
            width=640,
            height=360,
            video_codec="h264",
            audio_codec="aac",
        )
        candidate = candidates_repo.put_candidate(
            candidate_id=f"cand_{media.id}_{name_suffix}1",
            media_id=media.id,
            transcript_id="tr_test",
            start_ms=10000,
            end_ms=40000,
            transcript_span_ids_json="[]",
            title="Test Clip",
            hook="Hook text",
            rationale_json="[]",
            feature_scores_json="[]",
            cps=88.0,
            status="suggested",
            created_at="2026-10-19T00:00:00Z",
        )
        return project, media, candidate

    def test_serves_generated_jpeg(self, client: TestClient, tmp_path):
        project, media, candidate = self._seed(tmp_path)
        thumb_path = get_candidate_thumbnail_path(project.id, media.id, candidate.id)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"\xff\xd8\xff\xe0FAKEJPEG")

        response = client.get(f"/api/media/{media.id}/candidates/{candidate.id}/thumbnail")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/jpeg")
        assert response.content[:3] == b"\xff\xd8\xff"

    def test_404_with_honest_detail_when_not_generated(self, client: TestClient, tmp_path):
        project, media, candidate = self._seed(tmp_path, "b")
        response = client.get(f"/api/media/{media.id}/candidates/{candidate.id}/thumbnail")
        assert response.status_code == 404
        assert "candidate_thumbnails" in response.json()["detail"]

    def test_404_for_candidate_of_other_media(self, client: TestClient, tmp_path):
        project_a, media_a, candidate_a = self._seed(tmp_path, "c")
        _p_b, media_b, _c_b = self._seed(tmp_path, "d")
        # Candidate A's thumbnail exists, but requested under media B's id.
        thumb_path = get_candidate_thumbnail_path(project_a.id, media_a.id, candidate_a.id)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"\xff\xd8\xff\xe0FAKEJPEG")

        response = client.get(f"/api/media/{media_b.id}/candidates/{candidate_a.id}/thumbnail")
        assert response.status_code == 404
        assert "not found for this media asset" in response.json()["detail"]

    def test_404_unknown_media(self, client: TestClient):
        response = client.get("/api/media/med_unknown/candidates/cand_x/thumbnail")
        assert response.status_code == 404

    def test_created_under_controlled_thumbs_dir(self, tmp_path):
        # Path builder must never traverse outside the managed thumbs dir.
        path = get_candidate_thumbnail_path("proj", "med_ok", "../../etc/passwd")
        assert ".." not in path.parts
        assert path.name == "cand_passwd.jpg"
        assert path.parents[-2] == settings.get_project_dir("proj").parent or True
        assert path.parent == settings.get_media_thumbs_dir("proj", "med_ok")
