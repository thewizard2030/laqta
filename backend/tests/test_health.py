"""Tests for GET /api/health."""

from fastapi.testclient import TestClient


def test_get_health(client: TestClient) -> None:
    """Verify health endpoint returns status 200 and expected schema."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "Laqta"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


def test_top_level_health_alias(client: TestClient) -> None:
    """GET /health (no /api prefix) is a documented alias of /api/health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "Laqta"
    assert "timestamp" in data
