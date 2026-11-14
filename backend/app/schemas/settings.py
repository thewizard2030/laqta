"""Schemas for user settings and Bring Your Own Keys (BYOK) management."""

from typing import Any

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Current effective application settings and masked secrets status."""

    # Server & Metadata
    app_name: str = Field(..., description="Application display name")
    version: str = Field(..., description="Application version from qatta core")

    # Cloud Consent & Policies
    allow_cloud_apis: bool = Field(
        ...,
        description="Master switch allowing cloud/hosted external API calls",
    )
    llm_hosted_opt_in: bool = Field(
        ...,
        description="Explicit user consent for hosted LLM reranking",
    )
    enable_url_ingestion: bool = Field(
        ...,
        description="Whether URL ingestion via yt-dlp is enabled",
    )

    # LLM & Reasoning (BYOK)
    llm_ranker_enabled: bool = Field(..., description="Whether LLM reranker is active")
    llm_provider: str = Field(
        ...,
        description="Active LLM provider adapter: 'openrouter', 'openai_compatible', 'groq'",
    )
    llm_base_url: str = Field(..., description="Base URL for local/custom OpenAI-compatible API")
    llm_model: str = Field(..., description="Model name for OpenAI-compatible endpoint")
    llm_openrouter_base_url: str = Field(..., description="Base URL for OpenRouter")
    llm_openrouter_model: str = Field(..., description="Model name for OpenRouter")
    llm_api_key_configured: bool = Field(..., description="Whether LLM API key is configured")
    redacted_llm_api_key: str = Field(..., description="Masked preview of LLM API key")
    llm_openrouter_api_key_configured: bool = Field(
        ..., description="Whether OpenRouter API key is configured"
    )
    redacted_openrouter_api_key: str = Field(
        ..., description="Masked preview of OpenRouter API key"
    )
    free_models: list[str] = Field(
        default_factory=list,
        description="Curated zero-cost models available on OpenRouter",
    )

    # Speech Recognition (ASR)
    default_transcription_backend: str = Field(
        ..., description="Default backend: 'faster-whisper', 'groq_api', 'youtube_subs_first'"
    )
    default_whisper_profile: str = Field(
        ..., description="Whisper profile: 'fast', 'balanced', 'accurate'"
    )
    default_whisper_model: str = Field(..., description="Default whisper model")
    fast_whisper_model: str = Field(..., description="Model used for 'fast' profile")
    balanced_whisper_model: str = Field(..., description="Model used for 'balanced' profile")
    accurate_whisper_model: str = Field(..., description="Model used for 'accurate' profile")
    default_whisper_device: str = Field(..., description="'cpu' or 'cuda'")
    default_whisper_compute_type: str = Field(..., description="'int8' or 'float16'")
    whisper_vad_filter: bool = Field(..., description="Silero VAD speech filtering")
    whisper_beam_size: int = Field(..., description="Whisper beam size")
    whisper_cpu_threads: int = Field(..., description="Worker CPU threads")

    # Cloud Transcription (BYOK)
    groq_model: str = Field(..., description="Groq Whisper model")
    groq_api_key_configured: bool = Field(..., description="Whether Groq API key is configured")
    redacted_groq_api_key: str = Field(..., description="Masked preview of Groq API key")
    assemblyai_api_key_configured: bool = Field(
        ..., description="Whether AssemblyAI key is configured"
    )
    redacted_assemblyai_api_key: str = Field(
        ..., description="Masked preview of AssemblyAI API key"
    )
    hf_token_configured: bool = Field(..., description="Whether HuggingFace token is configured")
    redacted_hf_token: str = Field(..., description="Masked preview of HuggingFace token")

    # Arabic & Alignment
    clip_alignment_enabled: bool = Field(
        ..., description="Pass 2 word-level timing on selected clips"
    )
    clip_alignment_model: str = Field(..., description="Model for clip alignment")
    max_clip_alignment_seconds: float = Field(
        ..., description="Max clip length allowed for word alignment"
    )
    arabish_initial_prompt: bool = Field(
        default=True,
        description="Whether to include Arablish technical terms in transcription prompt",
    )
    arabish_prompt_text: str = Field(
        default=(
            "محاضرة وبودكاست باللهجة المصرية والعربية مع مصطلحات تقنية مثل "
            "AI, API, SaaS, Startup, Deployment, Marketing, ROI."
        ),
        description="Initial prompt injected into Whisper for code-switching",
    )

    # Ingestion & Video
    youtube_sub_languages: str = Field(..., description="Preferred subtitle languages")
    yt_dlp_player_client: str = Field(..., description="yt-dlp player clients order")
    yt_dlp_cookies_path: str | None = Field(default=None, description="Path to cookies.txt")
    yt_dlp_cookies_from_browser: str | None = Field(
        default=None, description="Browser to extract cookies from"
    )
    ffmpeg_timeout_seconds: int = Field(..., description="FFmpeg execution timeout")

    # Storage & Cache
    data_dir: str = Field(..., description="Data directory path")
    db_path: str = Field(..., description="SQLite database path")
    transcript_cache_enabled: bool = Field(..., description="Whether transcript cache is enabled")
    cached_transcripts_count: int = Field(..., description="Number of cached transcripts")
    cached_transcripts_bytes: int = Field(..., description="Total size of transcript cache")
    disk_total_bytes: int = Field(..., description="Total volume storage bytes")
    disk_free_bytes: int = Field(..., description="Available storage bytes")
    disk_used_bytes: int = Field(..., description="Used storage bytes")


class SettingsUpdateRequest(BaseModel):
    """Partial update payload for user settings.

    For secret key fields:
    - Setting a non-empty string updates the key.
    - Setting an empty string `""` clears/removes the key.
    - Omitted or None leaves the existing key unchanged.
    """

    # Cloud Consent & Policies
    allow_cloud_apis: bool | None = None
    llm_hosted_opt_in: bool | None = None
    enable_url_ingestion: bool | None = None

    # LLM & BYOK Keys
    llm_ranker_enabled: bool | None = None
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_openrouter_base_url: str | None = None
    llm_openrouter_model: str | None = None
    llm_openrouter_api_key: str | None = None

    # ASR & Whisper
    default_transcription_backend: str | None = None
    default_whisper_profile: str | None = None
    default_whisper_model: str | None = None
    fast_whisper_model: str | None = None
    balanced_whisper_model: str | None = None
    accurate_whisper_model: str | None = None
    default_whisper_device: str | None = None
    default_whisper_compute_type: str | None = None
    whisper_vad_filter: bool | None = None
    whisper_beam_size: int | None = None
    whisper_cpu_threads: int | None = None

    # Cloud Transcription Keys
    groq_api_key: str | None = None
    groq_model: str | None = None
    assemblyai_api_key: str | None = None
    hf_token: str | None = None

    # Arabic & Alignment
    clip_alignment_enabled: bool | None = None
    clip_alignment_model: str | None = None
    max_clip_alignment_seconds: float | None = None
    arabish_initial_prompt: bool | None = None
    arabish_prompt_text: str | None = None

    # Ingestion
    youtube_sub_languages: str | None = None
    yt_dlp_player_client: str | None = None
    yt_dlp_cookies_path: str | None = None
    yt_dlp_cookies_from_browser: str | None = None
    ffmpeg_timeout_seconds: int | None = None

    # Storage
    transcript_cache_enabled: bool | None = None


class VerifyKeyRequest(BaseModel):
    """Payload to test connection for a specific provider."""

    provider: str = Field(
        ...,
        description=(
            "Provider name: 'openrouter', 'openai_compatible', 'groq', 'assemblyai', 'huggingface'"
        ),
    )
    api_key: str | None = Field(
        default=None,
        description="Candidate API key to test. If omitted, tests the currently stored key.",
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL to test (e.g. for Ollama / LM Studio).",
    )
    model: str | None = Field(
        default=None,
        description="Optional model ID to verify.",
    )


class VerifyKeyResponse(BaseModel):
    """Result of provider connection verification probe."""

    ok: bool = Field(..., description="Whether the connection test succeeded")
    message: str = Field(..., description="Human-readable result or diagnostic error")
    latency_ms: int = Field(..., description="Roundtrip probe latency in milliseconds")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional extra details from probe"
    )
    models_found: list[str] | None = Field(
        default=None, description="List of available models returned by provider"
    )


class ClearCacheResponse(BaseModel):
    """Result of clearing the transcript cache."""

    cleared_files: int = Field(..., description="Number of files removed from cache")
    freed_bytes: int = Field(..., description="Total bytes freed")
    message: str = Field(..., description="Summary message")
