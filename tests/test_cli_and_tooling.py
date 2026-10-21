"""Tests for the `laqta` command line interface and the release tooling.

The CLI is the first thing a new user runs, so it must be honest: it reports
what is actually installed, it never fails because an optional component is
missing, and it exits non-zero only for a genuinely broken machine.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qatta.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
runner = CliRunner()


def test_version_command_prints_the_package_version() -> None:
    from qatta import __version__

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_flag_on_the_root_command() -> None:
    from qatta import __version__

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_doctor_reports_the_machine_without_crashing() -> None:
    result = runner.invoke(app, ["doctor"])

    # The doctor must always produce a report. It only fails when a required
    # component (Python/FFmpeg/FFprobe/data dir) is missing — in CI, ffmpeg
    # may be absent, so the exit code is allowed to be 1, but never a crash.
    assert result.exit_code in (0, 1)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Laqta doctor" in result.stdout
    assert "Python" in result.stdout
    assert "FFmpeg" in result.stdout


def test_doctor_never_reports_a_false_positive_for_missing_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing tool is reported as missing, never as available."""
    monkeypatch.setattr("qatta.cli._which", lambda name: None)

    result = runner.invoke(app, ["doctor"])

    assert "not found in PATH" in result.stdout
    # The tool must not be advertised as present anywhere in the report.
    assert "FFmpeg          installed" not in result.stdout


def test_models_command_handles_an_empty_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))

    result = runner.invoke(app, ["models"])

    assert result.exit_code == 0
    assert "No models downloaded yet" in result.stdout


def test_serve_refuses_to_start_without_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("uvicorn is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 1
    assert "uvicorn is not installed" in result.stdout


# --- Release tooling --------------------------------------------------------


def test_version_checker_passes_on_a_clean_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_version.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All manifests agree" in result.stdout


def test_requirements_profiles_are_consistent() -> None:
    """Every profile must exist and chain from the base requirements file."""
    backend = REPO_ROOT / "backend"
    base = (backend / "requirements.txt").read_text(encoding="utf-8")

    for name in ("requirements-asr.txt", "requirements-all.txt", "requirements-dev.txt"):
        assert (backend / name).is_file(), f"{name} is missing"

    # The heavier profiles include the lighter ones.
    assert "-r requirements.txt" in (backend / "requirements-asr.txt").read_text(encoding="utf-8")
    assert "-r requirements-asr.txt" in (backend / "requirements-all.txt").read_text(
        encoding="utf-8"
    )
    assert "-r requirements.txt" in (backend / "requirements-dev.txt").read_text(encoding="utf-8")

    # The base profile must not drag in the heavy optional stacks.
    for forbidden in ("faster-whisper", "yt-dlp", "librosa", "mediapipe", "scenedetect"):
        assert forbidden not in base, f"{forbidden} must not be a base dependency"


def test_lock_file_pins_every_package_with_a_hash() -> None:
    lock = (REPO_ROOT / "backend" / "requirements-lock.txt").read_text(encoding="utf-8")

    packages = re.findall(r"^([A-Za-z0-9._-]+)==(\S+)", lock, re.MULTILINE)
    assert packages, "the lock file is empty"

    for name, version in packages:
        assert version, f"unpinned entry: {name}"
    # Every pinned package must carry at least one hash.
    assert lock.count("--hash=sha256:") >= len(packages)
    assert "fastapi==" in lock
    assert "faster-whisper==" in lock


# --- the CLI's local probes --------------------------------------------------


def test_http_probe_returns_none_for_a_closed_port() -> None:
    """A port that nothing listens on must report "not running"."""
    from qatta.cli import _probe_http

    # Port 1 is reserved and never has a listener.
    assert _probe_http("http://127.0.0.1:1/api/health", timeout=0.5) is None


def test_http_probe_reads_a_local_response() -> None:
    """The probe must return the body of a reachable local server."""
    import http.server
    import threading

    from qatta.cli import _probe_http

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            body = b'{"app": "Laqta", "version": "0.1.1"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        payload = _probe_http(f"http://127.0.0.1:{port}/api/health", timeout=2)
    finally:
        server.shutdown()
        server.server_close()

    assert payload is not None
    assert "Laqta" in payload


def test_doctor_reports_the_running_api_and_studio(monkeypatch) -> None:
    """The doctor must say whether the services are up, not only what is installed."""
    from typer.testing import CliRunner

    from qatta.cli import app

    monkeypatch.setattr("qatta.cli._probe_http", lambda url, timeout=1.5: "{}")
    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code in (0, 1)
    assert "running on :8000" in result.stdout
    assert "running on :5173" in result.stdout


def test_doctor_reports_a_stopped_api(monkeypatch) -> None:
    from typer.testing import CliRunner

    from qatta.cli import app

    monkeypatch.setattr("qatta.cli._probe_http", lambda url, timeout=1.5: None)
    result = CliRunner().invoke(app, ["doctor"])

    assert "not running on :8000" in result.stdout
    assert "not running on :5173" in result.stdout


def test_studio_refuses_to_start_without_a_backend_environment(monkeypatch, tmp_path) -> None:
    """`laqta studio` must fail clearly instead of half-starting."""
    from typer.testing import CliRunner

    from qatta import cli

    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    result = CliRunner().invoke(cli.app, ["studio"])

    assert result.exit_code == 1
    assert "setup.sh" in result.stdout
