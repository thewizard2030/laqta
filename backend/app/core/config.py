"""Application configuration settings for Laqta."""

import os
import shutil
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logging import logger


class Settings(BaseSettings):
    """Laqta application settings."""

    # Server binding (strictly local-only by default)
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Application metadata
    APP_NAME: str = "Laqta"
    # The version is NOT a setting: it comes from the `qatta` core package
    # (`qatta.__version__`), the single source of truth. An environment
    # variable must never be able to make the API report a different
    # version than the code it runs.
    DEBUG: bool = False
    ENV: str = "development"

    # CORS configuration (strictly explicit, no wildcard allowed)
    CORS_ORIGINS: list[str] | str = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # Storage paths (Linux default: ~/.local/share/qatta)
    DATA_DIR: Path = Path.home() / ".local" / "share" / "qatta"

    # Upload and media constraints
    MAX_UPLOAD_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GB default
    MIN_FREE_DISK_BYTES: int = 200 * 1024 * 1024  # 200 MB safety buffer
    ALLOWED_MEDIA_EXTENSIONS: set[str] = {".mp4", ".mov", ".mkv", ".webm"}

    # Processing and job configuration (protecting 8 GB RAM)
    DEFAULT_JOB_WORKERS: int = 1
    FFMPEG_TIMEOUT_SECONDS: int = 300
    CLEAN_INTERMEDIATE_WAV: bool = False

    # ASR / Transcription configuration (conservative CPU-first defaults)
    DEFAULT_WHISPER_MODEL: str = "base"
    DEFAULT_WHISPER_DEVICE: str = "cpu"
    DEFAULT_WHISPER_COMPUTE_TYPE: str = "int8"
    ALLOWED_WHISPER_MODELS: tuple[str, ...] = (
        "tiny",
        "base",
        "small",
        "medium",
        "large-v3",
        "large-v3-turbo",
    )
    WHISPER_BEAM_SIZE: int = 1  # 1 for fast greedy decoding (3x faster than 5 on CPU)
    WHISPER_VAD_FILTER: bool = True  # Silero VAD to skip non-speech pauses and ambient gaps
    WHISPER_CPU_THREADS: int = 4  # Maximize CPU core throughput without thrashing

    # Two-pass transcription performance profiles (docs/PERFORMANCE.md).
    # "fast" (default): base/int8/beam1 and NO word-level alignment over the
    #   full video; word timing is re-derived per selected clip at render time.
    # "balanced": small/int8 for better Arabic accuracy; still no full-video
    #   word alignment.
    # "accurate": configurable higher-accuracy model; explicitly slower.
    DEFAULT_WHISPER_PROFILE: str = "fast"
    FAST_WHISPER_MODEL: str = "base"
    BALANCED_WHISPER_MODEL: str = "small"
    ACCURATE_WHISPER_MODEL: str = "medium"

    # Pass B: clip-scoped word re-timing for animated word-by-word captions.
    # Only selected clips (~30-55 s) are processed, never the full video.
    # This keeps peak RAM bounded and adds real model load only when needed.
    CLIP_ALIGNMENT_ENABLED: bool = True
    # "small" is noticeably better than "base" on Arabic (the base model
    # mangles Arabic words, e.g. "ليه مش هنحارب" -> "لم يشهن حارب") and
    # the pass only ever runs on the 30-55 s winning clip, so the extra
    # CPU time stays bounded.
    CLIP_ALIGNMENT_MODEL: str = "small"
    CLIP_ALIGNMENT_BEAM_SIZE: int = 5
    MAX_CLIP_ALIGNMENT_SECONDS: float = 120.0
    # Optional clip alignment model compute type override; defaults to the
    # global DEFAULT_WHISPER_COMPUTE_TYPE.
    CLIP_ALIGNMENT_COMPUTE_TYPE: str | None = None

    # Transcript result cache (docs/PERFORMANCE.md §cache). Content-addressed
    # by the extracted 16 kHz WAV fingerprint plus transcription settings and
    # a schema version. Lives under the data dir, never in source code dirs.
    TRANSCRIPT_CACHE_ENABLED: bool = True

    # Optional LLM reranking (PRD §5 FR-05/FR-11). Disabled by default: the
    # deterministic baseline must work with no provider at all.
    LLM_RANKER_ENABLED: bool = False
    # Which adapter to use for reranking: "openai_compatible" (LOCAL servers
    # such as Ollama/LM Studio) or "openrouter" (HOSTED gateway).
    LLM_PROVIDER: str = "openai_compatible"
    # OpenAI-compatible LOCAL server (Ollama/LM Studio/llama.cpp/vLLM). Loopback
    # by default; changing this to a remote host is a deliberate user action.
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_MODEL: str = "qwen2.5:7b-instruct"
    # Secret. Read from env/.env only; never logged, never returned via API.
    LLM_API_KEY: str | None = None
    # OpenRouter (HOSTED, optional, fail-closed). One OpenAI-compatible
    # gateway in front of many models; ids ending in ":free" are zero price
    # but share a rate-limited upstream pool, so a 429 is an expected,
    # recoverable state (the deterministic baseline stays the fallback).
    LLM_OPENROUTER_API_KEY: str | None = None
    LLM_OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_OPENROUTER_MODEL: str = "minimax/minimax-m3.1-flash:free"
    # Public attribution metadata (not secrets) shown on OpenRouter's
    # dashboard: they are sent as plain HTTP headers.
    LLM_OPENROUTER_SITE_URL: str = "http://127.0.0.1:5173"
    LLM_OPENROUTER_APP_TITLE: str = "Laqta"
    # Bounded request limits (defense in depth; ranker clamps further).
    LLM_TIMEOUT_SECONDS: float = 20.0
    LLM_MAX_OUTPUT_TOKENS: int = 1_200
    LLM_MAX_RETRIES: int = 1
    LLM_MAX_CANDIDATES: int = 12
    # Hosted providers (cloud) require this explicit opt-in. When a hosted
    # adapter is selected the UI must surface TRANSCRIPT_LEAVES_DEVICE_NOTICE
    # before any request leaves the device (PRD §9).
    LLM_HOSTED_OPT_IN: bool = False

    # URL ingestion (yt-dlp) — PRD FR-12. The platform-policy/rights review
    # was completed by owner decision on 2026-10-19, so ingestion is ON by
    # default. Every import STILL requires the explicit per-request rights
    # confirmation from the user, and the opt-out flag is always honored
    # (nothing may run when this is false — fail-closed).
    ENABLE_URL_INGESTION: bool = True
    # Whole-download deadline for the yt-dlp subprocess (argument array only).
    URL_INGEST_TIMEOUT_SECONDS: float = 1800.0
    # Preferred subtitle languages for URL ingestion (no 'all' to avoid YouTube 429 rate limits)
    URL_INGEST_SUB_LANGUAGES: str = "ar.*,ar,en.*,en"
    # YouTube player client strategy to prevent HTTP 403 Forbidden / "Did not get any data blocks"
    YT_DLP_PLAYER_CLIENT: str = "android,ios,web"
    # Optional cookies file path for authenticated or bot-gated YouTube downloads
    YT_DLP_COOKIES_PATH: str | None = None
    # Optional browser name to extract cookies from (e.g. 'firefox', 'chrome')
    YT_DLP_COOKIES_FROM_BROWSER: str | None = None
    # Command execution timeout for `yt-dlp --version` capability probes.
    YT_DLP_PROBE_TIMEOUT_SECONDS: float = 10.0
    # Native pure-Python YouTube transcript extraction (Innertube timedtext)
    ENABLE_NATIVE_YOUTUBE_TRANSCRIPT: bool = True
    # Auto-enqueue local Whisper transcription if no subtitles were found during URL ingest
    AUTO_TRANSCRIBE_ON_INGEST_FALLBACK: bool = True

    # Multi-engine transcription & cloud provider settings (PRD privacy & reliability)
    DEFAULT_TRANSCRIPTION_BACKEND: str = "faster-whisper"
    ALLOW_CLOUD_APIS: bool = False
    GROQ_API_KEY: str | None = None

    GROQ_MODEL: str = "whisper-large-v3-turbo"
    ASSEMBLYAI_API_KEY: str | None = None
    HF_TOKEN: str | None = None
    HF_WHISPER_MODEL: str = "openai/whisper-large-v3-turbo"
    WHISPER_CPP_PATH: str | None = None
    WHISPER_CPP_MODEL_PATH: str | None = None

    def groq_api_key_configured(self) -> bool:
        return bool(self.GROQ_API_KEY)

    def assemblyai_api_key_configured(self) -> bool:
        return bool(self.ASSEMBLYAI_API_KEY)

    def hf_token_configured(self) -> bool:
        return bool(self.HF_TOKEN)

    def llm_api_key_configured(self) -> bool:
        """Secret-free status probe for capabilities/UI (never returns the key)."""
        if self.LLM_PROVIDER == "openrouter":
            return bool(self.LLM_OPENROUTER_API_KEY)
        return bool(self.LLM_API_KEY)

    def llm_provider_is_hosted(self) -> bool:
        """True when the selected LLM adapter sends data to a hosted service.

        Hosted adapters require the explicit ``LLM_HOSTED_OPT_IN`` opt-in and
        the transcript-leaves-device disclosure (PRD §9, FR-11).
        """
        return self.LLM_PROVIDER == "openrouter"

    @property
    def redacted_openrouter_key(self) -> str:
        return redact_secret(self.LLM_OPENROUTER_API_KEY)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            origins = [item.strip() for item in v.split(",") if item.strip()]
        elif isinstance(v, list):
            origins = [str(item).strip() for item in v if str(item).strip()]
        else:
            origins = ["http://127.0.0.1:5173", "http://localhost:5173"]

        # Security check: never allow wildcard CORS
        if "*" in origins:
            raise ValueError("Wildcard '*' CORS origin is strictly forbidden for security.")
        return origins

    @field_validator("DATA_DIR", mode="before")
    @classmethod
    def expand_data_dir(cls, v: str | Path) -> Path:
        if isinstance(v, str):
            return Path(os.path.expanduser(v)).resolve()
        return Path(v).expanduser().resolve()

    def get_effective_data_dir(self) -> Path:
        """Return a verified writable data directory.

        Attempts to use configured DATA_DIR; falls back to workspace-local './data'
        if the primary directory is read-only (e.g., in restricted sandboxes).
        """
        candidate = Path(self.DATA_DIR)
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            return candidate
        except (OSError, PermissionError):
            fallback = Path.cwd() / "data"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def get_db_path(self) -> Path:
        """Return absolute path to SQLite database."""
        return self.get_effective_data_dir() / "qatta.db"

    def get_project_dir(self, project_id: str) -> Path:
        """Return controlled, server-managed project directory.

        Never trusts client paths; uses strictly validated project IDs.
        """
        safe_id = Path(project_id).name
        p_dir = self.get_effective_data_dir() / "projects" / safe_id
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def get_project_media_dir(self, project_id: str) -> Path:
        """Return controlled media directory for a specific project."""
        media_dir = self.get_project_dir(project_id) / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir

    def get_media_thumbs_dir(self, project_id: str, media_id: str) -> Path:
        """Return controlled thumbnail cache directory for one media asset.

        Uses strictly validated media IDs (never client paths), mirroring the
        project/media directories above.
        """
        safe_media_id = Path(media_id).name
        thumbs_dir = self.get_project_dir(project_id) / "thumbs" / safe_media_id
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        return thumbs_dir

    def get_job_temp_dir(self, project_id: str, job_id: str) -> Path:
        """Return isolated temporary directory for a specific job."""
        safe_job_id = Path(job_id).name
        temp_dir = self.get_project_dir(project_id) / "temp" / safe_job_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def cleanup_job_temp_dir(self, project_id: str, job_id: str) -> bool:
        """Remove a job's temp directory after cancellation.

        Only files inside the per-job temp directory are touched (never the
        media or render output directories), so cancellation can never
        delete user work.
        """
        safe_job_id = Path(job_id).name
        temp_dir = self.get_project_dir(project_id) / "temp" / safe_job_id
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned job temp dir: {temp_dir}")
                return True
        except Exception as e:  # pragma: no cover - rm failures are non-fatal
            logger.warning(f"Failed to clean temp dir {temp_dir}: {e}")
        return False

    def get_project_renders_dir(self, project_id: str) -> Path:
        """Return controlled output directory for rendered clips (FR-09).

        Rendered outputs are stored separately from source media.
        """
        renders_dir = self.get_project_dir(project_id) / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)
        return renders_dir

    def get_project_captions_dir(self, project_id: str) -> Path:
        """Return controlled directory for generated caption files (FR-08)."""
        captions_dir = self.get_project_dir(project_id) / "captions"
        captions_dir.mkdir(parents=True, exist_ok=True)
        return captions_dir

    def get_job_audio_path(self, project_id: str, job_id: str) -> Path:
        """Return target path for extracted 16kHz mono WAV audio."""
        return self.get_job_temp_dir(project_id, job_id) / "audio_16k.wav"

    def get_whisper_models_dir(self) -> Path:
        """Return controlled local cache directory for faster-whisper model weights."""
        models_dir = self.get_effective_data_dir() / "models" / "whisper"
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir

    def get_transcript_cache_dir(self) -> Path:
        """Return controlled directory for cached transcription results.

        Kept under the data directory (never inside source code dirs) with a
        deterministic layout: cache/transcripts/<fingerprint>.json.
        """
        cache_dir = self.get_effective_data_dir() / "cache" / "transcripts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def check_available_space(self, target_dir: Path, required_bytes: int) -> bool:
        """Verify whether sufficient disk space is available."""
        try:
            stat = shutil.disk_usage(target_dir)
            return stat.free >= (required_bytes + self.MIN_FREE_DISK_BYTES)
        except Exception:
            return True

    def get_transcripts_cache_dir(self) -> Path:
        """Alias for get_transcript_cache_dir."""
        return self.get_transcript_cache_dir()

    @property
    def redacted_groq_key(self) -> str:
        return redact_secret(self.GROQ_API_KEY)

    @property
    def redacted_assemblyai_key(self) -> str:
        return redact_secret(self.ASSEMBLYAI_API_KEY)

    @property
    def redacted_hf_token(self) -> str:
        return redact_secret(self.HF_TOKEN)

    model_config = SettingsConfigDict(
        env_prefix="QATTA_",
        # The repo-root .env holds the shared settings/keys for both the API
        # and the core pipeline; a local backend/.env may override them.
        # (In pydantic-settings the LAST file wins for duplicate keys.)
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def redact_secret(secret: str | None) -> str:
    """Safely redact secret tokens and API keys for logs and diagnostic displays."""
    if not secret:
        return "<none>"
    s = secret.strip()
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}...{s[-4:]}"
