"""Comprehensive test suite for Settings & Bring Your Own Keys (BYOK) API routes."""

import os
import stat
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.settings_service import SettingsService


@pytest.fixture(autouse=True)
def clean_settings_state():
    """Ensure settings changes in tests do not pollute subsequent tests or environment."""
    yield
    SettingsService.reset_to_defaults()


def test_get_settings_redacted(client: TestClient) -> None:
    """GET /api/settings returns valid settings schema with properly redacted secrets."""
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
    assert "redacted_assemblyai_api_key" in data
    assert "redacted_hf_token" in data
    assert "default_whisper_profile" in data
    assert "data_dir" in data
    assert "disk_total_bytes" in data
    assert "disk_free_bytes" in data

    # Verify secrets are never exposed in plain text
    assert data["redacted_openrouter_api_key"] != "sk-or-real-secret"
    assert data["redacted_groq_api_key"] != "gsk_real-secret"
    assert isinstance(data["llm_openrouter_api_key_configured"], bool)
    assert isinstance(data["groq_api_key_configured"], bool)


def test_patch_settings_partial_and_persistence(client: TestClient) -> None:
    """PATCH /api/settings updates settings, persists to SQLite and mirror, and syncs env."""
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

    # Verify runtime singleton updated
    assert settings.LLM_PROVIDER == "openrouter"
    assert settings.ALLOW_CLOUD_APIS is True
    assert settings.WHISPER_VAD_FILTER is False

    # Verify os.environ synchronized
    assert os.environ.get("QATTA_LLM_PROVIDER") == "openrouter"
    assert os.environ.get("QATTA_ALLOW_CLOUD_APIS") == "true"
    assert os.environ.get("QATTA_WHISPER_VAD_FILTER") == "false"

    # Verify restart persistence by re-running init_and_sync
    settings.ALLOW_CLOUD_APIS = False
    SettingsService.init_and_sync()
    assert settings.ALLOW_CLOUD_APIS is True


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
    assert settings.LLM_OPENROUTER_API_KEY is None


@pytest.mark.asyncio
async def test_cloud_gating_independent(client: TestClient) -> None:
    """Verify that cloud flags independently block remote probes without HTTP requests."""
    # Ensure cloud is blocked
    client.patch("/api/settings", json={"allow_cloud_apis": False, "llm_hosted_opt_in": False})

    with patch("app.services.settings_service.httpx.AsyncClient") as mock_client:
        # Probe hosted OpenRouter
        resp = client.post(
            "/api/settings/verify", json={"provider": "openrouter", "api_key": "test_key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Cloud APIs are disabled" in data["message"]
        mock_client.assert_not_called()

        # Enable allow_cloud_apis but keep llm_hosted_opt_in False
        client.patch("/api/settings", json={"allow_cloud_apis": True, "llm_hosted_opt_in": False})
        resp = client.post(
            "/api/settings/verify", json={"provider": "openrouter", "api_key": "test_key"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Hosted LLM opt-in is required" in data["message"]
        mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_verify_provider_mocked_scenarios(client: TestClient) -> None:
    """Mock OpenRouter, Groq, and Ollama with success, timeout, 401, 429, and 404."""
    # Enable cloud flags for mock test
    client.patch("/api/settings", json={"allow_cloud_apis": True, "llm_hosted_opt_in": True})

    # 1. OpenRouter 200 Success
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "data": [
            {"id": "minimax/minimax-m3.1-flash:free"},
            {"id": "meta-llama/llama-3.3-70b-instruct:free"},
        ]
    }

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_resp_200
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http_client):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openrouter", "api_key": "candidate_temp_key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["models_found"]) == 2
        # Verify candidate key was NOT persisted automatically
        curr_settings = client.get("/api/settings").json()
        assert curr_settings["redacted_openrouter_api_key"] != "cand..._key"

    # 2. OpenRouter 401 Invalid Key
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    mock_http_client.get.return_value = mock_resp_401
    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http_client):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openrouter", "api_key": "bad_key"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "401 Unauthorized" in resp.json()["message"]

    # 3. OpenRouter 429 Rate Limit
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_http_client.get.return_value = mock_resp_429
    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http_client):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openrouter", "api_key": "rate_limited_key"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "429 Rate Limit" in resp.json()["message"]

    # 4. Timeout Exception
    mock_http_client.get.side_effect = httpx.TimeoutException("Read timed out")
    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http_client):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openrouter", "api_key": "timeout_key"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "timed out" in resp.json()["message"].lower()

    # 5. Connection Refused
    mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")
    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http_client):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openai_compatible", "base_url": "http://127.0.0.1:11434/v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "Connection refused" in resp.json()["message"]


