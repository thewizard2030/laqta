"""Base interfaces and result models for pluggable transcription providers."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.schemas.transcription import ProviderCapabilityInfo, TranscriptSegment


class TranscriptionError(Exception):
    """Exception raised when speech-to-text transcription fails."""

    def __init__(
        self,
        message: str,
        error_code: str = "TRANSCRIPTION_FAILED",
        diagnostic_logs: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.diagnostic_logs = diagnostic_logs


@dataclass
class TranscriptionResult:
    """Standardized result returned by all transcription providers."""

    language: str
    duration: float
    text: str
    segments: list[TranscriptSegment]
    word_timestamps_available: bool
    timing_granularity: str  # "word" or "segment"
    provider: str
    model: str
    language_probability: float | None = None
    speaker_diarization_available: bool = False
    device: str = "cpu"
    compute_type: str = "int8"
    fallback_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        """Convert result to serializable dict matching Pydantic convention."""
        return {
            "language": self.language,
            "language_probability": self.language_probability,
            "duration": self.duration,
            "text": self.text,
            "segments": [s.model_dump() for s in self.segments],
            "word_timestamps_available": self.word_timestamps_available,
            "timing_granularity": self.timing_granularity,
            "provider": self.provider,
            "model": self.model,
            "speaker_diarization_available": self.speaker_diarization_available,
            "device": self.device,
            "compute_type": self.compute_type,
            "fallback_reason": self.fallback_reason,
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class TranscriptionProvider(ABC):
    """Abstract interface for speech-to-text transcription providers (PRD §5 FR-03)."""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str = "base",
        word_timestamps: bool = True,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Transcribe an extracted 16 kHz mono WAV audio file.

        Args:
            audio_path: Safe path to input 16 kHz mono WAV file.
            language: Optional 2-letter ISO language code (e.g. 'ar', 'en'). None for auto-detect.
            model_size: Model size ('tiny', 'base', 'small', 'medium', 'large-v3').
            word_timestamps: Whether to request word-level timing from the provider.
            cancel_event: Optional cooperative cancellation flag.
            progress_callback: Optional progress reporter receiving (percent, stage).

        Returns:
            TranscriptionResult with validated segments and truthful timing granularity.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider dependencies and environment are operational."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilityInfo:
        """Return honest capability details for this provider."""
        pass
