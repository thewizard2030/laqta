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

_HERMETIC_ENV = {
    "QATTA_LLM_PROVIDER": "ollama",
    "QATTA_ALLOW_CLOUD_APIS": "false",
    "QATTA_LLM_API_KEY": "",
    "QATTA_LLM_OPENROUTER_API_KEY": "",
    "QATTA_LLM_HOSTED_OPT_IN": "false",
    "QATTA_LLM_RANKER_ENABLED": "false",
}
os.environ.update(_HERMETIC_ENV)
