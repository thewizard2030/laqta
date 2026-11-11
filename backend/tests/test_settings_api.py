"""Tests for Settings & BYOK API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_get_settings(client: TestClient) -> None:
    """GET /api/settings returns valid settings schema with redacted secrets."""
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()

    assert data["app_name"] == "Laqta"
    assert "version" in data
    assert "allow_cloud_apis" in data
    assert "llm_hosted_opt_in" in data
    assert "llm_provider" in data
    assert "redacted_openrouter_api_key" in data
    assert "redacted_groq_api_key" in data
    assert "default_whisper_profile" in data
    assert "data_dir" in data
    assert "disk_total_bytes" in data
    assert "disk_free_bytes" in data

    # Verify secrets are NEVER exposed in plain text
    assert data["redacted_openrouter_api_key"] != "sk-or-real-secret"
    assert data["redacted_groq_api_key"] != "gsk_real-secret"


def test_update_settings(client: TestClient) -> None:
    """PATCH /api/settings updates settings and persists them."""
    patch_payload = {
        "llm_provider": "openrouter",
        "llm_openrouter_model": "meta-llama/llama-3.3-70b-instruct:free",
        "default_whisper_profile": "balanced",
        "allow_cloud_apis": True,
        "llm_hosted_opt_in": True,
        "whisper_vad_filter": False,
    }

    response = client.patch("/api/settings", json=patch_payload)
    assert response.status_code == 200
    data = response.json()

    assert data["llm_provider"] == "openrouter"
    assert data["llm_openrouter_model"] == "meta-llama/llama-3.3-70b-instruct:free"
    assert data["default_whisper_profile"] == "balanced"
    assert data["allow_cloud_apis"] is True
    assert data["llm_hosted_opt_in"] is True
    assert data["whisper_vad_filter"] is False


def test_byok_api_key_update_and_clear(client: TestClient) -> None:
    """PATCH /api/settings allows setting a new API key and clearing it with empty string."""
    # 1. Set key
    response = client.patch(
        "/api/settings",
        json={"llm_openrouter_api_key": "sk-or-v1-testkey1234567890abcdef"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["llm_openrouter_api_key_configured"] is True
    assert data["redacted_openrouter_api_key"].startswith("sk-o...")

    # Verify raw secret is never returned
    assert "testkey1234567890" not in data["redacted_openrouter_api_key"]

    # 2. Clear key with empty string
    response = client.patch(
        "/api/settings",
        json={"llm_openrouter_api_key": ""},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["llm_openrouter_api_key_configured"] is False
    assert data["redacted_openrouter_api_key"] == "<none>"


@pytest.mark.asyncio
async def test_verify_provider_without_key(client: TestClient) -> None:
    """POST /api/settings/verify fails gracefully when no key is configured."""
    with patch.object(settings, "LLM_OPENROUTER_API_KEY", None):
        response = client.post(
            "/api/settings/verify",
            json={"provider": "openrouter"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "No OpenRouter API key" in data["message"]


@pytest.mark.asyncio
async def test_verify_openrouter_success(client: TestClient) -> None:
    """POST /api/settings/verify returns ok=True when probe returns 200."""
    mock_models_response = {
        "data": [
            {"id": "minimax/minimax-m3.1-flash:free"},
            {"id": "meta-llama/llama-3.3-70b-instruct:free"},
            {"id": "anthropic/claude-3.5-sonnet"},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_models_response

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_resp
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch(
        "app.services.settings_service.httpx.AsyncClient",
        return_value=mock_http_client,
    ):
        response = client.post(
            "/api/settings/verify",
            json={
                "provider": "openrouter",
                "api_key": "sk-or-v1-mockvalidkey123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "Connected to OpenRouter" in data["message"]
        assert len(data["models_found"]) == 2


@pytest.mark.asyncio
async def test_verify_groq_success(client: TestClient) -> None:
    """POST /api/settings/verify verifies Groq speech models."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "whisper-large-v3-turbo"},
            {"id": "whisper-large-v3"},
            {"id": "llama-3.3-70b-versatile"},
        ]
    }

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_resp
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch(
        "app.services.settings_service.httpx.AsyncClient",
        return_value=mock_http_client,
    ):
        response = client.post(
            "/api/settings/verify",
            json={"provider": "groq", "api_key": "gsk_mockvalidkey123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "Connected to Groq Cloud Whisper API" in data["message"]


def test_clear_transcript_cache(client: TestClient) -> None:
    """POST /api/settings/clear-cache deletes cached transcript files."""
    cache_dir = settings.get_transcript_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    test_cache_file = cache_dir / "test_fake_hash.json"
    test_cache_file.write_text('{"mock": "cached"}', encoding="utf-8")

    response = client.post("/api/settings/clear-cache")
    assert response.status_code == 200
    data = response.json()
    assert data["cleared_files"] >= 1
    assert data["freed_bytes"] > 0
    assert not test_cache_file.exists()


def test_reset_settings(client: TestClient) -> None:
    """POST /api/settings/reset clears user overrides and restores defaults."""
    # First make a change
    client.patch("/api/settings", json={"llm_provider": "openrouter"})

    # Then reset
    response = client.post("/api/settings/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["llm_provider"] in ("openai_compatible", "ollama")
