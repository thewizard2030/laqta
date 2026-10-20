"""Pytest fixtures for Laqta backend tests."""

import os
import shutil
import tempfile

# Redirect all storage into an isolated temp directory BEFORE the app is
# imported: app.core.config.Settings reads QATTA_DATA_DIR at import time and
# pytest imports this conftest before collecting any test module. Without this
# override, integration tests wrote test projects, media rows and fixture
# files into the user's real data directory (~/.local/share/qatta).
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="qatta-test-data-")
os.environ["QATTA_DATA_DIR"] = _TEST_DATA_DIR

# Tests must be hermetic: a developer's local .env (which may hold a real
# OpenRouter key and hosted opt-ins) must never change test behaviour — and a
# test must never send a request to a hosted service. Environment variables
# take precedence over dotenv files in pydantic-settings, so the values below
# neutralise whatever a local .env contains. They are set BEFORE the app is
# imported, i.e. before the settings singleton is built.
os.environ.update(
    {
        "QATTA_LLM_PROVIDER": "openai_compatible",
        "QATTA_LLM_HOSTED_OPT_IN": "false",
        "QATTA_LLM_RANKER_ENABLED": "false",
        "QATTA_LLM_API_KEY": "",
        "QATTA_LLM_OPENROUTER_API_KEY": "",
        "QATTA_ALLOW_CLOUD_APIS": "false",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """Delete the isolated test data directory."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Synchronous test client for API endpoints."""
    with TestClient(app) as test_client:
        yield test_client
