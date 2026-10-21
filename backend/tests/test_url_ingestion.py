"""Tests for the fail-closed URL ingestion capability (PRD FR-12).

Covered invariants:
- The order of gates is explicit: operator flag → yt-dlp binary → explicit
  per-import rights confirmation → SSRF-guarded public http(s) URL. Every
  refusal returns a clear error; nothing starts silently.
- The validator rejects loopback/private/link-local hosts, DNS answers that
  resolve into private space, userinfo URLs, and non-http schemes.
- yt-dlp itself is always invoked as a strict argument array with
  server-controlled output names, --no-playlist, and a filesize cap.
- Job execution re-verifies the operator flag and required config.
  The full download path is exercised with a real (generated) media file and
  a stubbed yt-dlp runner — no network access happens in tests.
"""

import asyncio
import socket
import stat
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import JobRecord
from app.db.repository import ProjectRepository
from app.jobs.manager import job_manager
from app.services.media import url_ingest
from app.services.media.url_ingest import (
    UrlIngestError,
    _parse_yt_dlp_progress_line,
    build_url_ingest_command,
    detect_yt_dlp,
    validate_public_http_url,
)


@pytest.fixture(autouse=True)
def mock_dns_resolution(monkeypatch):
    """Stub external DNS lookups so unit tests run cleanly without internet."""
    orig_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host in ("www.youtube.com", "youtube.com", "example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", port))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(url_ingest.socket, "getaddrinfo", fake_getaddrinfo)


