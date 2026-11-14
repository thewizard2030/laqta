# Transcription

## Overview
Pluggable multi-engine speech-to-text service managing local Faster-Whisper, whisper.cpp, Groq, AssemblyAI, HuggingFace, and YouTube captions with hardware discovery and content-addressed caching.

## Interface
- app.services.transcription.base:TranscriptionProvider(ABC)
- app.services.transcription.base:TranscriptionResult
- app.services.transcription.base:TranscriptionError
- app.services.transcription.manager:TranscriptionManager
- app.services.transcription.manager:transcription_manager
- app.services.transcription.manager:get_transcription_provider(name: str = 'faster-whisper') -> TranscriptionProvider
- app.services.transcription.faster_whisper_provider:FasterWhisperProvider
- app.services.transcription.faster_whisper_provider:is_faster_whisper_installed() -> bool
- app.services.transcription.whisper_cpp_provider:WhisperCppProvider
- app.services.transcription.groq_provider:GroqTranscriptionProvider
- app.services.transcription.assemblyai_provider:AssemblyAITranscriptionProvider
- app.services.transcription.huggingface_provider:HuggingFaceTranscriptionProvider
- app.services.transcription.youtube_provider:YouTubeTranscriptionProvider
- app.services.transcription.fake_provider:FakeTranscriptionProvider
- app.services.transcription.cache:compute_cache_key(audio_path: Path, provider: str, model: str, language: str | None, word_timestamps: bool) -> str
- app.services.transcription.cache:load_cached_transcript(cache_dir: Path, cache_key: str) -> TranscriptionResult | None
- app.services.transcription.cache:store_transcript(cache_dir: Path, cache_key: str, result: TranscriptionResult) -> None
- app.services.transcription.alignment:align_clip_words(audio_path: Path, clip_start_ms: int, clip_duration_ms: int, language: str, text: str) -> list[WordTiming]

## Invariants
- Cloud API gating: hosted providers (Groq, AssemblyAI, HuggingFace) require settings.ALLOW_CLOUD_APIS=true and valid API keys; fail-closed by default [manager.py:transcribe, groq_provider.py, assemblyai_provider.py]
- Concurrency bounding: local CPU inference is bounded by a semaphore (_local_semaphore = asyncio.Semaphore(1)) to prevent OOM on 8 GB RAM machines [manager.py:transcribe]
- Timing granularity truthfulness: accurately reports timing_granularity as 'word' or 'segment'; never fabricates missing word timestamps [base.py:TranscriptionResult]
- BiDi & Arablish support: Whisper initial_prompt settings preserve English technical terms within Arabic transcription [faster_whisper_provider.py]

## Side Effects
- CPU/GPU compute cycles for local speech recognition inference (CTranslate2 / faster-whisper) [faster_whisper_provider.py]
- Reads audio files from disk and writes content-addressed JSON cache files under DATA_DIR/transcripts/cache [cache.py:store_transcript]
- Outbound HTTPS requests to external cloud APIs (Groq, AssemblyAI, Hugging Face) when enabled [groq_provider.py, assemblyai_provider.py, huggingface_provider.py]

## Verification
- Run: `pytest backend/tests`
