"""Tests for the FFmpeg render pipeline (PRD §5 FR-09, §11 Gate D).

Unit tests cover command construction, path escaping, crop math, and output
validation failures. Integration tests exercise the full API render flow on
a tiny programmatically generated fixture and are skipped with an explicit
reason when FFmpeg/libass/x264/AAC are unavailable (no silent skips).
"""

import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.core.config import settings

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
from app.db.repository import CandidateRepository, ProjectRepository
from app.services.rendering.render import (
    QUALITY_PRESETS,
    RenderError,
    build_render_command,
    compute_center_crop,
    escape_filter_path,
    probe_render_environment,
    probe_render_output,
    run_render_process,
)

FFMPEG_BIN = "/usr/bin/ffmpeg"


def _environment_ready(report) -> bool:
    return (
        bool(report["ffmpeg_available"])
        and bool(report["libass_available"])
        and bool(report["h264_encoder_available"])
        and bool(report["aac_encoder_available"])
    )


@pytest.fixture(scope="module")
def env_report() -> dict:
    return probe_render_environment()


@pytest.fixture(scope="module")
def render_ready(env_report: dict) -> bool:
    return _environment_ready(env_report)


def _skip_reason(report: dict) -> str:
    parts = []
    if not report["ffmpeg_available"]:
        parts.append("ffmpeg binary unavailable")
    if not report["libass_available"]:
        parts.append("libass subtitles filter unavailable in this ffmpeg build")
    if not report["h264_encoder_available"]:
        parts.append("libx264 encoder unavailable")
    if not report["aac_encoder_available"]:
        parts.append("aac encoder unavailable")
    return "Integration render skipped: " + " + ".join(parts)


# Tests take the session-scoped `client` fixture from conftest.py so that all
# modules share one TestClient (one asyncio loop) over the same app instance
# and the single JobManager singleton.


# ---------------------------------------------------------------------------
# Unit: command construction (pure, no subprocess)
# ---------------------------------------------------------------------------


def test_build_command_center_crop_uses_arg_arrays(tmp_path: Path) -> None:
    cmd = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="center_crop",
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=True,
        caption_path="/proj/captions/c1.ass",
        caption_format="ass",
        start_ms=1000,
        duration_ms=42000,
    )
    assert cmd[0] == FFMPEG_BIN
    assert "-y" in cmd
    assert "-ss" in cmd and "1.000" in cmd
    assert "-t" in cmd and "42.000" in cmd
    assert "-i" in cmd and "/media/src.mp4" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    # 1920x1080 -> centered 9:16 crop (607.5 floored to an even 606): crop=606:1080
    assert "crop=w=606:h=1080" in vf
    assert "scale=1080:1920:flags=lanczos" in vf
    assert "setsar=1" in vf
    assert "ass='/proj/captions/c1.ass'" in vf
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-crf") + 1] == "20"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-movflags" in cmd
    assert str(tmp_path / "out.mp4") == cmd[-1]
    # Defensive: never build shell strings.
    assert "sh -c" not in " ".join(cmd)


def test_build_command_bitrate_encoder_skips_crf_preset(tmp_path: Path) -> None:
    """Fedora's FFmpeg ships libopenh264, which does not accept CRF/-preset."""
    cmd = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="center_crop",
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=True,
        video_encoder="libopenh264",
    )
    assert cmd[cmd.index("-c:v") + 1] == "libopenh264"
    assert "-crf" not in cmd
    assert "-preset" not in cmd
    assert cmd[cmd.index("-b:v") + 1] == "5000000"


def test_crop_math_landscape_and_portrait() -> None:
    # Landscape 16:9 source -> width becomes height * 9/16
    # 607.5 is floored to an even 606 px (H.264 requires even dimensions)
    assert compute_center_crop(1920, 1080, 1080, 1920) == (606, 1080)
    # Already-portrait source keeps full frame
    assert compute_center_crop(1080, 1920, 1080, 1920) == (1080, 1920)
    with pytest.raises(RenderError):
        compute_center_crop(0, 100, 1080, 1920)