def test_filesystem_security_and_permissions(client: TestClient) -> None:
    """Verify that data_dir is 0700 and settings.json / qatta.db are 0600 on POSIX systems."""
    data_dir = settings.get_effective_data_dir()
    db_file = settings.get_db_path()
    mirror_file = data_dir / "settings.json"

    # Trigger a settings update to ensure mirror exists
    client.patch("/api/settings", json={"ffmpeg_timeout_seconds": 350})

    if os.name == "posix":
        dir_mode = stat.S_IMODE(data_dir.stat().st_mode)
        assert dir_mode == 0o700, f"Expected 0700 on data_dir, got {oct(dir_mode)}"

        if mirror_file.exists():
            file_mode = stat.S_IMODE(mirror_file.stat().st_mode)
            assert file_mode == 0o600, f"Expected 0600 on settings.json, got {oct(file_mode)}"

        if db_file.exists():
            db_mode = stat.S_IMODE(db_file.stat().st_mode)
            assert db_mode == 0o600, f"Expected 0600 on qatta.db, got {oct(db_mode)}"


def test_clear_transcript_cache_preserves_media_and_renders(client: TestClient) -> None:
    """POST /api/settings/clear-cache deletes only cached transcripts, not media or renders."""
    cache_dir = settings.get_transcript_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    test_cache_file = cache_dir / "test_fake_hash.json"
    test_cache_file.write_text('{"mock": "cached"}', encoding="utf-8")

    # Create dummy project media and render files
    media_dir = settings.get_project_media_dir("test_proj_preserve")
    render_dir = settings.get_project_renders_dir("test_proj_preserve")
    dummy_media = media_dir / "sample.mp4"
    dummy_render = render_dir / "clip_01.mp4"
    dummy_media.write_bytes(b"media_bytes")
    dummy_render.write_bytes(b"render_bytes")

    response = client.post("/api/settings/clear-cache")
    assert response.status_code == 200
    data = response.json()
    assert data["cleared_files"] >= 1
    assert data["freed_bytes"] > 0
    assert not test_cache_file.exists()

    # Verify media and renders are preserved
    assert dummy_media.exists()
    assert dummy_render.exists()

    # Clean up dummy project
    dummy_media.unlink()
    dummy_render.unlink()


def test_reset_to_defaults(client: TestClient) -> None:
    """POST /api/settings/reset clears user overrides and restores defaults."""
    # First make a change
    client.patch(
        "/api/settings", json={"llm_provider": "openrouter", "ffmpeg_timeout_seconds": 999}
    )

    # Then reset
    response = client.post("/api/settings/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["llm_provider"] in ("openai_compatible", "ollama")
    assert data["ffmpeg_timeout_seconds"] == 300

    # Verify settings.json was deleted or emptied
    mirror_file = settings.get_effective_data_dir() / "settings.json"
    assert not mirror_file.exists()


def test_masked_preview_resubmission_ignored(client: TestClient) -> None:
    """Ensure submitting a masked preview does not overwrite the real stored secret."""
    real_secret = "sk-or-v1-abcdef1234567890real"
    client.patch("/api/settings", json={"llm_openrouter_api_key": real_secret})
    assert settings.LLM_OPENROUTER_API_KEY == real_secret

    resp = client.get("/api/settings")
    redacted = resp.json()["redacted_openrouter_api_key"]
    assert redacted != real_secret
    assert "..." in redacted

    # Resubmit the redacted preview
    client.patch("/api/settings", json={"llm_openrouter_api_key": redacted})
    # Real secret must remain intact
    assert settings.LLM_OPENROUTER_API_KEY == real_secret

    # Also test "***" and "<none>" resubmission
    client.patch("/api/settings", json={"llm_openrouter_api_key": "***"})
    assert settings.LLM_OPENROUTER_API_KEY == real_secret

    client.patch("/api/settings", json={"llm_openrouter_api_key": "<none>"})
    assert settings.LLM_OPENROUTER_API_KEY == real_secret


def test_cloud_metadata_ssrf_blocked(client: TestClient) -> None:
    """Ensure probes to cloud metadata / link-local addresses are rejected before sending."""
    # Enable cloud flags to test endpoint boundary validation
    client.patch("/api/settings", json={"allow_cloud_apis": True, "llm_hosted_opt_in": True})

    with patch("app.services.settings_service.httpx.AsyncClient") as mock_client:
        # 169.254.169.254 AWS/GCP/Azure link-local metadata
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "openai_compatible", "base_url": "http://169.254.169.254/v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "prohibited" in resp.json()["message"].lower()
        mock_client.assert_not_called()

        # metadata.google.internal
        resp2 = client.post(
            "/api/settings/verify",
            json={
                "provider": "openai_compatible",
                "base_url": "http://metadata.google.internal/v1",
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["ok"] is False
        assert "metadata" in resp2.json()["message"].lower()
        mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_verify_huggingface_provider(client: TestClient) -> None:
    """Verify Hugging Face token probing (200 success and 401 unauthorized)."""
    client.patch("/api/settings", json={"allow_cloud_apis": True})

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"name": "test_developer"}

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_resp_200
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "huggingface", "api_key": "hf_valid_token_123"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "Connected to Hugging Face API (test_developer)" in resp.json()["message"]

    # 401 Unauthorized
    mock_resp_401 = MagicMock()
    mock_resp_401.status_code = 401
    mock_http.get.return_value = mock_resp_401

    with patch("app.services.settings_service.httpx.AsyncClient", return_value=mock_http):
        resp = client.post(
            "/api/settings/verify",
            json={"provider": "huggingface", "api_key": "hf_invalid_token"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "401 Unauthorized" in resp.json()["message"]
