"""Tests for the backend OpenRouter adapter and its capability reporting.

Mocked only: no network, no model, no real key.
"""

from app.core.config import Settings
from app.providers.llm.openrouter import (
    DEFAULT_MODEL,
    FREE_MODEL_IDS,
    OpenRouterProvider,
)
from app.services.media.probe import detect_llm_capabilities


def _settings(**overrides) -> Settings:
    values = {
        "LLM_PROVIDER": "openrouter",
        "LLM_OPENROUTER_API_KEY": "sk-or-test",
        "LLM_OPENROUTER_MODEL": DEFAULT_MODEL,
        "LLM_OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_HOSTED_OPT_IN": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_provider_name_and_headers() -> None:
    provider = OpenRouterProvider(
        api_key="sk-or-test",
        model=DEFAULT_MODEL,
        base_url="https://openrouter.ai/api/v1",
        site_url="http://127.0.0.1:5173",
        app_title="Laqta",
    )

    assert provider.name == "openrouter"
    assert provider.endpoint == "https://openrouter.ai/api/v1"

    headers = provider._headers()
    assert headers["Authorization"] == "Bearer sk-or-test"
    assert headers["HTTP-Referer"] == "http://127.0.0.1:5173"
    assert headers["X-Title"] == "Laqta"


def test_describe_config_never_exposes_the_key() -> None:
    provider = OpenRouterProvider(api_key="sk-or-supersecret", model=DEFAULT_MODEL)
    described = provider.describe_config()

    assert described["api_key_configured"] is True
    assert described["hosted"] is True
    assert "sk-or-supersecret" not in str(described)


def test_free_model_ids_are_zero_price_ids() -> None:
    assert FREE_MODEL_IDS
    for model_id in FREE_MODEL_IDS:
        assert model_id.endswith(":free"), model_id


def test_capabilities_report_the_hosted_provider_without_secrets() -> None:
    settings = _settings()
    llm = detect_llm_capabilities(settings)

    assert llm.provider == "openrouter"
    assert llm.model == DEFAULT_MODEL
    assert llm.base_url == "https://openrouter.ai/api/v1"
    assert llm.api_key_configured is True
    assert llm.hosted_opt_in is True
    # The disclosure must be present for a hosted provider.
    assert llm.disclosure and "leave this device" in llm.disclosure
    assert FREE_MODEL_IDS[0] in llm.free_models
    # Never the key itself.
    assert "sk-or-test" not in str(llm.model_dump())


def test_capabilities_without_key_report_missing_key() -> None:
    settings = _settings(LLM_OPENROUTER_API_KEY=None)
    llm = detect_llm_capabilities(settings)

    assert llm.api_key_configured is False