def test_build_command_blurred_background_filtergraph(tmp_path: Path) -> None:
    cmd = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="blurred_background",
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=True,
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "split=2" in graph
    assert "boxblur=" in graph
    assert "overlay=x=(W-w)/2:y=(H-h)/2" in graph
    assert "[vout]" in graph
    assert cmd[cmd.index("-map") + 1] == "[vout]"


def test_build_command_skips_audio_for_silent_source(tmp_path: Path) -> None:
    cmd = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="center_crop",
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=False,
    )
    assert "-an" in cmd
    assert "-c:a" not in cmd


def test_cpu_friendly_preset_is_lower_quality(tmp_path: Path) -> None:
    cmd = build_render_command(
        FFMPEG_BIN,
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout="center_crop",
        quality="cpu_friendly",
        src_width=1920,
        src_height=1080,
        has_audio=True,
    )
    preset = QUALITY_PRESETS["cpu_friendly"]
    assert f"scale={preset['width']}:{preset['height']}" in cmd[cmd.index("-vf") + 1]
    assert cmd[cmd.index("-crf") + 1] == "26"
    assert cmd[cmd.index("-preset") + 1] == "ultrafast"


def test_invalid_layout_or_quality_rejected(tmp_path: Path) -> None:
    with pytest.raises(RenderError):
        build_render_command(
            FFMPEG_BIN,
            Path("/media/src.mp4"),
            tmp_path / "out.mp4",
            layout="split_screen",  # intentionally deferred (FR-07)
            quality="high",
            src_width=1920,
            src_height=1080,
            has_audio=True,
        )
    with pytest.raises(RenderError):
        build_render_command(
            FFMPEG_BIN,
            Path("/media/src.mp4"),
            tmp_path / "out.mp4",
            layout="center_crop",
            quality="ultra_premium",
            src_width=1920,
            src_height=1080,
            has_audio=True,
        )


def test_subtitle_path_escaping_consistency() -> None:
    assert "\\:" in escape_filter_path("/tmp/a:b.ass")
    assert escape_filter_path("plain.ass") == "plain.ass"


# ---------------------------------------------------------------------------
# Unit: output validation failure paths (no ffmpeg subprocess required)
# ---------------------------------------------------------------------------


def test_output_probe_missing_and_empty(tmp_path: Path) -> None:
    with pytest.raises(RenderError) as exc:
        probe_render_output(
            "/usr/bin/ffprobe",
            tmp_path / "missing.mp4",
            expected_width=1080,
            expected_height=1920,
            expected_duration_ms=2000,
        )
    assert exc.value.error_code == "OUTPUT_MISSING"

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(RenderError) as exc:
        probe_render_output(
            "/usr/bin/ffprobe",
            empty,
            expected_width=1080,
            expected_height=1920,
            expected_duration_ms=2000,
        )
    assert exc.value.error_code == "OUTPUT_EMPTY"


def test_run_render_rejects_nonexistent_binary(tmp_path: Path) -> None:
    argv = ["/definitely/not/ffmpeg", "-y", str(tmp_path / "x.mp4")]
    with pytest.raises(RenderError) as exc:
        import asyncio

        asyncio.run(run_render_process(argv, tmp_path / "x.mp4"))
    assert exc.value.error_code == "FFMPEG_NOT_FOUND"


# ---------------------------------------------------------------------------
# Unit: honest environment probing
# ---------------------------------------------------------------------------


def test_environment_probe_reports_missing_ffmpeg() -> None:
    report = probe_render_environment(custom_ffmpeg="/definitely/not/ffmpeg")
    assert report["ffmpeg_available"] is False
    assert report["install_hint"]
    assert "ffmpeg" in report["install_hint"].lower()


def test_environment_probe_detects_content_encoder(env_report: dict) -> None:
    """The probe must report encoder presence honestly (never fabricate)."""
    if not env_report["ffmpeg_available"]:
        pytest.skip("ffmpeg unavailable on this host; nothing to detect")
    # Fedora builds ship libopenh264 (no libx264); either software encoder is valid.
    assert env_report["h264_encoder"] in ("libx264", "libopenh264")
    assert env_report["h264_encoder_available"] is True
    assert env_report["aac_encoder"] == "aac"
    assert env_report["libass_available"] is True


# ---------------------------------------------------------------------------
# Integration: real render of a programmatically generated fixture
# ---------------------------------------------------------------------------