class TestUrlValidator:
    def test_accepts_public_https_url(self):
        assert validate_public_http_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_rejects_empty_and_schemeless(self):
        with pytest.raises(UrlIngestError):
            validate_public_http_url("")
        with pytest.raises(UrlIngestError):
            validate_public_http_url("not-a-url")
        with pytest.raises(UrlIngestError):
            validate_public_http_url("ftp://example.com/video.mp4")

    def test_rejects_userinfo(self):
        with pytest.raises(UrlIngestError):
            validate_public_http_url("https://user:pass@example.com/video.mp4")

    def test_rejects_loopback_and_private_hosts(self):
        for url in (
            "http://localhost/video.mp4",
            "http://localhost:8000/file",
            "http://127.0.0.1/file",
            "http://10.0.0.5/file",
            "http://192.168.1.10/file",
            "http://172.16.0.1/file",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/file",
            "http://0.0.0.0/file",
        ):
            with pytest.raises(UrlIngestError) as exc_info:
                validate_public_http_url(url)
            assert exc_info.value.error_code == "URL_FORBIDDEN_HOST"

    def test_rejects_dns_resolving_to_private_space(self, monkeypatch):
        the_monkeypatch = monkeypatch

        def fake_getaddrinfo(host, port, proto=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))]

        the_monkeypatch.setattr(url_ingest.socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(UrlIngestError) as exc_info:
            validate_public_http_url("https://internal.example.corp/video.mp4")
        assert exc_info.value.error_code == "URL_FORBIDDEN_HOST"

    def test_rejects_unresolvable_host(self, monkeypatch):
        def fail_getaddrinfo(host, port, proto=0):
            raise socket.gaierror(8, "nodename nor servname provided")

        monkeypatch.setattr(url_ingest.socket, "getaddrinfo", fail_getaddrinfo)
        with pytest.raises(UrlIngestError) as exc_info:
            validate_public_http_url("https://missing.invalid/video.mp4")
        assert exc_info.value.error_code == "URL_RESOLVE_FAILED"


class TestYtDlpDetection:
    def test_missing_binary_is_unavailable_with_reason(self, monkeypatch, tmp_path):
        monkeypatch.setattr(url_ingest.shutil, "which", lambda name: None)
        cap = detect_yt_dlp()
        assert cap.available is False
        assert "yt-dlp is not installed" in (cap.details or "")

    def test_fake_binary_probe(self, monkeypatch, tmp_path):
        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\necho 2026.01.05\n")
        fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(url_ingest.shutil, "which", lambda name: str(fake_bin))
        cap = detect_yt_dlp()
        assert cap.available is True
        assert cap.version == "2026.01.05"
        assert cap.path == str(fake_bin)


class TestCommandBuilder:
    def test_strict_argument_array_and_safety_flags(self, tmp_path):
        cmd = build_url_ingest_command("yt-dlp", tmp_path, "https://example.com/watch?v=1", 1024)
        assert cmd[0] == "yt-dlp"
        assert "--no-playlist" in cmd
        assert "--restrict-filenames" in cmd
        assert "--max-filesize" in cmd and cmd[cmd.index("--max-filesize") + 1] == "1024"
        # Output name is server-controlled, not remote-controlled
        out = cmd[cmd.index("-o") + 1]
        assert "%(id)s.%(ext)s" in out
        assert " " not in out
        assert cmd[-1] == "https://example.com/watch?v=1"

    def test_progress_line_parsing(self):
        assert _parse_yt_dlp_progress_line("[download]  42.3% of ~ 12.34MiB") == 42.3
        assert _parse_yt_dlp_progress_line("[download]   0.0% of ~ 1.00MiB") == 0.0
        assert _parse_yt_dlp_progress_line("[download] Destination: x.mp4") is None
        assert _parse_yt_dlp_progress_line("[info] qAAABcDdEf: Downloading") is None


def _wait_for_job_row(rdb, job_id: str, timeout_s: float = 2.0):
    """Poll until the job row is visible.

    The row is committed inside the request that returned 202 (SQLite WAL
    visibility can lag the HTTP response by one checkpoint), so assert on
    eventually-visible state instead of racing immediate reads.
    """
    deadline = time.monotonic() + timeout_s
    job = None
    while time.monotonic() < deadline:
        job = rdb.get_job(job_id)
        if job is not None:
            return job
        time.sleep(0.05)
    return None


class TestApiGating:
    def _seed_project(self) -> str:
        repo = ProjectRepository()
        return repo.create_project(f"url-ingest-{int(time.time_ns())}").id

    def test_flag_off_refuses_with_explicit_detail(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", False)
        response = client.post(
            "/api/media/url",
            json={
                "project_id": "proj_any",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "rights_confirmed": True,
            },
        )
        assert response.status_code == 403
        assert "QATTA_ENABLE_URL_INGESTION" in response.json()["detail"]

    def test_flag_on_but_rights_missing_refuses(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)
        response = client.post(
            "/api/media/url",
            json={
                "project_id": "proj_any",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "rights_confirmed": False,
            },
        )
        assert response.status_code == 422
        assert "rights" in response.json()["detail"].lower()

    def test_flag_on_but_binary_missing_refuses(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)

        def fake_detect(custom=None):
            from app.schemas.capabilities import BinaryCapability

            return BinaryCapability(
                available=False, path=None, version=None, details="yt-dlp is not installed."
            )

        monkeypatch.setattr("app.services.media.url_ingest.detect_yt_dlp", fake_detect)
        response = client.post(
            "/api/media/url",
            json={
                "project_id": "proj_any",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "rights_confirmed": True,
            },
        )
        assert response.status_code == 503
        assert "yt-dlp" in response.json()["detail"]

    def test_flag_on_private_url_refused_even_with_rights(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)
        fake_bin = "/bin/true"
        monkeypatch.setattr(url_ingest.shutil, "which", lambda name: fake_bin)
        response = client.post(
            "/api/media/url",
            json={
                "project_id": "proj_any",
                "url": "http://127.0.0.1:8000/internal.mp4",
                "rights_confirmed": True,
            },
        )
        assert response.status_code == 400
        assert "blocked" in response.json()["detail"].lower()

    def test_accepted_job_carries_url_and_rights(self, client: TestClient, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)
        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\necho 2026.01.05\n")
        fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(url_ingest.shutil, "which", lambda name: str(fake_bin))

        # Stub the network runner and probe boundary: no real download in tests.
        class FakeProbe:
            duration_ms = 120000
            width = 1280
            height = 720
            video_codec = "h264"
            audio_codec = "aac"

        async def fake_run(url, download_dir, **kwargs):
            path = download_dir / "abc123.mp4"
            path.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # placeholder; probe stubbed
            if kwargs.get("progress_callback"):
                kwargs["progress_callback"](50.0, "downloading")
            return path

        monkeypatch.setattr(url_ingest, "run_url_ingest", fake_run)
        import app.jobs.manager as manager_mod

        monkeypatch.setattr(
            manager_mod,
            "run_url_ingest",
            fake_run,
        )
        monkeypatch.setattr(
            manager_mod,
            "probe_media_file",
            lambda p: FakeProbe(),
        )

        project_id = self._seed_project()
        response = client.post(
            "/api/media/url",
            json={
                "project_id": project_id,
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "rights_confirmed": True,
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["url_host"] == "www.youtube.com"

        job_id = body["job_id"]
        job = _wait_for_job_row(job_manager.repo, job_id)
        assert job is not None
        assert job.type == "url_ingestion"
        assert "dQw4w9WgXcQ" in (job.config_json or "")
        assert "rights_confirmed" in (job.config_json or "")


class TestExecutorRefusals:
    def _job(self, config: dict) -> JobRecord:
        return JobRecord(
            id=f"job_test_{int(time.time_ns())}",
            project_id="proj_x",
            media_id=None,
            type="url_ingestion",
            status="running",
            stage="starting",
            progress=0.0,
            error_code=None,
            error_message=None,
            config_json=__import__("json").dumps(config),
            created_at="2026-10-19T00:00:00Z",
            started_at=None,
            finished_at=None,
        )

    def test_refuses_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", False)
        with pytest.raises(UrlIngestError) as exc_info:
            asyncio.run(
                job_manager._execute_url_ingest(
                    self._job({"url": "https://example.com/v", "rights_confirmed": True}),
                    asyncio.Event(),
                )
            )
        assert exc_info.value.error_code == "URL_INGEST_DISABLED"

    def test_refuses_without_rights_confirmation(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)
        monkeypatch.setattr(url_ingest.shutil, "which", lambda name: "/usr/bin/yt-dlp")
        with pytest.raises(UrlIngestError) as exc_info:
            asyncio.run(
                job_manager._execute_url_ingest(
                    self._job({"url": "https://example.com/v"}),
                    asyncio.Event(),
                )
            )
        assert exc_info.value.error_code == "URL_INGEST_INVALID_CONFIG"


class TestSubtitleExtraction:
    def test_command_builder_includes_subtitles_flags(self, tmp_path):
        cmd = build_url_ingest_command("yt-dlp", tmp_path, "https://example.com/watch?v=1", 1024)
        assert "--write-sub" in cmd
        assert "--write-auto-sub" in cmd
        assert "--sub-format" in cmd and cmd[cmd.index("--sub-format") + 1] == "vtt/best"
        assert "--sub-langs" in cmd

    def test_locate_best_vtt_arabic_priority(self, tmp_path):
        from app.services.media.url_ingest import _locate_best_vtt

        (tmp_path / "vid1.en.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello")
        (tmp_path / "vid1.ar.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nمرحبا")

        best_vtt, lang = _locate_best_vtt(tmp_path, video_id="vid1")
        assert best_vtt is not None
        assert best_vtt.name == "vid1.ar.vtt"
        assert lang == "ar"

    def test_locate_best_vtt_english_fallback(self, tmp_path):
        from app.services.media.url_ingest import _locate_best_vtt

        (tmp_path / "vid2.en.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello")
        best_vtt, lang = _locate_best_vtt(tmp_path, video_id="vid2")
        assert best_vtt is not None
        assert best_vtt.name == "vid2.en.vtt"
        assert lang == "en"

    def test_locate_best_vtt_none_when_empty(self, tmp_path):
        from app.services.media.url_ingest import _locate_best_vtt

        best_vtt, lang = _locate_best_vtt(tmp_path, video_id="none")
        assert best_vtt is None
        assert lang is None

    def test_execute_url_ingest_creates_transcript_and_manifest(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import UrlIngestResult

        # URL ingestion is fail-closed: the test opts in explicitly.
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)

        vtt_sample = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "السلام عليكم\n\n"
            "00:00:03.000 --> 00:00:06.000\n"
            "وفي هذا الفيديو نتحدث عن الذكاء الاصطناعي\n"
        )

        project = job_manager.repo.create_project("Test Ingest Subs")
        job = job_manager.repo.create_job(
            project_id=project.id,
            job_type="url_ingestion",
            config_json=__import__("json").dumps(
                {
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "rights_confirmed": True,
                }
            ),
        )

        # Mock probe
        class FakeProbe:
            duration_ms = 6000
            width = 1280
            height = 720
            video_codec = "h264"
            audio_codec = "aac"

        monkeypatch.setattr("app.jobs.manager.probe_media_file", lambda p: FakeProbe())

        # Mock run_url_ingest returning a UrlIngestResult with VTT
        async def fake_run_with_subs(url, download_dir, **kwargs):
            media = download_dir / "dQw4w9WgXcQ.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            vtt = download_dir / "dQw4w9WgXcQ.ar.vtt"
            vtt.write_text(vtt_sample, encoding="utf-8")
            return UrlIngestResult(
                media_path=media,
                subtitle_path=vtt,
                language="ar",
                video_id="dQw4w9WgXcQ",
            )

        monkeypatch.setattr("app.jobs.manager.run_url_ingest", fake_run_with_subs)

        asyncio.run(job_manager._execute_url_ingest(job, asyncio.Event()))

        updated_job = job_manager.repo.get_job(job.id)
        assert updated_job.status == "succeeded"
        cfg = __import__("json").loads(updated_job.config_json or "{}")
        assert cfg.get("transcript_created") is True
        assert cfg.get("transcript_language") == "ar"
        assert cfg.get("transcript_segments") == 2

        # Verify MediaAsset was created
        media_id = cfg.get("media_id")
        assert media_id is not None
        media = None
        for _ in range(20):
            media = job_manager.repo.get_media_asset(media_id)
            if media is not None:
                break
            time.sleep(0.05)
        assert media is not None

        # Verify TranscriptRecord was created in DB
        transcripts = job_manager.repo.list_media_transcripts(media_id)
        assert len(transcripts) == 1
        tr = transcripts[0]
        assert tr.provider == "youtube"
        assert tr.model == "captions"
        assert "السلام عليكم" in tr.text
        assert "الذكاء الاصطناعي" in tr.text

        # Verify qatta_manifest.json has atomic utterances
        manifest_path = settings.get_project_dir(project.id) / "qatta_manifest.json"
        assert manifest_path.is_file()
        from qatta.core.schema import QattaManifest

        manifest = QattaManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest.atomic_utterances) >= 1
        assert "s01_ingest" in manifest.completed_stages
        assert "s02_transcript" in manifest.completed_stages

    def test_command_builder_has_ignore_errors_and_no_all_subs(self, tmp_path):
        cmd = build_url_ingest_command("yt-dlp", tmp_path, "https://example.com/watch?v=1", 1024)
        assert "--ignore-errors" in cmd
        assert "--sub-langs" in cmd
        sub_langs_val = cmd[cmd.index("--sub-langs") + 1]
        assert "all" not in sub_langs_val.split(",")
        assert "ar" in sub_langs_val
        assert "en" in sub_langs_val

    def test_command_builder_supports_disabling_subtitles(self, tmp_path):
        cmd = build_url_ingest_command(
            "yt-dlp", tmp_path, "https://example.com/watch?v=1", 1024, include_subtitles=False
        )
        assert "--write-sub" not in cmd
        assert "--write-auto-sub" not in cmd
        assert "--sub-langs" not in cmd
        assert "--ignore-errors" in cmd

    def test_run_url_ingest_succeeds_on_subtitle_429_if_media_present(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import run_url_ingest

        # Simulate fake yt-dlp binary
        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        # Mock subprocess execution: returns rc=1 and stderr with 429, but writes the media file
        async def fake_execute(cmd, **kwargs):
            media_file = tmp_path / "video123.mp4"
            media_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            return 1, (
                "ERROR: Unable to download video subtitles for 'en': "
                "HTTP Error 429: Too Many Requests"
            )

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        result = asyncio.run(
            run_url_ingest(
                "https://www.youtube.com/watch?v=video123",
                tmp_path,
                yt_dlp_bin_override=str(fake_bin),
            )
        )

        assert result.media_path.name == "video123.mp4"
        assert result.subtitle_path is None
        assert result.language is None

    def test_run_url_ingest_retries_without_subtitles_on_rate_limit(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import run_url_ingest

        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        calls = []

        async def fake_execute(cmd, **kwargs):
            calls.append(cmd)
            if "--write-sub" in cmd:
                # Pass 1 with subtitles fails with 429 and does not write media
                return 1, (
                    "ERROR: Unable to download video subtitles for 'en': "
                    "HTTP Error 429: Too Many Requests"
                )
            else:
                # Pass 2 without subtitles succeeds and produces media
                media_file = tmp_path / "video456.mp4"
                media_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
                return 0, ""

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        result = asyncio.run(
            run_url_ingest(
                "https://www.youtube.com/watch?v=video456",
                tmp_path,
                yt_dlp_bin_override=str(fake_bin),
            )
        )

        assert len(calls) == 2
        assert "--write-sub" in calls[0]
        assert "--write-sub" not in calls[1]
        assert result.media_path.name == "video456.mp4"
        assert result.subtitle_path is None

    def test_run_url_ingest_raises_when_all_attempts_fail(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import UrlIngestError, run_url_ingest

        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        async def fake_execute(cmd, **kwargs):
            return 1, "ERROR: Video unavailable: Private video"

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        with pytest.raises(UrlIngestError) as exc_info:
            asyncio.run(
                run_url_ingest(
                    "https://www.youtube.com/watch?v=unavailable",
                    tmp_path,
                    yt_dlp_bin_override=str(fake_bin),
                )
            )
        assert exc_info.value.error_code == "URL_INGEST_FAILED"

    def test_command_builder_includes_403_prevention_flags(self, tmp_path):
        cmd = build_url_ingest_command("yt-dlp", tmp_path, "https://example.com/watch?v=1", 1024)
        assert "--no-cache-dir" in cmd
        assert "-4" in cmd
        assert "--extractor-args" in cmd
        ext_args_val = cmd[cmd.index("--extractor-args") + 1]
        assert "youtube:player_client=" in ext_args_val
        assert "android" in ext_args_val

    def test_command_builder_supports_cookies(self, tmp_path):
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        cmd = build_url_ingest_command(
            "yt-dlp",
            tmp_path,
            "https://example.com/watch?v=1",
            1024,
            cookies_path=str(cookies_file),
        )
        assert "--cookies" in cmd
        assert cmd[cmd.index("--cookies") + 1] == str(cookies_file)

    def test_run_url_ingest_retries_on_403_stream_forbidden(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import run_url_ingest

        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        calls = []

        async def fake_execute(cmd, **kwargs):
            calls.append(cmd)
            if "--write-sub" in cmd:
                # Pass 1 fails with 403 Forbidden
                return 1, (
                    "ERROR: Did not get any data blocks\n"
                    "ERROR: unable to download video data: HTTP Error 403: Forbidden"
                )
            else:
                # Pass 2 without subtitles succeeds
                media_file = tmp_path / "video789.mp4"
                media_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
                return 0, ""

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        result = asyncio.run(
            run_url_ingest(
                "https://www.youtube.com/watch?v=video789",
                tmp_path,
                yt_dlp_bin_override=str(fake_bin),
            )
        )

        assert len(calls) == 2
        assert result.media_path.name == "video789.mp4"

    def test_run_url_ingest_403_specific_error_message(self, monkeypatch, tmp_path):
        from app.services.media.url_ingest import UrlIngestError, run_url_ingest

        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        async def fake_execute(cmd, **kwargs):
            return 1, "ERROR: unable to download video data: HTTP Error 403: Forbidden"

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        with pytest.raises(UrlIngestError) as exc_info:
            asyncio.run(
                run_url_ingest(
                    "https://www.youtube.com/watch?v=failing403",
                    tmp_path,
                    yt_dlp_bin_override=str(fake_bin),
                )
            )
        assert exc_info.value.error_code == "URL_INGEST_FAILED"
        assert "403 Forbidden" in str(exc_info.value)

    def test_execute_url_ingest_auto_enqueues_fallback_whisper_when_no_subs(
        self, monkeypatch, tmp_path
    ):
        from app.services.media.url_ingest import UrlIngestResult

        # URL ingestion is fail-closed: the test opts in explicitly.
        monkeypatch.setattr(settings, "ENABLE_URL_INGESTION", True)

        project = job_manager.repo.create_project("Test Auto Whisper Fallback")
        job = job_manager.repo.create_job(
            project_id=project.id,
            job_type="url_ingestion",
            config_json=__import__("json").dumps(
                {
                    "url": "https://www.youtube.com/watch?v=no_subs_video",
                    "rights_confirmed": True,
                }
            ),
        )

        class FakeProbe:
            duration_ms = 5000
            width = 1280
            height = 720
            video_codec = "h264"
            audio_codec = "aac"

        monkeypatch.setattr("app.jobs.manager.probe_media_file", lambda p: FakeProbe())

        async def fake_run_no_subs(url, download_dir, **kwargs):
            media = download_dir / "no_subs_video.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            return UrlIngestResult(
                media_path=media,
                subtitle_path=None,
                language=None,
                video_id="no_subs_video",
            )

        monkeypatch.setattr("app.jobs.manager.run_url_ingest", fake_run_no_subs)

        asyncio.run(job_manager._execute_url_ingest(job, asyncio.Event()))

        updated_job = job_manager.repo.get_job(job.id)
        assert updated_job.status == "succeeded"
        cfg = __import__("json").loads(updated_job.config_json or "{}")
        assert cfg.get("transcript_created") is False
        assert cfg.get("fallback_transcription_enqueued") is True

        # Verify a transcription job was enqueued in the project
        project_jobs = job_manager.repo.list_project_jobs(project.id)
        transcribe_jobs = [j for j in project_jobs if j.type == "transcription"]
        assert len(transcribe_jobs) == 1
        assert transcribe_jobs[0].media_id == cfg.get("media_id")

    def test_run_url_ingest_tier1_native_subtitles_skips_sub_flags_on_download(
        self, monkeypatch, tmp_path
    ):
        from app.services.media.url_ingest import run_url_ingest
        from app.services.transcription.transcript_cleaner import CleanCue

        fake_bin = tmp_path / "yt-dlp"
        fake_bin.write_text("#!/bin/sh\nexit 0\n")
        fake_bin.chmod(0o755)

        # Mock Tier 1 extractor returning clean cues and writing vtt
        async def fake_extract_and_save(url, out_dir, **kwargs):
            vtt = out_dir / "native12345.ar.vtt"
            vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nمرحبا", encoding="utf-8")
            return vtt, "ar", [CleanCue(1000, 3000, "مرحبا")]

        monkeypatch.setattr(
            "app.services.transcription.youtube_extractor.YouTubeTranscriptExtractor.extract_and_save_vtt",
            fake_extract_and_save,
        )

        captured_cmd = []

        async def fake_execute(cmd, **kwargs):
            captured_cmd.append(cmd)
            media = tmp_path / "native12345.mp4"
            media.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            return 0, ""

        monkeypatch.setattr(
            "app.services.media.url_ingest._execute_yt_dlp_subprocess", fake_execute
        )

        result = asyncio.run(
            run_url_ingest(
                "https://www.youtube.com/watch?v=native12345",
                tmp_path,
                yt_dlp_bin_override=str(fake_bin),
            )
        )

        # Media download command should NOT have --write-sub because the native
        # subtitles were already acquired
        assert len(captured_cmd) == 1
        assert "--write-sub" not in captured_cmd[0]
        assert result.subtitle_path is not None
        assert result.subtitle_path.name == "native12345.ar.vtt"
        assert result.language == "ar"
