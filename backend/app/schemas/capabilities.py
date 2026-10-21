"""System capabilities schema for honest runtime detection."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.transcription import ProviderCapabilityInfo
from qatta import __version__


class BinaryCapability(BaseModel):
    """Detection result for a system CLI binary."""

    available: bool = Field(..., description="Whether binary is installed and executable")
    path: str | None = Field(default=None, description="Absolute path to executable binary")
    version: str | None = Field(default=None, description="Detected version string")
    details: str | None = Field(default=None, description="Optional diagnostic details")


class FFmpegCapability(BinaryCapability):
    """Detection result for FFmpeg including libass filter check."""

    has_libass: bool = Field(
        default=False,
        description="Whether FFmpeg includes libass support for subtitle rendering",
    )


class AsrCapabilities(BaseModel):
    """Speech recognition backend availability."""

    faster_whisper: bool = Field(
        default=False,
        description="Whether faster-whisper library is installed",
    )
    whisperx: bool = Field(
        default=False,
        description="Whether whisperX library is installed",
    )
    whisper_cpp: bool = Field(
        default=False,
        description="Whether whisper.cpp binary is installed",
    )
    cloud_apis_allowed: bool = Field(
        default=False,
        description="Whether cloud transcription backends are enabled by the user",
    )
    active_provider: str = Field(
        default="faster-whisper",
        description="Default active ASR provider name",
    )
    providers: list[ProviderCapabilityInfo | dict[str, Any]] = Field(
        default_factory=list,
        description="List of all supported engines and their capabilities",
    )


class LlmCapabilities(BaseModel):
    """Optional LLM adapter availability (secret-free; never exposes keys)."""

    openai_compatible: bool = Field(
        default=True,
        description="Whether local OpenAI-compatible endpoints can be called",
    )
    provider: str = Field(
        default="openai_compatible",
        description=(
            "Configured LLM adapter: 'openai_compatible' (local server) or "
            "'openrouter' (hosted gateway). Never a secret."
        ),
    )
    ranker_enabled: bool = Field(
        default=False,
        description="Whether LLM reranking is enabled (deterministic baseline is default)",
    )
    base_url: str | None = Field(
        default=None,
        description="Configured OpenAI-compatible endpoint (no secrets)",
    )
    model: str | None = Field(
        default=None,
        description="Configured model name (no secrets)",
    )
    api_key_configured: bool = Field(
        default=False,
        description="Whether an API key is configured (boolean only, never the key)",
    )
    hosted_opt_in: bool = Field(
        default=False,
        description="Whether a hosted (cloud) provider is opted in; requires UI disclosure",
    )
    free_models: list[str] = Field(
        default_factory=list,
        description=(
            "Curated list of zero-price model ids the hosted gateway offers "
            "(ids ending in ':free'). Informational only."
        ),
    )
    disclosure: str | None = Field(
        default=None,
        description="Opt-in disclosure text shown when transcript text leaves the device",
    )


class HardwareCapabilities(BaseModel):
    """Hardware environment detection."""

    device: str = Field(default="cpu", description="Primary compute device (cpu or cuda)")
    cuda_available: bool = Field(default=False, description="Whether NVIDIA CUDA is available")
    cuda_device_name: str | None = Field(default=None, description="Name of detected CUDA GPU")
    cuda_device_count: int = Field(default=0, description="Number of detected CUDA GPUs")
    compute_type: str = Field(default="int8", description="Default compute precision")
    model: str = Field(default="base", description="Default Whisper model size")
    precision: str = Field(default="int8", description="Model compute precision")
    fallback_reason: str | None = Field(default=None, description="Reason if fallen back to CPU")
    recommended_worker_concurrency: int = Field(
        default=1,
        description="Recommended job concurrency (1 by default for 8 GB RAM target)",
    )


class StorageCapabilities(BaseModel):
    """Local storage state."""

    data_dir: str = Field(..., description="Configured local data directory")
    exists: bool = Field(..., description="Whether data directory exists")
    writable: bool = Field(..., description="Whether data directory is writable")


class UrlIngestionCapabilities(BaseModel):
    """URL ingestion (yt-dlp) capability — PRD FR-12, fail-closed."""

    enabled: bool = Field(
        ...,
        description=(
            "Whether URL ingestion is fully available: requires "
            "QATTA_ENABLE_URL_INGESTION (disabled by default — an operator "
            "must opt in) AND an installed yt-dlp. Every import still "
            "requires the per-request rights confirmation."
        ),
    )
    feature_flag: bool = Field(
        default=False,
        description=(
            "Whether QATTA_ENABLE_URL_INGESTION is enabled (regardless of yt-dlp availability)"
        ),
    )
    yt_dlp: BinaryCapability = Field(..., description="yt-dlp binary capability")
    notice: str | None = Field(
        default=None,
        description="Honest explanation of the current disabled/partial state",
    )


class CapabilitiesResponse(BaseModel):
    """Full system capability report."""

    app_name: str = "Laqta"
    version: str = __version__
    local_only: bool = Field(
        default=True,
        description="Whether all processing runs strictly on local device",
    )
    ffmpeg: FFmpegCapability = Field(..., description="FFmpeg binary capability")
    ffprobe: BinaryCapability = Field(..., description="FFprobe binary capability")
    asr: AsrCapabilities = Field(..., description="Speech-to-text capabilities")
    llm: LlmCapabilities = Field(..., description="LLM adapter capabilities")
    hardware: HardwareCapabilities = Field(..., description="Hardware capabilities")
    storage: StorageCapabilities = Field(..., description="Local storage capabilities")
    url_ingestion: UrlIngestionCapabilities = Field(
        ..., description="URL ingestion (yt-dlp) capability (PRD FR-12, reviewed 2026-10-19)"
    )