def _generate_fixture(tmp_path: Path, name: str = "fixture.mp4") -> Path:
    """Generate a tiny 2 s 640x360 MP4 (synthetic test pattern + sine tone).

    Programmatically generated; no private or committed media is used. Uses
    the first available software H.264 encoder reported by the environment
    probe (x264 or Fedora's libopenh264).
    """
    env = probe_render_environment()
    encoder = env["h264_encoder"]
    if not env["ffmpeg_available"] or not encoder:
        pytest.skip(
            "ffmpeg or an H.264 software encoder is unavailable; "
            "integration fixture cannot be created"
        )

    fixture = tmp_path / name
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=640x360:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:v",
        encoder,
        "-b:v",
        "2000000",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        str(fixture),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    return fixture


def _create_project_media_transcript_candidate(tmp_path: Path):
    """Create persisted records exercising the real repository layer."""
    repo = ProjectRepository()
    candidates_repo = CandidateRepository()
    project = repo.create_project(f"render-test-{int(time.time())}")
    fixture = _generate_fixture(tmp_path)
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path=str(fixture),
        original_name=fixture.name,
        size_bytes=fixture.stat().st_size,
        duration_ms=2000,
        width=640,
        height=360,
        video_codec="h264",
        audio_codec="aac",
    )
    segments = [
        {
            "id": "seg_1",
            "start": 0.1,
            "end": 1.0,
            "text": "الدرس الأول عن النحو",
            "words": [
                {"word": "الدرس", "start": 0.1, "end": 0.4, "probability": 0.9},
                {"word": "الأول", "start": 0.4, "end": 0.7, "probability": 0.9},
                {"word": "عن", "start": 0.7, "end": 0.85, "probability": 0.9},
                {"word": "النحو", "start": 0.85, "end": 1.0, "probability": 0.9},
            ],
        },
        {
            "id": "seg_2",
            "start": 1.1,
            "end": 1.9,
            "text": "مع الاستاذ Ahmad من Cairo",
            "words": [
                {"word": "مع", "start": 1.1, "end": 1.25, "probability": 0.9},
                {"word": "الاستاذ", "start": 1.25, "end": 1.5, "probability": 0.9},
                {"word": "Ahmad", "start": 1.5, "end": 1.7, "probability": 0.9},
                {"word": "من", "start": 1.7, "end": 1.8, "probability": 0.9},
                {"word": "Cairo", "start": 1.8, "end": 1.9, "probability": 0.9},
            ],
        },
    ]
    transcript = repo.create_transcript(
        media_id=media.id,
        language="ar",
        provider="test-fixture",
        model="synthetic",
        text="الدرس الأول عن النحو مع الاستاذ Ahmad من Cairo",
        segments_json=json.dumps(segments),
        word_timestamps_available=True,
        timing_granularity="word",
    )
    candidate_record = candidates_repo.put_candidate(
        candidate_id=f"cand_{media.id}",
        media_id=media.id,
        transcript_id=transcript.id,
        start_ms=100,
        end_ms=1900,
        transcript_span_ids_json=json.dumps(["seg_1", "seg_2"]),
        title="درس النحو",
        hook=None,
        rationale_json=json.dumps([]),
        feature_scores_json=json.dumps([]),
        cps=50.0,
        status="suggested",
        created_at=transcript.created_at,
    )
    return project, media, candidate_record


def _post_render(client: TestClient, candidate_id: str, **overrides) -> str:
    payload: dict = {}
    payload.update(overrides)
    resp = client.post(f"/api/candidates/{candidate_id}/render-jobs", json=payload)
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def _await_terminal(client: TestClient, job_id: str, timeout_s: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.25)
    raise TimeoutError(f"Job {job_id} did not reach a terminal state in {timeout_s}s")


