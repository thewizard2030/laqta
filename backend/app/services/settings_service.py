"""Settings service for local-first configuration persistence and BYOK management."""

import ipaddress
import json
import os
import shutil
import time
import urllib.parse
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


def _is_loopback_url(url: str) -> bool:
    """True when the URL host is loopback (127.0.0.1, localhost, ::1)."""
    host = urllib.parse.urlparse(url).hostname or ""
    if not host:
        return False
    host = host.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class SettingsService:
    """Manages application settings, BYOK secrets, and connection probes."""

    _initial_snapshot: dict[str, Any] = {}
    _initial_env: dict[str, str] = {}

    @classmethod
    def _ensure_secure_permissions(
        cls, data_dir: Path, db_path: Path | None = None, mirror_path: Path | None = None
    ) -> None:
        """Enforce strict POSIX file mode 0600 on files and 0700 on containing directories."""
        if os.name != "posix":
            return
        try:
            if data_dir.exists():
                os.chmod(data_dir, 0o700)
            if db_path and db_path.exists():
                os.chmod(db_path, 0o600)
                for aux in (data_dir / f"{db_path.name}-wal", data_dir / f"{db_path.name}-shm"):
                    if aux.exists():
                        os.chmod(aux, 0o600)
            if mirror_path and mirror_path.exists():
                os.chmod(mirror_path, 0o600)
        except OSError as e:
            logger.debug(f"Could not set restrictive filesystem permissions: {e}")

    @classmethod
    def _atomic_write_mirror(cls, data_dir: Path, data: dict[str, Any]) -> Path:
        """Write settings mirror atomically to settings.json with mode 0600."""
        data_dir.mkdir(parents=True, exist_ok=True)
        cls._ensure_secure_permissions(data_dir)
        target = data_dir / "settings.json"
        if target.is_symlink():
            target.unlink()

        tmp_target = data_dir / f"settings.json.tmp.{os.getpid()}"
        if tmp_target.is_symlink():
            tmp_target.unlink()

        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            fd = os.open(tmp_target, flags, 0o600)
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            try:
                os.chmod(tmp_target, 0o600)
            except OSError:
                pass
            os.replace(tmp_target, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            return target
        finally:
            if tmp_target.exists():
                try:
                    tmp_target.unlink()
                except OSError:
                    pass

    @classmethod
    def init_and_sync(cls, db_path: Path | None = None) -> None:
        """Load persisted user overrides from SQLite (or mirror) and apply to runtime settings."""
        if not cls._initial_snapshot:
            cls._initial_snapshot = {
                k: getattr(settings, k)
                for k in dir(settings)
                if k.isupper() and not k.startswith("_")
            }
            cls._initial_env = dict(os.environ)

        data_dir = settings.get_effective_data_dir()
        db_file = db_path or settings.get_db_path()
        mirror_file = data_dir / "settings.json"
        cls._ensure_secure_permissions(data_dir, db_file, mirror_file)

        loaded_settings: dict[str, Any] = {}
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
                    loaded_settings[key] = val

            # If SQLite has no rows but settings.json mirror exists, populate from mirror
            if not loaded_settings and mirror_file.exists():
                try:
                    with open(mirror_file, encoding="utf-8") as f:
                        mirror_data = json.load(f)
                    if isinstance(mirror_data, dict) and mirror_data:
                        loaded_settings = mirror_data
                        now = _utc_now_iso()
                        with get_connection(db_path) as conn:
                            for k, v in loaded_settings.items():
                                conn.execute(
                                    """
                                    INSERT INTO user_settings (key, value, updated_at)
                                    VALUES (?, ?, ?)
                                    ON CONFLICT(key) DO UPDATE SET
                                        value = excluded.value, updated_at = excluded.updated_at
                                    """,
                                    (k, json.dumps(v), now),
                                )
                except Exception as ex:
                    logger.warning(f"Could not load settings mirror from {mirror_file}: {ex}")

            for key, val in loaded_settings.items():
                if hasattr(settings, key):
                    setattr(settings, key, val)
                if val is not None:
                    os.environ[f"QATTA_{key}"] = (
                        str(val).lower() if isinstance(val, bool) else str(val)
                    )
                else:
                    os.environ.pop(f"QATTA_{key}", None)

            if loaded_settings:
                cls._atomic_write_mirror(data_dir, loaded_settings)

            logger.info("Loaded persisted user settings overrides.")
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

        data_dir = settings.get_effective_data_dir()
        db_file = db_path or settings.get_db_path()
        mirror_file = data_dir / "settings.json"

        with get_connection(db_path) as conn:
            for field_name, val in fields.items():
                setting_key = key_map.get(field_name)
                if not setting_key:
                    continue

                # Handle secret updates & masked preview protection
                if setting_key in SECRET_FIELDS:
                    if val == "":
                        val = None
                    elif isinstance(val, str) and (
                        val in ("<none>", "***")
                        or val == redact_secret(getattr(settings, setting_key, None))
                        or ("..." in val and len(val) <= 12)
                    ):
                        # Masked preview resubmitted; do not overwrite stored secret with preview
                        continue

                # Update in-memory settings
                if hasattr(settings, setting_key):
                    setattr(settings, setting_key, val)

                # Persist in user_settings table
                conn.execute(
                    """
                    INSERT INTO user_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value, updated_at = excluded.updated_at
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

            # Query all current overrides and mirror atomically to settings.json
            cursor = conn.execute("SELECT key, value FROM user_settings")
            all_overrides = {}
            for row in cursor.fetchall():
                try:
                    all_overrides[row["key"]] = json.loads(row["value"])
                except Exception:
                    all_overrides[row["key"]] = row["value"]

            cls._atomic_write_mirror(data_dir, all_overrides)
            cls._ensure_secure_permissions(data_dir, db_file, mirror_file)

        return cls.get_settings_response(db_path)

    @classmethod
    async def verify_provider_connection(
        cls, req: VerifyKeyRequest, http_client: httpx.AsyncClient | None = None
    ) -> VerifyKeyResponse:
        """Execute a lightweight live connection probe for an AI provider."""
        t0 = time.monotonic()
        provider = req.provider.lower().strip()

        # Cloud privacy gating checks
        if provider in ("openrouter", "groq", "assemblyai", "huggingface", "hf"):
            if not settings.ALLOW_CLOUD_APIS:
                return VerifyKeyResponse(
                    ok=False,
                    message=(
                        "Cloud APIs are disabled. "
                        "Enable 'allow_cloud_apis: true' before testing hosted providers."
                    ),
                    latency_ms=0,
                )
            if provider == "openrouter" and not settings.LLM_HOSTED_OPT_IN:
                return VerifyKeyResponse(
                    ok=False,
                    message=(
                        "Hosted LLM opt-in is required. "
                        "Enable 'llm_hosted_opt_in: true' before testing OpenRouter."
                    ),
                    latency_ms=0,
                )

        # URL validation helper
        def _validate_url(url_str: str) -> str | None:
            try:
                p = urllib.parse.urlparse(url_str)
                if p.scheme not in ("http", "https"):
                    return (
                        f"Invalid URL scheme '{p.scheme}'. Only http:// and https:// are supported."
                    )
                if not p.netloc or not p.hostname:
                    return "Invalid URL: missing host authority."
                host = p.hostname.strip("[]").lower()
                # Disallow cloud metadata and link-local addresses
                if host in ("metadata.google.internal", "instance-data"):
                    return "Access to cloud metadata endpoints is prohibited."
                try:
                    ip = ipaddress.ip_address(host)
                    if ip.is_link_local or ip.is_reserved or ip.is_multicast:
                        return (
                            "Access to link-local, reserved, or multicast addresses is prohibited."
                        )
                except ValueError:
                    pass
            except Exception as ex:
                return f"Malformed URL: {ex}"
            return None

        # Check custom base URL if provided
        if req.base_url:
            err = _validate_url(req.base_url)
            if err:
                return VerifyKeyResponse(ok=False, message=err, latency_ms=0)
            if provider in ("openai_compatible", "ollama", "lmstudio") and not _is_loopback_url(
                req.base_url
            ):
                if not settings.ALLOW_CLOUD_APIS or not settings.LLM_HOSTED_OPT_IN:
                    return VerifyKeyResponse(
                        ok=False,
                        message=(
                            "Remote endpoint requires both 'allow_cloud_apis: true' "
                            "and 'llm_hosted_opt_in: true'."
                        ),
                        latency_ms=0,
                    )

        # Shared client context with explicit 8.0s timeout and disabled redirects (prevents SSRF)
        client_ctx = (
            http_client
            if http_client is not None
            else httpx.AsyncClient(
                timeout=httpx.Timeout(8.0),
                follow_redirects=False,
            )
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

                    base_url = (req.base_url or settings.LLM_OPENROUTER_BASE_URL).rstrip("/")
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
                        model_ids = [
                            m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m
                        ]
                        free_models = [m for m in model_ids if m and m.endswith(":free")]
                        return VerifyKeyResponse(
                            ok=True,
                            message=(
                                f"Connected to OpenRouter ({len(model_ids)} models available, "
                                f"{len(free_models)} zero-cost)"
                            ),
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
                        model_ids = [
                            m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m
                        ]
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
                        model_ids = [
                            m.get("id") for m in raw_models if isinstance(m, dict) and "id" in m
                        ]
                        whisper_models = [m for m in model_ids if "whisper" in m.lower()]
                        return VerifyKeyResponse(
                            ok=True,
                            message=(
                                f"Connected to Groq Cloud Whisper API "
                                f"({len(whisper_models)} speech models ready)"
                            ),
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

                elif provider in ("huggingface", "hf"):
                    key = req.api_key or settings.HF_TOKEN
                    if not key:
                        return VerifyKeyResponse(
                            ok=False,
                            message="No Hugging Face token provided or configured.",
                            latency_ms=0,
                        )

                    resp = await client.get(
                        "https://huggingface.co/api/whoami-v2",
                        headers={"Authorization": f"Bearer {key.strip()}"},
                    )
                    latency = int((time.monotonic() - t0) * 1000)

                    if resp.status_code == 200:
                        data = resp.json()
                        user_name = data.get("name", "account verified")
                        return VerifyKeyResponse(
                            ok=True,
                            message=f"Connected to Hugging Face API ({user_name})",
                            latency_ms=latency,
                        )
                    if resp.status_code == 401:
                        return VerifyKeyResponse(
                            ok=False,
                            message="401 Unauthorized: Invalid Hugging Face token.",
                            latency_ms=latency,
                        )
                    return VerifyKeyResponse(
                        ok=False,
                        message=f"Hugging Face returned HTTP {resp.status_code}: {resp.text[:120]}",
                        latency_ms=latency,
                    )

                else:
                    return VerifyKeyResponse(
                        ok=False,
                        message=(
                            f"Unknown provider '{provider}'. "
                            "Supported: openrouter, openai_compatible, "
                            "groq, assemblyai, huggingface"
                        ),
                        latency_ms=0,
                    )

        except httpx.TimeoutException:
            latency = int((time.monotonic() - t0) * 1000)
            return VerifyKeyResponse(
                ok=False,
                message="Connection timed out after 8 seconds. Check network or host address.",
                latency_ms=latency,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            latency = int((time.monotonic() - t0) * 1000)
            return VerifyKeyResponse(
                ok=False,
                message="Connection refused: Target host is unreachable or not running.",
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
        data_dir = settings.get_effective_data_dir()
        mirror_file = data_dir / "settings.json"
        if mirror_file.exists():
            try:
                mirror_file.unlink()
            except OSError:
                pass

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
