"""API tests for candidate review/edit (PATCH boundaries) and media file streaming.

Covers (user journey step 10, FR-04/FR-05, FR-14):
- PATCH validates against source duration and configured 30-55 s bounds.
- Edited spans are re-scored deterministically from transcript evidence.
- Edited ranges without transcript coverage are rejected with clear errors.
- Media file endpoint serves server-managed files with byte ranges for
  <video> seeking, refuses missing files and out-of-project paths.
"""

import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.repository import ProjectRepository


def make_segments() -> list[dict]:
    """30 word-timed sentences at 8 s spacing (240 s speech, 300 s media)."""
    segments: list[dict] = []
    for i in range(30):
        text = f"Fact number {i} shows {i * 3} clear steps today."
        tokens = text.split()
        start = i * 8.0
        words = [
            {"word": t, "start": start + j, "end": start + j + 1, "probability": 0.95}
            for j, t in enumerate(tokens)
        ]
        words[-1]["end"] = start + 8.0
        segments.append(
            {
                "id": f"seg_{i:04d}",
                "start": start,
                "end": start + 8.0,
                "text": text,
                "words": words,
                "avg_logprob": -0.3,
                "no_speech_prob": 0.02,
            }
        )
    return segments


@pytest.fixture
def media_id(client: TestClient) -> str:
    res_proj = client.post("/api/projects", json={"name": "Candidate Edit"})
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]
    repo = ProjectRepository()
    media = repo.create_media_asset(
        project_id=project_id,
        safe_path="/tmp/qatta_edit_test.mp4",
        original_name="edit_test.mp4",
        size_bytes=1024,
        duration_ms=300_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    repo.create_transcript(
        media_id=media.id,
        language="en",
        provider="fake",
        model="base",
        text=" ".join(s["text"] for s in make_segments()),
        segments_json=json.dumps(make_segments()),
        word_timestamps_available=True,
        timing_granularity="word",
    )
    # Generate candidates so at least one exists to edit.
    res = client.post(f"/api/media/{media.id}/candidates", json={})
    assert res.status_code == 201, res.text
    return media.id


def _first_candidate(client: TestClient, media_id: str) -> dict:
    res = client.get(f"/api/media/{media_id}/candidates")
    assert res.status_code == 200
    candidates = res.json()
    assert candidates
    return candidates[0]


def test_patch_updates_boundaries_and_rescores_deterministically(
    client: TestClient, media_id: str
) -> None:
    cand = _first_candidate(client, media_id)
    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={"start_ms": 32_000, "end_ms": 70_000},  # 38 s, inside 30-55 s
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == cand["id"]  # stable ID addresses the same record
    assert body["start_ms"] == 32_000
    assert body["end_ms"] == 70_000
    assert body["boundary_edited"] is True
    assert 30_000 <= body["duration_ms"] <= 55_000
    assert 0 <= body["cps"] <= 100
    assert any("manually edited" in r for r in body["rationale"])
    assert body["feature_scores"], "component breakdown must re-derive"
    # Boundaries bind to real transcript evidence (word ids present since
    # the transcript has word timings).
    assert body["transcript_span_ids"]


def test_patch_end_beyond_media_duration_rejected(client: TestClient, media_id: str) -> None:
    cand = _first_candidate(client, media_id)
    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={"start_ms": 0, "end_ms": 400_000},  # media is 300_000 ms
    )
    assert res.status_code == 422
    assert "exceeds the source media duration" in res.json()["detail"]


def test_patch_outside_configured_duration_bounds_rejected(
    client: TestClient, media_id: str
) -> None:
    cand = _first_candidate(client, media_id)
    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={"start_ms": 0, "end_ms": 10_000},  # 10 s < 30 s minimum
    )
    assert res.status_code == 422
    assert "outside the configured bounds" in res.json()["detail"]

    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={"start_ms": 0, "end_ms": 90_000},  # 90 s > 55 s maximum
    )
    assert res.status_code == 422
    assert "outside the configured bounds" in res.json()["detail"]


def test_patch_unknown_candidate_404(client: TestClient) -> None:
    res = client.patch(
        "/api/candidates/cand_nonexistent",
        json={"start_ms": 0, "end_ms": 40_000},
    )
    assert res.status_code == 404


def test_patch_span_without_transcript_content_rejected(client: TestClient, media_id: str) -> None:
    """Transcript spans 0-240 s; a 260-290 s window has no evidence."""
    cand = _first_candidate(client, media_id)
    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={"start_ms": 260_000, "end_ms": 290_000},
    )
    assert res.status_code == 422
    assert "no transcript content" in res.json()["detail"]


