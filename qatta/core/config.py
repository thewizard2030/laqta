"""Laqta core configuration (Pydantic v2 BaseSettings, env prefix QATTA_).

Scope: the ``qatta`` core pipeline package (this coexists with the FastAPI
backend's own settings; both use the ``QATTA_`` env prefix but are separate
processes/apps).

Policy notes enforced by defaults:
- Transcription is LOCAL first. ``groq_api`` (cloud) requires an explicit
  opt-in flag AND credentials. ``youtube_subs_first`` fetches the
  platform's own caption track (no media download in Pass 1). URL ingestion
  is available by default, but the ``QATTA_ENABLE_URL_INGESTION=false``
  opt-out is always honored and a user-facing per-import rights
  confirmation stays mandatory. See ``docs/POLICY.md``.
- The captions-first flow skips local Whisper for YouTube sources and
  downloads ONLY ranking-selected clip sections (s05b) for local Pass 2
  word timing. Real per-stage wall time is measured and persisted in
  ``stage_timings_ms`` — performance claims must reference that
  measurement, never invented numbers.
- Deterministic local fallback is required, so ``local_turbo`` is the
  default backend.
- The large-v3-turbo CT2 model named by the rules is memory-heavy; on an
  8 GB machine prefer QATTA_TURBO_MODEL with a smaller CT2 model (tiny/base)
  or run ``large-v3-turbo`` only when free RAM allows. Always configurable.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TranscriptionBackend = Literal["local_turbo", "groq_api", "youtube_subs_first"]
LLM_PROVIDER = Literal["ollama", "gemini", "openai_compatible", "openrouter"]

# Rule 4: Pass 2 re-runs word timing on selected clips with a padding buffer.
PASS2_PADDING_MS = 3_000


class QattaSettings(BaseSettings):
    """Pipeline-wide settings, overridable via ``QATTA_`` env vars / .env."""

    model_config = SettingsConfigDict(
        env_prefix="QATTA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Transcription (Pass 1 / Pass 2) ---------------------------------
    transcription_backend: TranscriptionBackend = "local_turbo"
    # CT2 model directory or HF id. The rules name the large-v3-turbo CT2
    # model, but that is heavy for 8 GB RAM, so the model is configurable.
    turbo_model: str = "deepdml/faster-whisper-large-v3-turbo-ct2"
    # Batched decoding exists in faster-whisper (BatchedInferencePipeline);
    # None = auto-tune: 16 on CUDA, 4 on CPU (the 8 GB-safe default).
    turbo_batch_size: int | None = Field(default=None, ge=1, le=64)
    # None = auto: "int8_float16" on CUDA, "int8" on CPU.
    turbo_compute_type: str | None = None
    turbo_beam_size: int = Field(default=1, ge=1, le=5)

    # Groq API (cloud, OPTIONAL; requires an explicit key AND opt-in).
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_transcribe_model: str = "whisper-large-v3"
    # Explicit-enabled gate: cloud transcription must never run silently.
    allow_cloud_apis: bool = Field(
        default=False,
        description=(
            "Explicit opt-in required before any cloud transcription backend "
            "(groq_api) executes. Transcript text leaves the device when "
            "enabled — surfaced to users as a disclosure."
        ),
    )

    # YouTube captions-first (``youtube_subs_first`` backend): the caption
    # track is fetched WITHOUT downloading the media (yt-dlp skip_download),
    # and only the ranking-selected clip sections are downloaded later.
    youtube_sub_languages: str = Field(
        default="ar,en",
        description=(
            "Comma-separated caption language preference (first match "
            "wins; manual subs preferred over auto-generated)."
        ),
    )
    youtube_fetch_timeout_seconds: float = Field(default=120.0, gt=0)
    # URL ingestion (yt-dlp) — PRD FR-12. The platform-policy/rights
    # review was completed by owner decision on 2026-10-19; callers must
    # still confirm the user owns the content or has permission (a UI
    # confirmation requirement, not an env flag).
    enable_url_ingestion: bool = Field(
        default=True,
        description=(
            "URL ingestion via yt-dlp (PRD FR-12). Default ON since the "
            "FR-12 policy review was completed by owner decision "
            "(2026-10-19); user-facing rights confirmation remains "
            "mandatory in the backend/UI flow."
        ),
    )

    # --- LLM provider selection (rule 3: never output timestamps) ---------
    llm_provider: LLM_PROVIDER = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434/v1"  # Ollama default
    llm_model: str = "qwen2.5:7b-instruct"
    llm_api_key: str | None = None  # gemini/openai_compatible; never logged
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    # When the LLM is unreachable or returns nothing usable, stages must
    # degrade to the deterministic heuristic candidate generator instead
    # of failing (enabled by default; disable for strict LLM-only runs).
    llm_fallback_enabled: bool = True
    # Arablish-aware prompt keeps English technical terms in Latin script.
    arabish_initial_prompt: bool = True
    arabish_prompt_text: str = (
        "محاضرة وبودكاست باللهجة المصرية والعربية مع مصطلحات تقنية مثل "
        "AI, API, SaaS, Startup, Deployment, Marketing, ROI."
    )

    # --- OpenRouter (CLOUD, optional, fail-closed) --------------------------
    # OpenRouter proxies many hosted models behind one OpenAI-compatible API
    # (https://openrouter.ai/api/v1). Models whose id ends with ":free" are
    # offered at zero price, but the free pool is rate limited (a 429 is a
    # normal, expected outcome — the deterministic local generator stays the
    # fallback). Selecting this provider sends transcript text to a hosted
    # service, so it requires ``allow_cloud_apis`` AND a key.
    llm_openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_openrouter_model: str = "minimax/minimax-m3.1-flash:free"
    llm_openrouter_api_key: str | None = None  # secret; header-only transport
    # OpenRouter uses these to attribute the app on its dashboard; they are
    # not secrets and are sent as plain headers.
    llm_openrouter_site_url: str = "http://127.0.0.1:5173"
    llm_openrouter_app_title: str = "Laqta"

    # --- Stage s01_ingest ---------------------------------------------------
    ffmpeg_timeout_seconds: float = Field(default=600.0, gt=0)

    # --- Pass 1 pause segmentation (Stage s02) ------------------------------
    # Real acoustic pauses shorter than this do NOT split utterances.
    pause_split_ms: int = Field(default=350, ge=50, le=5_000)

    # --- Pass 2 word alignment on winners (fine_pass) ------------------------
    fine_padding_ms: int = Field(default=2000, ge=0)
    fine_beam_size: int = Field(default=2, ge=1, le=5)
    snap_pad_ms: int = Field(default=120, ge=0, le=1_000)

    # --- Groq cloud adapter (OPTIONAL; fail-closed) --------------------------
    groq_chunk_seconds: int = Field(default=900, ge=30, le=1800)
    groq_max_concurrency: int = Field(default=4, ge=1, le=16)
    groq_timeout_seconds: float = Field(default=120.0, gt=0)

    # --- Stage s04 candidate windows ----------------------------------------
    sliding_window_sec: int = Field(default=900, ge=60)  # 15 minutes
    sliding_overlap_sec: int = Field(default=120, ge=0, le=600)  # 2 minutes
    max_winners: int = Field(default=5, ge=1, le=50)

    # --- Stage s05 gate thresholds (heuristic, documented) -------------------
    boundary_pause_ms: int = Field(default=200, ge=0)
    boundary_rms_contrast: float = Field(default=1.25, gt=0)
    snap_search_ms: int = Field(default=3000, ge=0)

    # --- Clip geometry -----------------------------------------------------
    min_clip_sec: int = Field(default=28, ge=5)
    max_clip_sec: int = Field(default=58, ge=10, le=180)
    video_max_clip_sec: int = Field(
        default=180,
        ge=58,
        description="Absolute upper bound (configurable up to 180 s).",
    )

    # --- Storage ------------------------------------------------------------
    data_dir: Path = Path.home() / ".local" / "share" / "qatta"
    ffprobe_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, v: str | Path) -> Path:
        import os

        return Path(os.path.expanduser(str(v))).resolve()

    @model_validator(mode="after")
    def _check_ranges(self) -> "QattaSettings":
        if self.min_clip_sec >= self.max_clip_sec:
            raise ValueError(
                f"min_clip_sec ({self.min_clip_sec}) must be < max_clip_sec ({self.max_clip_sec})."
            )
        if self.max_clip_sec > self.video_max_clip_sec:
            raise ValueError(
                f"max_clip_sec ({self.max_clip_sec}) exceeds the absolute "
                f"cap ({self.video_max_clip_sec})."
            )
        return self

    @model_validator(mode="after")
    def _apply_openrouter_defaults(self) -> "QattaSettings":
        """Point the generic LLM fields at OpenRouter when it is selected.

        Selecting ``llm_provider="openrouter"`` must be enough to work, so the
        shared ``llm_base_url`` / ``llm_model`` fields follow the OpenRouter
        defaults — but only while the user left them at the Ollama defaults.
        An explicit ``QATTA_LLM_BASE_URL`` / ``QATTA_LLM_MODEL`` always wins.
        """
        if self.llm_provider != "openrouter":
            return self
        if self.llm_base_url == "http://127.0.0.1:11434/v1":
            self.llm_base_url = self.llm_openrouter_base_url
        if self.llm_model == "qwen2.5:7b-instruct":
            self.llm_model = self.llm_openrouter_model
        return self

    def openrouter_api_key_configured(self) -> bool:
        """Secret-free probe: is a usable OpenRouter key present?"""
        return bool(self.llm_openrouter_api_key)

    def youtube_sub_language_list(self) -> list[str]:
        """Parsed caption-language preference (order preserved)."""
        return [chunk.strip() for chunk in self.youtube_sub_languages.split(",") if chunk.strip()]

    def backend_is_gated(self) -> bool:
        """True when the selected backend is a cloud/youtube one that has
        NOT been explicitly opted in. Stages must refuse to run and surface
        an honest, actionable message instead."""
        if self.transcription_backend == "local_turbo":
            return False
        return not self.cloud_backend_permitted(self.transcription_backend)

    def cloud_backend_permitted(self, backend: str) -> bool:
        """Fail-closed helper: cloud backends require explicit opt-in."""
        if backend == "groq_api":
            return self.allow_cloud_apis and bool(self.groq_api_key)
        if backend == "youtube_subs_first":
            return self.enable_url_ingestion
        return backend == "local_turbo"

    def manifest_path(self, project_id: str) -> Path:
        """Manifest location: <data_dir>/projects/<id>/qatta_manifest.json."""
        safe = Path(project_id).name
        return self.data_dir / "projects" / safe / "qatta_manifest.json"
