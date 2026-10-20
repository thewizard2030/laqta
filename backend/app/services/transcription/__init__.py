"""Transcription services, multi-engine manager, and providers (PRD §5 FR-03, FR-12)."""

from app.services.transcription.assemblyai_provider import AssemblyAITranscriptionProvider
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)
from app.services.transcription.fake_provider import FakeTranscriptionProvider
from app.services.transcription.faster_whisper_provider import (
    FasterWhisperProvider,
    is_faster_whisper_installed,
)
from app.services.transcription.groq_provider import GroqTranscriptionProvider
from app.services.transcription.huggingface_provider import HuggingFaceTranscriptionProvider
from app.services.transcription.manager import (
    TranscriptionManager,
    transcription_manager,
)
from app.services.transcription.whisper_cpp_provider import WhisperCppProvider


def get_transcription_provider(name: str = "faster-whisper") -> TranscriptionProvider:
    """Return configured TranscriptionProvider instance via TranscriptionManager.

    Args:
        name: Provider name ('faster-whisper', 'whisper.cpp', 'groq',
            'assemblyai', 'huggingface', 'fake').


    Returns:
        Instance conforming to TranscriptionProvider.
    """
    return transcription_manager.get_provider(name)


__all__ = [
    "TranscriptionProvider",
    "FasterWhisperProvider",
    "FakeTranscriptionProvider",
    "WhisperCppProvider",
    "GroqTranscriptionProvider",
    "AssemblyAITranscriptionProvider",
    "HuggingFaceTranscriptionProvider",
    "TranscriptionManager",
    "transcription_manager",
    "TranscriptionError",
    "TranscriptionResult",
    "get_transcription_provider",
    "is_faster_whisper_installed",
]
