"""Tests for GET /api/health."""

from fastapi.testclient import TestClient

from qatta import __version__


def test_get_health(client: TestClient) -> None:
    """Verify health endpoint returns status 200 and expected schema."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "Laqta"
    # The version comes from the package, so a release bump cannot break it.
    assert data["version"] == __version__
    assert "timestamp" in data


def test_top_level_health_alias(client: TestClient) -> None:
    """GET /health (no /api prefix) is a documented alias of /api/health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "Laqta"
    assert "timestamp" in data