def test_full_render_job_pipeline_end_to_end(
    client: "TestClient", tmp_path: Path, env_report: dict, render_ready: bool
):
    """Gate D: one candidate exports as verified 1080x1920 MP4."""
    if not render_ready:
        pytest.skip(_skip_reason(env_report))

    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    job_id = _post_render(client, candidate.id)

    job = _await_terminal(client, job_id)
    assert job["status"] == "succeeded", job

    cfg = json.loads(job["config_json"])
    output_path = Path(cfg["output_path"])
    assert output_path.is_file()
    assert output_path.suffix == ".mp4"
    # Output validation passed inside the job; verify key probe facts recorded.
    assert cfg["probe"]["width"] == 1080
    assert cfg["probe"]["height"] == 1920
    assert cfg["probe"]["video_codec"] == "h264"
    assert cfg["probe"]["audio_codec"] == "aac"

    # Per-render config/log persisted next to the render (FR-09).
    diag_dir = settings.get_project_renders_dir(project.id) / "logs"
    assert (diag_dir / f"{job_id}.config.json").is_file()
    assert (diag_dir / f"{job_id}.log").is_file()

    # A validated rendered-clip record exists via the artifacts endpoint.
    artifacts = client.get(f"/api/candidates/{candidate.id}/artifacts").json()
    mp4s = [a for a in artifacts["rendered_clips"] if a["kind"] == "mp4"]
    assert mp4s
    assert all(a["size_bytes"] > 0 for a in mp4s)

    # Safe overwrite (FR-09): a second render must fail without explicit opt-in.
    job2_id = _post_render(client, candidate.id)
    job2 = _await_terminal(client, job2_id)
    assert job2["status"] == "failed", job2
    assert job2["error_code"] == "OUTPUT_EXISTS"

    # With explicit overwrite the render succeeds again.
    job3_id = _post_render(client, candidate.id, overwrite=True)
    job3 = _await_terminal(client, job3_id)
    assert job3["status"] == "succeeded", job3


def test_captions_endpoint_generates_srt_and_ass(client: TestClient, tmp_path: Path):
    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    payload = {
        "style": {
            "font_name": "Noto Sans Arabic",
            "font_size": 64,
            "max_chars_per_line": 30,
            "max_lines": 2,
            "karaoke": True,
        },
        "formats": ["srt", "ass"],
    }
    resp = client.post(f"/api/candidates/{candidate.id}/captions", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    srt_path, ass_path = body["srt_path"], body["ass_path"]
    assert Path(srt_path).is_file() and Path(ass_path).is_file()
    srt = Path(srt_path).read_text(encoding="utf-8")
    assert "-->" in srt and "الدرس" in srt
    # Word timestamps are reliable here, so word granularity is reported;
    # karaoke is opt-in only.
    assert body["timing_granularity"] == "word"
    assert body["karaoke_used"] is True
    ass = Path(ass_path).read_text(encoding="utf-8")
    assert "PlayResX: 1080" in ass
    assert "{\\k" in ass

    artifacts = client.get(f"/api/candidates/{candidate.id}/artifacts").json()
    kinds = {a["kind"] for a in artifacts["captions"]}
    assert {"srt", "ass"}.issubset(kinds)


def test_render_job_clear_error_without_ffmpeg(
    client: "TestClient", tmp_path: Path, env_report: dict
):
    """When ffmpeg is unavailable the render job must fail with a diagnostic."""
    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    job_id = _post_render(client, candidate.id)
    job = _await_terminal(client, job_id)
    if env_report["ffmpeg_available"]:
        # Environment actually has ffmpeg, so this test only asserts happy
        # behavior reaches terminal state; skip the strict check.
        pytest.skip("ffmpeg is available on this host; failure path not applicable")
    assert job["status"] == "failed"
    assert "ffmpeg" in (job["error_message"] or "").lower()


def test_serve_candidate_render_file_returns_video(client: "TestClient", tmp_path: Path):
    project, media, candidate = _create_project_media_transcript_candidate(tmp_path)
    # 404 when no render exists
    res = client.get(f"/api/candidates/{candidate.id}/render-file")
    assert res.status_code == 404

    # Create mock rendered file in the project renders dir
    renders_dir = settings.get_project_dir(project.id) / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    out_file = renders_dir / f"{candidate.id}.mp4"
    out_file.write_bytes(b"dummy mp4 content bytes")

    res = client.get(f"/api/candidates/{candidate.id}/render-file")
    assert res.status_code == 200
    assert res.content == b"dummy mp4 content bytes"
    assert res.headers["content-type"] == "video/mp4"
    assert "inline" in res.headers["content-disposition"]
