"""Settings service for local-first configuration persistence and BYOK management."""

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

import qatta
from app.core.config import redact_secret, settings
from app.core.logging import logger
from app.db.connection import get_connection
from app.providers.llm.openrouter import FREE_MODEL_IDS as OPENROUTER_FREE_MODEL_IDS
from app.schemas.settings import (
    ClearCacheResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    VerifyKeyRequest,
    VerifyKeyResponse,
)

# Secret field names that must be redacted and never leaked to logs or client
SECRET_FIELDS = {
    "LLM_API_KEY",
    "LLM_OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "ASSEMBLYAI_API_KEY",
    "HF_TOKEN",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SettingsService:
    """Manages application settings, BYOK secrets, and connection probes."""

    _initial_snapshot: dict[str, Any] = {}
    _initial_env: dict[str, str] = {}

    @classmethod
    def init_and_sync(cls, db_path: Path | None = None) -> None:
        """Load persisted user overrides from SQLite and apply them to runtime settings."""
        if not cls._initial_snapshot:
            cls._initial_snapshot = {
                k: getattr(settings, k)
                for k in dir(settings)
                if k.isupper() and not k.startswith("_")
            }
            cls._initial_env = dict(os.environ)

        try:
            with get_connection(db_path) as conn:
                cursor = conn.execute("SELECT key, value FROM user_settings")
                rows = cursor.fetchall()
                for row in rows:
                    key = row["key"]
                    raw_val = row["value"]
                    try:
                        val = json.loads(raw_val)
                    except Exception:
                        val = raw_val

                    # Apply to in-memory settings
                    if hasattr(settings, key):
                        setattr(settings, key, val)
                    # Sync to os.environ so qatta core pipeline instances inherit overrides
                    if val is not None:
                        os.environ[f"QATTA_{key}"] = str(val).lower() if isinstance(val, bool) else str(val)
                    else:
                        os.environ.pop(f"QATTA_{key}", None)
            logger.info("Loaded persisted user settings overrides from database.")
        except Exception as e:
            logger.warning(f"Could not load user_settings from SQLite (using defaults): {e}")

    @classmethod
    def get_settings_response(cls, db_path: Path | None = None) -> SettingsResponse:
        """Formulate a comprehensive SettingsResponse with masked secrets and disk metrics."""
        data_dir = settings.get_effective_data_dir()
        db_path_resolved = settings.get_db_path()

        # Disk metrics
        try:
            usage = shutil.disk_usage(data_dir)
            total_b = usage.total
            free_b = usage.free
            used_b = usage.used
        except Exception:
            total_b = 0
            free_b = 0
            used_b = 0

        # Transcript cache metrics
        cache_dir = settings.get_transcript_cache_dir()
        cached_count = 0
        cached_bytes = 0
        if cache_dir.exists():
            for p in cache_dir.glob("*.json"):
                if p.is_file():
                    cached_count += 1
                    try:
                        cached_bytes += p.stat().st_size
                    except OSError:
                        pass

        return SettingsResponse(
            app_name=settings.APP_NAME,
            version=qatta.__version__,
            allow_cloud_apis=settings.ALLOW_CLOUD_APIS,
            llm_hosted_opt_in=settings.LLM_HOSTED_OPT_IN,
            enable_url_ingestion=settings.ENABLE_URL_INGESTION,
            # LLM
            llm_ranker_enabled=settings.LLM_RANKER_ENABLED,
            llm_provider=settings.LLM_PROVIDER,
            llm_base_url=settings.LLM_BASE_URL,
            llm_model=settings.LLM_MODEL,
            llm_openrouter_base_url=settings.LLM_OPENROUTER_BASE_URL,
            llm_openrouter_model=settings.LLM_OPENROUTER_MODEL,
            llm_api_key_configured=bool(settings.LLM_API_KEY),
            redacted_llm_api_key=redact_secret(settings.LLM_API_KEY),
            llm_openrouter_api_key_configured=bool(settings.LLM_OPENROUTER_API_KEY),
            redacted_openrouter_api_key=redact_secret(settings.LLM_OPENROUTER_API_KEY),
            free_models=list(OPENROUTER_FREE_MODEL_IDS),
            # Speech Recognition
            default_transcription_backend=settings.DEFAULT_TRANSCRIPTION_BACKEND,
            default_whisper_profile=settings.DEFAULT_WHISPER_PROFILE,
            default_whisper_model=settings.DEFAULT_WHISPER_MODEL,
            fast_whisper_model=settings.FAST_WHISPER_MODEL,
            balanced_whisper_model=settings.BALANCED_WHISPER_MODEL,
            accurate_whisper_model=settings.ACCURATE_WHISPER_MODEL,
            default_whisper_device=settings.DEFAULT_WHISPER_DEVICE,
            default_whisper_compute_type=settings.DEFAULT_WHISPER_COMPUTE_TYPE,
            whisper_vad_filter=settings.WHISPER_VAD_FILTER,
            whisper_beam_size=settings.WHISPER_BEAM_SIZE,
            whisper_cpu_threads=settings.WHISPER_CPU_THREADS,
            # Cloud Transcription
            groq_model=settings.GROQ_MODEL,
            groq_api_key_configured=bool(settings.GROQ_API_KEY),
            redacted_groq_api_key=redact_secret(settings.GROQ_API_KEY),
            assemblyai_api_key_configured=bool(settings.ASSEMBLYAI_API_KEY),
            redacted_assemblyai_api_key=redact_secret(settings.ASSEMBLYAI_API_KEY),
            hf_token_configured=bool(settings.HF_TOKEN),
            redacted_hf_token=redact_secret(settings.HF_TOKEN),
            # Arabic & Alignment
            clip_alignment_enabled=settings.CLIP_ALIGNMENT_ENABLED,
            clip_alignment_model=settings.CLIP_ALIGNMENT_MODEL,
            max_clip_alignment_seconds=settings.MAX_CLIP_ALIGNMENT_SECONDS,
            arabish_initial_prompt=True,
            arabish_prompt_text=(
                "محاضرة وبودكاست باللهجة المصرية والعربية مع مصطلحات تقنية مثل "
                "AI, API, SaaS, Startup, Deployment, Marketing, ROI."
            ),
            # Ingestion
            youtube_sub_languages=settings.URL_INGEST_SUB_LANGUAGES,
            yt_dlp_player_client=settings.YT_DLP_PLAYER_CLIENT,
            yt_dlp_cookies_path=settings.YT_DLP_COOKIES_PATH,
            yt_dlp_cookies_from_browser=settings.YT_DLP_COOKIES_FROM_BROWSER,
            ffmpeg_timeout_seconds=settings.FFMPEG_TIMEOUT_SECONDS,
            # Storage
            data_dir=str(data_dir),
            db_path=str(db_path_resolved),
            transcript_cache_enabled=settings.TRANSCRIPT_CACHE_ENABLED,
            cached_transcripts_count=cached_count,
            cached_transcripts_bytes=cached_bytes,
            disk_total_bytes=total_b,
            disk_free_bytes=free_b,
            disk_used_bytes=used_b,
        )

    @classmethod
    def update_settings(
        cls, patch: SettingsUpdateRequest, db_path: Path | None = None
    ) -> SettingsResponse:
        """Apply patch to user_settings table, in-memory settings, and os.environ."""
        fields = patch.model_dump(exclude_unset=True)
        now = _utc_now_iso()

        # Mapping between schema fields and Settings attribute names
        key_map = {
            "allow_cloud_apis": "ALLOW_CLOUD_APIS",
            "llm_hosted_opt_in": "LLM_HOSTED_OPT_IN",
            "enable_url_ingestion": "ENABLE_URL_INGESTION",
            "llm_ranker_enabled": "LLM_RANKER_ENABLED",
            "llm_provider": "LLM_PROVIDER",
            "llm_base_url": "LLM_BASE_URL",
            "llm_model": "LLM_MODEL",
            "llm_api_key": "LLM_API_KEY",
            "llm_openrouter_base_url": "LLM_OPENROUTER_BASE_URL",
            "llm_openrouter_model": "LLM_OPENROUTER_MODEL",
            "llm_openrouter_api_key": "LLM_OPENROUTER_API_KEY",
            "default_transcription_backend": "DEFAULT_TRANSCRIPTION_BACKEND",
            "default_whisper_profile": "DEFAULT_WHISPER_PROFILE",
            "default_whisper_model": "DEFAULT_WHISPER_MODEL",
            "fast_whisper_model": "FAST_WHISPER_MODEL",
            "balanced_whisper_model": "BALANCED_WHISPER_MODEL",
            "accurate_whisper_model": "ACCURATE_WHISPER_MODEL",
            "default_whisper_device": "DEFAULT_WHISPER_DEVICE",
            "default_whisper_compute_type": "DEFAULT_WHISPER_COMPUTE_TYPE",
            "whisper_vad_filter": "WHISPER_VAD_FILTER",
            "whisper_beam_size": "WHISPER_BEAM_SIZE",
            "whisper_cpu_threads": "WHISPER_CPU_THREADS",
            "groq_api_key": "GROQ_API_KEY",
            "groq_model": "GROQ_MODEL",
            "assemblyai_api_key": "ASSEMBLYAI_API_KEY",
            "hf_token": "HF_TOKEN",
            "clip_alignment_enabled": "CLIP_ALIGNMENT_ENABLED",
            "clip_alignment_model": "CLIP_ALIGNMENT_MODEL",
            "max_clip_alignment_seconds": "MAX_CLIP_ALIGNMENT_SECONDS",
            "youtube_sub_languages": "URL_INGEST_SUB_LANGUAGES",
            "yt_dlp_player_client": "YT_DLP_PLAYER_CLIENT",
            "yt_dlp_cookies_path": "YT_DLP_COOKIES_PATH",
            "yt_dlp_cookies_from_browser": "YT_DLP_COOKIES_FROM_BROWSER",
            "ffmpeg_timeout_seconds": "FFMPEG_TIMEOUT_SECONDS",
            "transcript_cache_enabled": "TRANSCRIPT_CACHE_ENABLED",
        }

        with get_connection(db_path) as conn:
            for field_name, val in fields.items():
                setting_key = key_map.get(field_name)
                if not setting_key:
                    continue

                # Handle secret clearing
                if setting_key in SECRET_FIELDS and val == "":
                    val = None

                # Update in-memory settings
                if hasattr(settings, setting_key):
                    setattr(settings, setting_key, val)

                # Persist in user_settings table
                conn.execute(
                    """
                    INSERT INTO user_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                    """,
                    (setting_key, json.dumps(val), now),
                )

                # Update os.environ
                if val is not None:
                    os.environ[f"QATTA_{setting_key}"] = (
                        str(val).lower() if isinstance(val, bool) else str(val)
                    )
                else:
                    os.environ.pop(f"QATTA_{setting_key}", None)

        return cls.get_settings_response(db_path)

    @classmethod
    async def verify_provider_connection(
        cls, req: VerifyKeyRequest, http_client: httpx.AsyncClient | None = None
    ) -> VerifyKeyResponse:
        """Execute a lightweight live connection probe for an AI provider."""
        t0 = time.monotonic()
        provider = req.provider.lower().strip()

        # Shared client context
        client_ctx = (
            http_client
            if http_client is not None
            else httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        )

        try:
            async with client_ctx as client:
                if provider == "openrouter":
                    key = req.api_key or settings.LLM_OPENROUTER_API_KEY
                    if not key:
                        return VerifyKeyResponse(
                            ok=False,
                            message="No OpenRouter API key provided or configured.",
                            latency_ms=0,
                        )

                    base_url = (
                        req.base_url or settings.LLM_OPENROUTER_BASE_URL
                    ).rstrip("/")
                    resp = await client.get(
                        f"{base_url}/models",
                        headers={
                            "Authorization": f"Bearer {key.strip()}",
                            "HTTP-Referer": "http://127.0.0.1:5173",
                            "X-Title": "Laqta",
                        },
                    )
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        data = resp.json()
                        raw_models = data.get("data", [])
                        model_ids = [m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m]
                        free_models = [m for m in model_ids if m and m.endswith(":free")]
                        return VerifyKeyResponse(
                            ok=True,
                            message=f"Connected to OpenRouter ({len(model_ids)} models available, {len(free_models)} zero-cost)",
                            latency_ms=latency,
                            models_found=free_models[:10],
                        )
                    if resp.status_code == 401:
                        return VerifyKeyResponse(
                            ok=False,
                            message="401 Unauthorized: Invalid OpenRouter API key.",
                            latency_ms=latency,
                        )
                    if resp.status_code == 429:
                        return VerifyKeyResponse(
                            ok=False,
                            message="429 Rate Limit: OpenRouter rate limit reached.",
                            latency_ms=latency,
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"OpenRouter returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                elif provider in ("openai_compatible", "ollama", "lmstudio"):
                    base_url = (req.base_url or settings.LLM_BASE_URL).rstrip("/")
                    key = req.api_key or settings.LLM_API_KEY
                    headers = {}
                    if key:
                        headers["Authorization"] = f"Bearer {key.strip()}"

                    resp = await client.get(f"{base_url}/models", headers=headers)
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        data = resp.json()
                        raw_models = data.get("data", [])
                        model_ids = [m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m]
                        return VerifyKeyResponse(
                            ok=True,
                            message=f"Connected to endpoint ({len(model_ids)} models found)",
                            latency_ms=latency,
                            models_found=model_ids[:10],
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"Endpoint returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                elif provider == "groq":
                    key = req.api_key or settings.GROQ_API_KEY
                    if not key:
                        return VerifyKeyResponse(
                            ok=False,
                            message="No Groq API key provided or configured.",
                            latency_ms=0,
                        )

                    resp = await client.get(
                        "https://api.groq.com/openai/v1/models",
                        headers={"Authorization": f"Bearer {key.strip()}"},
                    )
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        data = resp.json()
                        raw_models = data.get("data", [])
                        model_ids = [m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m]
                        whisper_models = [m for m in model_ids if "whisper" in m.lower()]
                        return VerifyKeyResponse(
                            ok=True,
                            message=f"Connected to Groq Cloud Whisper API ({len(whisper_models)} speech models ready)",
                            latency_ms=latency,
                            models_found=whisper_models,
                        )
                    if resp.status_code == 401:
                        return VerifyKeyResponse(
                            ok=False,
                            message="401 Unauthorized: Invalid Groq API key.",
                            latency_ms=latency,
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"Groq returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                elif provider == "assemblyai":
                    key = req.api_key or settings.ASSEMBLYAI_API_KEY
                    if not key:
                        return VerifyKeyResponse(
                            ok=False,
                            message="No AssemblyAI API key provided or configured.",
                            latency_ms=0,
                        )

                    resp = await client.get(
                        "https://api.assemblyai.com/v2/account",
                        headers={"Authorization": key.strip()},
                    )
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        return VerifyKeyResponse(
                            ok=True,
                            message="Connected to AssemblyAI API (Account verified)",
                            latency_ms=latency,
                        )
                    if resp.status_code == 401:
                        return VerifyKeyResponse(
                            ok=False,
                            message="401 Unauthorized: Invalid AssemblyAI API key.",
                            latency_ms=latency,
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"AssemblyAI returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                elif provider == "gemini":
                    key = req.api_key or settings.LLM_API_KEY
                    if not key:
                        return VerifyKeyResponse(
                            ok=False,
                            message="No Gemini API key provided or configured.",
                            latency_ms=0,
                        )

                    resp = await client.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models?key={key.strip()}"
                    )
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        data = resp.json()
                        raw_models = data.get("models", [])
                        names = [m.get("displayName", m.get("name")) for m in raw_models if isinstance(m, dict)]
                        return VerifyKeyResponse(
                            ok=True,
                            message=f"Connected to Google Gemini API ({len(names)} models available)",
                            latency_ms=latency,
                            models_found=names[:6],
                        )
                    if resp.status_code in (400, 403):
                        return VerifyKeyResponse(
                            ok=False,
                            message="API key rejected by Google Gemini API.",
                            latency_ms=latency,
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"Gemini returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                else:
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"Unknown provider '{provider}'. Supported: openrouter, openai_compatible, groq, assemblyai, gemini",
                        latency_ms=0,
                    )

        except httpx.TimeoutException:
            latency = int((time.monotonic() - t0) * 1000)
            return VerifyKeyResponse(
                ok=False,
                message="Connection timed out after 10 seconds. Check network or host address.",
                latency_ms=latency,
            )
        except (httpx.RequestError, OSError) as e:
            latency = int((time.monotonic() - t0) * 1000)
            return VerifyKeyResponse(
                ok=False,
                message=f"Connection refused or network error: {e}",
                latency_ms=latency,
            )

    @classmethod
    def clear_transcript_cache(cls) -> ClearCacheResponse:
        """Safely clear cached transcript JSON files."""
        cache_dir = settings.get_transcript_cache_dir()
        count = 0
        freed = 0
        if cache_dir.exists():
            for p in cache_dir.glob("*.json"):
                if p.is_file():
                    try:
                        sz = p.stat().st_size
                        p.unlink()
                        count += 1
                        freed += sz
                    except OSError:
                        pass
        return ClearCacheResponse(
            cleared_files=count,
            freed_bytes=freed,
            message=f"Cleared {count} cached transcripts ({freed / (1024 * 1024):.2f} MB freed).",
        )

    @classmethod
    def reset_to_defaults(cls, db_path: Path | None = None) -> SettingsResponse:
        """Clear user_settings table overrides and reset to code defaults."""
        with get_connection(db_path) as conn:
            cursor = conn.execute("SELECT key FROM user_settings")
            keys = [r["key"] for r in cursor.fetchall()]
            conn.execute("DELETE FROM user_settings")

        for k in keys:
            upper_k = f"QATTA_{k}"
            if upper_k in cls._initial_env:
                os.environ[upper_k] = cls._initial_env[upper_k]
            else:
                os.environ.pop(upper_k, None)

        if cls._initial_snapshot:
            for k, val in cls._initial_snapshot.items():
                if hasattr(settings, k):
                    setattr(settings, k, val)
        else:
            from app.core.config import Settings
            fresh = Settings()
            for k in dir(fresh):
                if k.isupper() and not k.startswith("_"):
                    setattr(settings, k, getattr(fresh, k))

        return cls.get_settings_response(db_path)
