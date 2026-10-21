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


def test_health_reports_the_job_worker_state(client: TestClient) -> None:
    """The health endpoint must not claim "healthy" when the worker is dead.

    A stopped worker means queued jobs would never run, so reporting
    "healthy" would be a lie the studio would show.
    """
    from app.jobs.manager import job_manager

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert data["worker"] in ("running", "stopped")
    expected = "healthy" if data["worker"] == "running" else "degraded"
    assert data["status"] == expected

    # The reported state must follow the worker, not a constant.
    original = job_manager._running
    try:
        job_manager._running = False
        stopped = client.get("/api/health").json()
        assert stopped["status"] == "degraded"
        assert stopped["worker"] == "stopped"

        job_manager._running = True
        running = client.get("/api/health").json()
        assert running["status"] == "healthy"
        assert running["worker"] == "running"
    finally:
        job_manager._running = original


def test_top_level_health_alias(client: TestClient) -> None:
    """GET /health (no /api prefix) is a documented alias of /api/health."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "Laqta"
    assert "timestamp" in data
