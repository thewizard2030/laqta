"""Tests for the release mode: the API serves the built studio.

With a built frontend the whole application lives on one address
(`http://127.0.0.1:8000`): the root opens the studio, deep links fall back
to index.html, the API keeps working, and nothing outside the build
directory is ever served.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings


def _fake_dist(tmp_path: Path) -> Path:
    """A minimal build directory: index.html, a hashed asset, a file."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Laqta</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('laqta')", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    return dist


def test_without_a_build_the_root_is_the_api_status(client: TestClient) -> None:
    """Without a built studio the root stays a helpful JSON status."""
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "Laqta"
    assert payload["local_only"] is True


def test_unknown_paths_explain_how_to_build_the_studio(client: TestClient) -> None:
    response = client.get("/not-a-real-page")

    assert response.status_code == 404
    assert "npm run build" in response.json()["hint"]


def test_release_mode_serves_the_studio(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    """With a build directory the root opens the studio itself."""
    dist = _fake_dist(tmp_path)
    monkeypatch.setattr(settings, "FRONTEND_DIST", str(dist))

    root = client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert "<title>Laqta</title>" in root.text

    # A hashed asset is served as itself.
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text

    # A deep link falls back to the SPA entry point.
    deep = client.get("/projects/anything")
    assert deep.status_code == 200
    assert "<title>Laqta</title>" in deep.text


def test_release_mode_keeps_the_api_working(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """The catch-all must never shadow the API routes."""
    dist = _fake_dist(tmp_path)
    monkeypatch.setattr(settings, "FRONTEND_DIST", str(dist))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["app"] == "Laqta"

    capabilities = client.get("/api/capabilities")
    assert capabilities.status_code == 200


def test_release_mode_never_serves_files_outside_the_build(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    """A traversal attempt must not escape the build directory."""
    dist = _fake_dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    monkeypatch.setattr(settings, "FRONTEND_DIST", str(dist))

    response = client.get("/../secret.txt")

    assert "top secret" not in response.text
    assert response.status_code == 200  # the SPA entry point, not the secret
