"""Central transcription manager coordinating local and cloud speech engines (PRD §5 FR-03, FR-12).

Features:
- Uniform asynchronous interface across all local and cloud transcription providers.
- Dynamic provider registry (faster-whisper, whisper.cpp, groq, assemblyai, huggingface, fake).
- Concurrency control: limits concurrent local inference on memory-constrained systems.
- Fail-closed privacy gating for cloud providers (QATTA_ALLOW_CLOUD_APIS=true).
- Content-addressed result caching based on audio fingerprint and transcription settings.
- Accurate capability discovery and reporting (device, precision, fallback reasons).
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.schemas.transcription import (
    ProviderCapabilityInfo,
    TranscriptSegment,
    WordTiming,
)
from app.services.media.audio import JobCancelledError
from app.services.transcription.assemblyai_provider import AssemblyAITranscriptionProvider
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)
from app.services.transcription.cache import (
    compute_cache_key,
    load_cached_transcript,
    store_transcript,
)
from app.services.transcription.fake_provider import FakeTranscriptionProvider
from app.services.transcription.faster_whisper_provider import FasterWhisperProvider
from app.services.transcription.groq_provider import GroqTranscriptionProvider
from app.services.transcription.huggingface_provider import HuggingFaceTranscriptionProvider
from app.services.transcription.whisper_cpp_provider import WhisperCppProvider
from app.services.transcription.youtube_provider import YouTubeTranscriptionProvider


class TranscriptionManager:
    """Orchestrates local and cloud speech recognition engines."""

    def __init__(self) -> None:
        self._providers: dict[str, TranscriptionProvider] = {
            "faster-whisper": FasterWhisperProvider(),
            "whisper.cpp": WhisperCppProvider(),
            "groq": GroqTranscriptionProvider(),
            "assemblyai": AssemblyAITranscriptionProvider(),
            "huggingface": HuggingFaceTranscriptionProvider(),
            "youtube": YouTubeTranscriptionProvider(),
            "fake": FakeTranscriptionProvider(),
        }
        # Concurrency semaphore for local inference jobs to protect modest hardware (e.g. 8GB RAM)
        self._local_semaphore = asyncio.Semaphore(1)

    def register_provider(self, name: str, provider: TranscriptionProvider) -> None:
        """Register or replace a transcription provider instance."""
        self._providers[name] = provider

    def get_provider(self, name: str) -> TranscriptionProvider:
        """Retrieve provider by identifier."""
        if name not in self._providers:
            available_list = list(self._providers.keys())
            raise TranscriptionError(
                f"Unknown transcription provider '{name}'. Available: {available_list}",
                error_code="PROVIDER_NOT_FOUND",
            )
        return self._providers[name]

    def list_providers(self) -> list[ProviderCapabilityInfo]:
        """Return truthful capability and status disclosures for all registered providers."""
        active_name = settings.DEFAULT_TRANSCRIPTION_BACKEND
        info_list: list[ProviderCapabilityInfo] = []

        for name, provider in self._providers.items():
            try:
                cap = provider.get_capabilities()
                cap.active = name == active_name
                info_list.append(cap)
            except Exception as e:
                logger.warning("Failed to query capabilities for provider '%s': %s", name, e)

        return info_list

    async def transcribe(
        self,
        audio_path: Path,
        provider_name: str | None = None,
        language: str | None = None,
        model_size: str | None = None,
        word_timestamps: bool = True,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Execute transcription via selected provider with caching and safety gating."""
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        selected_provider_name = (
            provider_name or settings.DEFAULT_TRANSCRIPTION_BACKEND or "faster-whisper"
        )
        provider = self.get_provider(selected_provider_name)
        effective_model = model_size or settings.DEFAULT_WHISPER_MODEL

        # Privacy gating check
        capabilities = provider.get_capabilities()
        if capabilities.is_cloud:
            if not settings.ALLOW_CLOUD_APIS:
                raise TranscriptionError(
                    f"Provider '{selected_provider_name}' requires cloud access, "
                    "but QATTA_ALLOW_CLOUD_APIS is false. "
                    "Enable cloud APIs or switch to local faster-whisper.",
                    error_code="CLOUD_APIS_DISABLED",
                )
            if not capabilities.api_key_configured:
                reason = capabilities.fallback_reason or ""
                raise TranscriptionError(
                    f"Provider '{selected_provider_name}' requires an API key "
                    f"that is not configured. {reason}".strip(),
                    error_code="API_KEY_MISSING",
                )

        # Caching lookup
        cache_dir = settings.get_transcripts_cache_dir()
        settings_map = {
            "model_size": effective_model,
            "language": language or "auto",
            "beam_size": kwargs.get("beam_size", settings.WHISPER_BEAM_SIZE),
            "vad_filter": kwargs.get("vad_filter", settings.WHISPER_VAD_FILTER),
            "compute_type": kwargs.get("compute_type", settings.DEFAULT_WHISPER_COMPUTE_TYPE),
            "word_timestamps": word_timestamps,
            "profile": kwargs.get("profile", "default"),
            "provider": selected_provider_name,
            "wav_sample_rate": 16000,
            "wav_channels": 1,
            "cache_schema_version": 1,
        }

        cache_key = None
        if use_cache and audio_path.is_file():
            try:
                cache_key = compute_cache_key(audio_path, settings_map)
                cached_data = load_cached_transcript(cache_dir, cache_key)
                if cached_data and "result" in cached_data:
                    logger.info(
                        "Transcript cache HIT for audio: %s (key=%s)", audio_path.name, cache_key
                    )
                    if progress_callback:
                        progress_callback(100.0, "completed")
                    res = cached_data["result"]
                    return self._hydrate_result(res)
            except Exception as e:
                logger.warning("Cache lookup encountered error: %s", e)

        # Execute transcription with local concurrency limit
        if capabilities.is_local:
            async with self._local_semaphore:
                result = await provider.transcribe(
                    audio_path=audio_path,
                    language=language,
                    model_size=effective_model,
                    word_timestamps=word_timestamps,
                    cancel_event=cancel_event,
                    progress_callback=progress_callback,
                    **kwargs,
                )
        else:
            result = await provider.transcribe(
                audio_path=audio_path,
                language=language,
                model_size=effective_model,
                word_timestamps=word_timestamps,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
                **kwargs,
            )

        # Cache result
        if use_cache and cache_key:
            try:
                store_transcript(cache_dir, cache_key, settings_map, result.model_dump())
            except Exception as e:
                logger.warning("Failed to store result in transcript cache: %s", e)

        return result

    def _hydrate_result(self, raw: dict[str, Any]) -> TranscriptionResult:
        """Convert cached JSON dict back into a typed TranscriptionResult."""
        segments: list[TranscriptSegment] = []
        for s in raw.get("segments", []):
            words = None
            if s.get("words"):
                words = [
                    WordTiming(
                        word=w["word"],
                        start=w["start"],
                        end=w["end"],
                        probability=w.get("probability"),
                    )
                    for w in s["words"]
                ]
            segments.append(
                TranscriptSegment(
                    id=s["id"],
                    start=s["start"],
                    end=s["end"],
                    text=s["text"],
                    words=words,
                    speaker=s.get("speaker"),
                    avg_logprob=s.get("avg_logprob"),
                    no_speech_prob=s.get("no_speech_prob"),
                )
            )

        return TranscriptionResult(
            language=raw.get("language", "auto"),
            language_probability=raw.get("language_probability"),
            duration=raw.get("duration", 0.0),
            text=raw.get("text", ""),
            segments=segments,
            word_timestamps_available=raw.get("word_timestamps_available", False),
            timing_granularity=raw.get("timing_granularity", "segment"),
            provider=raw.get("provider", "cached"),
            model=raw.get("model", "unknown"),
            device=raw.get("device"),
            compute_type=raw.get("compute_type"),
            fallback_reason=raw.get("fallback_reason"),
            speaker_diarization_available=raw.get("speaker_diarization_available", False),
        )


# Global singleton manager instance
transcription_manager = TranscriptionManager()
