"""Pytest bootstrap for the core pipeline test suite.

Tests must be hermetic: a developer's local ``.env`` (which may hold a real
OpenRouter key and hosted opt-ins) must never change test behaviour, and a
test must never reach a hosted service.

Environment variables take precedence over dotenv files in pydantic-settings,
so the values below neutralise whatever a local ``.env`` may contain. They
are set BEFORE ``qatta.core.config`` is imported, i.e. before the settings
singleton is built.
"""

import os
import shutil
import tempfile

_HERMETIC_ENV = {
    "QATTA_LLM_PROVIDER": "ollama",
    "QATTA_ALLOW_CLOUD_APIS": "false",
    "QATTA_LLM_API_KEY": "",
    "QATTA_LLM_OPENROUTER_API_KEY": "",
    "QATTA_LLM_HOSTED_OPT_IN": "false",
    "QATTA_LLM_RANKER_ENABLED": "false",
}
os.environ.update(_HERMETIC_ENV)

# Redirect the storage directory into an isolated temp directory BEFORE the
# core config is imported: `qatta.core.config` reads QATTA_DATA_DIR at import
# time. Without this, the integration tests in this suite created real
# projects, manifests and media rows inside the developer's own data
# directory (~/.local/share/qatta).
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="laqta-core-test-data-")
os.environ["QATTA_DATA_DIR"] = _TEST_DATA_DIR


def pytest_sessionfinish(session, exitstatus):
    """Delete the isolated test data directory."""
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
