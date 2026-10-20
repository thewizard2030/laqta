"""Pydantic schemas for transcription requests, segments, and responses."""

from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    """Word-level timestamp representation."""

    word: str = Field(..., description="The spoken word token")
    start: float = Field(..., ge=0.0, description="Start time in seconds")
    end: float = Field(..., ge=0.0, description="End time in seconds")
    probability: float | None = Field(
        default=None, description="Confidence probability (0.0 - 1.0)"
    )


# Backward-compatible alias
TranscriptWord = WordTiming


class TranscriptSegment(BaseModel):
    """Transcript segment boundary and metadata."""

    id: str = Field(..., description="Unique segment identifier")
    start: float = Field(..., ge=0.0, description="Segment start time in seconds")
    end: float = Field(..., ge=0.0, description="Segment end time in seconds")
    text: str = Field(..., description="Transcribed text content")
    words: list[WordTiming] | None = Field(
        default=None,
        description="Optional word-level timings if available from provider",
    )
    speaker: str | None = Field(
        default=None,
        description="Optional speaker identifier (e.g. SPEAKER_00) if diarization is enabled",
    )
    avg_logprob: float | None = Field(default=None, description="Average log probability")
    no_speech_prob: float | None = Field(default=None, description="Probability of no speech")


class ProviderCapabilityInfo(BaseModel):
    """Detailed capability information for a transcription engine."""

    name: str = Field(default="", description="Provider unique identifier")
    provider: str = Field(default="", description="Provider unique identifier alias")
    display_name: str = Field(default="", description="Human-friendly provider title")
    is_local: bool = Field(default=True, description="True if inference runs completely locally")
    is_cloud: bool = Field(default=False, description="True if engine sends data to cloud")
    available: bool = Field(
        default=True, description="Whether engine dependencies and setup are ready"
    )
    active: bool = Field(default=False, description="Whether this is the currently active backend")
    device: str = Field(default="cpu", description="Active compute device (cpu or cuda)")
    cuda_available: bool = Field(default=False, description="Whether NVIDIA CUDA was detected")
    cuda_device_name: str | None = Field(default=None, description="NVIDIA CUDA device name")
    cuda_device_count: int = Field(default=0, description="NVIDIA CUDA device count")
    compute_type: str | None = Field(default=None, description="Compute precision")
    supported_models: list[str] = Field(
        default_factory=list, description="Supported Whisper model names"
    )
    models: list[str] = Field(default_factory=list, description="Supported model names alias")
    supports_word_timestamps: bool = Field(
        default=True, description="Whether engine can emit word timings"
    )
    supports_speaker_diarization: bool = Field(
        default=False, description="Whether engine emits speaker labels"
    )
    requires_api_key: bool = Field(default=False, description="Whether an API key is required")
    api_key_configured: bool = Field(default=False, description="Whether valid API key is present")
    disclosure_required: bool = Field(
        default=False, description="Whether user disclosure is required for cloud upload"
    )
    disclosure_text: str | None = Field(
        default=None, description="Disclosure message when audio leaves device"
    )
    privacy_disclosure: str | None = Field(default=None, description="Privacy disclosure alias")
    fallback_reason: str | None = Field(
        default=None, description="Reason if engine fell back to CPU"
    )
    details: str | None = Field(default=None, description="Diagnostic and configuration notes")

    def model_post_init(self, __context: object) -> None:
        if not self.name and self.provider:
            self.name = self.provider
        elif not self.provider and self.name:
            self.provider = self.name
        if not self.is_cloud and not self.is_local:
            self.is_cloud = True
        if self.is_cloud and not self.disclosure_required:
            self.disclosure_required = True
        if not self.disclosure_text and self.privacy_disclosure:
            self.disclosure_text = self.privacy_disclosure
        elif not self.privacy_disclosure and self.disclosure_text:
            self.privacy_disclosure = self.disclosure_text
        if not self.supported_models and self.models:
            self.supported_models = list(self.models)
        elif not self.models and self.supported_models:
            self.models = list(self.supported_models)


class TranscriptionRequest(BaseModel):
    """Request payload for enqueuing a transcription job."""

    model_size: str | None = Field(
        default=None,
        description=(
            "Whisper model size ('tiny', 'base', 'small', 'medium', "
            "'large-v3'). Overrides the selected performance profile."
        ),
    )
    language: str | None = Field(
        default=None,
        description="Optional 2-letter language code ('ar', 'en'). None enables auto-detection.",
    )
    word_timestamps: bool | None = Field(
        default=None,
        description=(
            "Force word-level timestamps on the full-video pass. None lets "
            "the selected profile decide (segment-level for 'fast' and "
            "'balanced', word-level for 'accurate')."
        ),
    )
    profile: str | None = Field(
        default=None,
        description=(
            "Performance profile: 'fast' (default: base/int8, no full-video "
            "word alignment), 'balanced' (small/int8), or 'accurate' "
            "(full-video word alignment; significantly slower)."
        ),
    )
    provider: str = Field(
        default="faster-whisper",
        description=(
            "ASR provider to use ('faster-whisper', 'whisper.cpp', 'groq', "
            "'assemblyai', 'huggingface', 'fake')"
        ),
    )

    beam_size: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="Beam search size (1 for fast greedy decoding, 5 for high precision)",
    )
    max_duration_sec: float | None = Field(
        default=None,
        ge=5.0,
        description="Optional maximum audio seconds to transcribe for rapid drafting",
    )


class TranscriptResponse(BaseModel):
    """Full transcript representation returned by API."""

    id: str
    media_id: str
    language: str
    provider: str
    model: str
    status: str
    text: str
    segments: list[TranscriptSegment]
    word_timestamps_available: bool
    speaker_diarization_available: bool = Field(default=False)
    timing_granularity: str = Field(
        ...,
        description="Truthful timing resolution: 'word' or 'segment'",
    )
    warnings: list[str] = Field(default_factory=list)
    created_at: str