def test_patch_title_and_hook_persisted(client: TestClient, media_id: str) -> None:
    cand = _first_candidate(client, media_id)
    res = client.patch(
        f"/api/candidates/{cand['id']}",
        json={
            "start_ms": 16_000,
            "end_ms": 56_000,
            "title": "Editor reviewed cut",
            "hook": "Why this matters",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Editor reviewed cut"
    assert body["hook"] == "Why this matters"


# --------------------------------------------------------- media file endpoint


def _media_with_real_file(project_name: str) -> str:
    """Create a media asset whose file actually exists in the project dir."""
    repo = ProjectRepository()
    project = repo.create_project(project_name)
    media_dir = settings.get_project_media_dir(project.id)
    file_path = media_dir / "sample_stream.mp4"
    file_path.write_bytes(b"\x00\x01Qatta real local media fixture bytes" * 100)
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path=str(file_path),
        original_name="sample_stream.mp4",
        size_bytes=file_path.stat().st_size,
        duration_ms=300_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    return media.id


def test_media_file_full_response(client: TestClient) -> None:
    media_id = _media_with_real_file("Media File Full")
    res = client.get(f"/api/media/{media_id}/file")
    assert res.status_code == 200
    assert res.headers["accept-ranges"] == "bytes"
    assert int(res.headers["content-length"]) == len(res.content)
    assert res.content.startswith(b"\x00\x01Qatta")


def test_media_file_range_request_for_seeking(client: TestClient) -> None:
    media_id = _media_with_real_file("Media File Range")
    res = client.get(f"/api/media/{media_id}/file", headers={"Range": "bytes=8-15"})
    assert res.status_code == 206
    assert res.headers["content-range"].startswith("bytes 8-15/")
    assert len(res.content) == 8
    # Serving the middle of the file (seek preview scenario).
    res2 = client.get(f"/api/media/{media_id}/file", headers={"Range": "bytes=100-103"})
    assert res2.status_code == 206
    assert len(res2.content) == 4


def test_media_file_missing_on_disk_gives_clear_error(client: TestClient) -> None:
    repo = ProjectRepository()
    project = repo.create_project("Media File Missing")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path=str(settings.get_project_media_dir(project.id) / "gone.mp4"),
        original_name="gone.mp4",
        size_bytes=10,
        duration_ms=30_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    res = client.get(f"/api/media/{media.id}/file")
    assert res.status_code == 404
    assert "no longer exists on disk" in res.json()["detail"]


def test_media_file_outside_project_dir_blocked(client: TestClient) -> None:
    """Defense in depth: a tampered safe_path must not leak arbitrary files."""
    outside = Path("/tmp/qatta_outside_should_never_serve.mp4")
    outside.write_bytes(b"secret")
    repo = ProjectRepository()
    project = repo.create_project("Media File Blocked")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path=str(outside),
        original_name="evil.mp4",
        size_bytes=6,
        duration_ms=30_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    res = client.get(f"/api/media/{media.id}/file")
    assert res.status_code == 403


def test_media_file_arabic_name_latin1_encodable_header(client: TestClient) -> None:
    """Arabic original_name must not crash the response with a 500.

    Starlette encodes headers as latin-1; the Content-Disposition therefore
    carries an ASCII fallback plus a percent-encoded RFC 5987 `filename*=`.
    """
    repo = ProjectRepository()
    project = repo.create_project("Media File Arabic Name")
    media_dir = settings.get_project_media_dir(project.id)
    file_path = media_dir / "sample_stream.mp4"
    file_path.write_bytes(b"\x00\x01Qatta arabic-name fixture" * 10)
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path=str(file_path),
        original_name="فيديو عربي.mp4",
        size_bytes=file_path.stat().st_size,
        duration_ms=120_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    res = client.get(f"/api/media/{media.id}/file")
    assert res.status_code == 200
    header = res.headers["content-disposition"]
    # Value must be latin-1 encodable (raw header bytes round-trip).
    header.encode("latin-1")
    assert 'filename=".mp4"' in header  # ASCII fallback retains the extension
    assert "filename*=UTF-8''" in header
    assert "%D9%81" in header  # percent-encoded U+0641 (Arabic faa)
    assert res.content.startswith(b"\x00\x01Qatta")


def test_content_disposition_header_helper() -> None:
    """Unit-level: ASCII names pass through; Arabic names get RFC 5987 form."""
    from app.api.routes.media import _content_disposition_header

    assert (
        _content_disposition_header("plain name (2).mp4")
        == 'inline; filename="plain name (2).mp4"; '
        "filename*=UTF-8''plain%20name%20%282%29.mp4"
    )
    arabic = _content_disposition_header("فيديو عربي.mp4")
    arabic.encode("latin-1")
    assert arabic == (
        "inline; filename=\".mp4\"; filename*=UTF-8''" + quote("فيديو عربي.mp4", safe="")
    )
