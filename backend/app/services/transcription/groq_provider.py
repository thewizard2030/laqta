"""Groq Whisper API transcription provider (PRD §5 FR-03, FR-12).

Features:
- Cloud-accelerated Whisper using whisper-large-v3-turbo or whisper-large-v3.
- Automatic duration and file-size inspection before upload.
- Overlapping audio chunking for files exceeding Groq's 25 MB limit.
- Timestamp-preserving chunk stitching with seam deduplication.
- Exponential backoff retry on HTTP 429 and 5xx errors.
- Strict gating: requires QATTA_ALLOW_CLOUD_APIS=true and non-empty GROQ_API_KEY.
- Redacted logging (API keys never appear in logs).
"""

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.transcription import (
    ProviderCapabilityInfo,
    TranscriptSegment,
    WordTiming,
)
from app.services.media.audio import JobCancelledError
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)
from app.services.transcription.chunking import (
    inspect_audio_file,
    merge_overlapping_segments,
    retry_with_backoff,
    split_audio_overlapping,
)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MAX_FILE_BYTES = 24 * 1024 * 1024  # 24 MB safety threshold below 25 MB limit
GROQ_ALLOWED_MODELS = ["whisper-large-v3-turbo", "whisper-large-v3"]


class GroqTranscriptionProvider(TranscriptionProvider):
    """Cloud transcription provider via Groq Whisper API."""

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._custom_client = http_client

    def is_available(self) -> bool:
        """Return True only if cloud APIs are permitted and an API key is configured."""
        return settings.ALLOW_CLOUD_APIS and settings.groq_api_key_configured()

    def get_capabilities(self) -> ProviderCapabilityInfo:
        allowed = settings.ALLOW_CLOUD_APIS
        key_set = settings.groq_api_key_configured()
        available = allowed and key_set

        fallback = None
        if not allowed:
            fallback = "Cloud APIs are disabled. Enable QATTA_ALLOW_CLOUD_APIS=true to use Groq."
        elif not key_set:
            fallback = "GROQ_API_KEY is not set."

        return ProviderCapabilityInfo(
            provider="groq",
            display_name="Groq Whisper Cloud (Ultra-Fast Large-v3)",
            is_local=False,
            is_cloud=True,
            available=available,
            active=False,
            device="cloud",
            cuda_available=False,
            cuda_device_name=None,
            cuda_device_count=0,
            compute_type="fp16",
            models=GROQ_ALLOWED_MODELS,
            supports_word_timestamps=True,
            supports_speaker_diarization=False,
            requires_api_key=True,
            api_key_configured=key_set,
            privacy_disclosure=(
                "Audio will be securely uploaded to Groq Inc. cloud infrastructure "
                "for transcription. Processing is fast but external."
            ),
            fallback_reason=fallback,
        )

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str = "whisper-large-v3-turbo",
        word_timestamps: bool = True,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        **kwargs: object,
    ) -> TranscriptionResult:
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        if not settings.ALLOW_CLOUD_APIS:
            raise TranscriptionError(
                "Cloud transcription is disabled. Set QATTA_ALLOW_CLOUD_APIS=true to enable.",
                error_code="CLOUD_APIS_DISABLED",
            )

        if not settings.groq_api_key_configured():
            raise TranscriptionError(
                "GROQ_API_KEY is missing or empty. Please set your GROQ_API_KEY env var.",
                error_code="API_KEY_MISSING",
            )

        if not audio_path.is_file():
            raise TranscriptionError(
                f"Audio file does not exist at {audio_path}",
                error_code="AUDIO_NOT_FOUND",
            )

        effective_model = model_size if model_size in GROQ_ALLOWED_MODELS else settings.GROQ_MODEL

        # Inspect duration and size
        file_size, duration = inspect_audio_file(audio_path)
        logger.info(
            "Groq transcription requested for file: size=%.2fMB, duration=%.1fs, key=%s",
            file_size / (1024 * 1024),
            duration,
            settings.redacted_groq_key,
        )

        if progress_callback:
            progress_callback(10.0, "transcribing")

        # Determine if chunking is required (> 24 MB or > 1200 seconds)
        if file_size > GROQ_MAX_FILE_BYTES or duration > 1200.0:
            return await self._transcribe_chunked(
                audio_path=audio_path,
                language=language,
                model_name=effective_model,
                word_timestamps=word_timestamps,
                total_duration=duration,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )
        else:
            return await self._transcribe_single(
                audio_path=audio_path,
                language=language,
                model_name=effective_model,
                word_timestamps=word_timestamps,
                duration=duration,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )

    async def _post_transcription_request(
        self,
        client: httpx.AsyncClient,
        file_bytes: bytes,
        file_name: str,
        language: str | None,
        model_name: str,
        word_timestamps: bool,
    ) -> dict[str, Any]:
        """Post a single transcription file to Groq with retries."""
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        }
        data: dict[str, Any] = {
            "model": model_name,
            "response_format": "verbose_json",
        }
        if language:
            data["language"] = language

        # In Groq API, timestamp_granularities[] must be sent as list in multipart form
        form_data = list(data.items())
        if word_timestamps:
            form_data.append(("timestamp_granularities[]", "word"))
            form_data.append(("timestamp_granularities[]", "segment"))
        else:
            form_data.append(("timestamp_granularities[]", "segment"))

        files = {
            "file": (file_name, file_bytes, "audio/wav"),
        }

        async def _call():
            response = await client.post(
                GROQ_TRANSCRIPTION_URL,
                headers=headers,
                data=form_data,
                files=files,
                timeout=90.0,
            )
            if response.status_code == 401:
                raise TranscriptionError(
                    "Invalid Groq API key or unauthorized request.",
                    error_code="UNAUTHORIZED",
                )
            if response.status_code in (429, 500, 502, 503, 504):
                response.raise_for_status()
            if response.status_code >= 400:
                raise TranscriptionError(
                    f"Groq API error ({response.status_code}): {response.text}",
                    error_code=f"HTTP_{response.status_code}",
                )
            return response.json()

        return await retry_with_backoff(_call, max_retries=3, base_delay=2.0)

    async def _transcribe_single(
        self,
        audio_path: Path,
        language: str | None,
        model_name: str,
        word_timestamps: bool,
        duration: float,
        cancel_event: asyncio.Event | None,
        progress_callback: Callable[[float, str], None] | None,
    ) -> TranscriptionResult:
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        file_bytes = audio_path.read_bytes()

        client_ctx = self._custom_client if self._custom_client else httpx.AsyncClient()
        try:
            async with client_ctx if not self._custom_client else nullcontext(client_ctx) as client:
                data = await self._post_transcription_request(
                    client=client,
                    file_bytes=file_bytes,
                    file_name=audio_path.name,
                    language=language,
                    model_name=model_name,
                    word_timestamps=word_timestamps,
                )
        except httpx.HTTPStatusError as e:
            raise TranscriptionError(
                f"Groq API HTTP error: {e.response.status_code} - {e.response.text}",
                error_code=f"HTTP_{e.response.status_code}",
            ) from e
        except httpx.RequestError as e:
            raise TranscriptionError(
                f"Network connection to Groq API failed: {e}",
                error_code="NETWORK_ERROR",
            ) from e

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        result_segments = _parse_groq_segments(data, word_timestamps)
        detected_lang = data.get("language", language or "auto")
        ret_duration = float(data.get("duration", duration))

        if progress_callback:
            progress_callback(100.0, "completed")

        return TranscriptionResult(
            language=detected_lang,
            language_probability=1.0,
            duration=ret_duration,
            text=str(data.get("text", "")).strip(),
            segments=result_segments,
            word_timestamps_available=bool(word_timestamps and result_segments),
            timing_granularity="word" if word_timestamps else "segment",
            provider="groq",
            model=model_name,
            device="cloud",
            compute_type="fp16",
        )

    async def _transcribe_chunked(
        self,
        audio_path: Path,
        language: str | None,
        model_name: str,
        word_timestamps: bool,
        total_duration: float,
        cancel_event: asyncio.Event | None,
        progress_callback: Callable[[float, str], None] | None,
    ) -> TranscriptionResult:
        """Split audio into chunks, transcribe sequentially with retry, merge cleanly."""
        chunk_sec = 600.0  # 10 minute chunks
        overlap_sec = 5.0

        chunks = split_audio_overlapping(
            audio_path,
            chunk_duration_sec=chunk_sec,
            overlap_sec=overlap_sec,
        )

        all_chunk_segments: list[list[TranscriptSegment]] = []
        detected_lang = language or "auto"
        client_ctx = self._custom_client if self._custom_client else httpx.AsyncClient()

        try:
            async with client_ctx if not self._custom_client else nullcontext(client_ctx) as client:
                for idx, chunk in enumerate(chunks):
                    if cancel_event and cancel_event.is_set():
                        raise JobCancelledError()

                    c_bytes = chunk.path.read_bytes()
                    data = await self._post_transcription_request(
                        client=client,
                        file_bytes=c_bytes,
                        file_name=chunk.path.name,
                        language=language,
                        model_name=model_name,
                        word_timestamps=word_timestamps,
                    )
                    detected_lang = data.get("language", detected_lang)
                    chunk_segs = _parse_groq_segments(data, word_timestamps)
                    all_chunk_segments.append(chunk_segs)

                    if progress_callback and total_duration > 0:
                        pct = min(95.0, 10.0 + 85.0 * ((idx + 1) / len(chunks)))
                        progress_callback(pct, "transcribing")
        finally:
            for c in chunks:
                try:
                    c.path.unlink(missing_ok=True)
                except Exception:
                    pass

        merged_segments = merge_overlapping_segments(chunks, all_chunk_segments)
        full_text = " ".join(s.text for s in merged_segments if s.text)

        if progress_callback:
            progress_callback(100.0, "completed")

        return TranscriptionResult(
            language=detected_lang,
            language_probability=1.0,
            duration=total_duration,
            text=full_text,
            segments=merged_segments,
            word_timestamps_available=bool(word_timestamps and merged_segments),
            timing_granularity="word" if word_timestamps else "segment",
            provider="groq",
            model=model_name,
            device="cloud",
            compute_type="fp16",
        )


def _parse_groq_segments(
    data: dict[str, Any],
    word_timestamps: bool,
) -> list[TranscriptSegment]:
    """Parse segments and optional word timings from Groq API verbose_json response."""
    segments: list[TranscriptSegment] = []
    raw_segments = data.get("segments", [])

    for idx, seg in enumerate(raw_segments):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        text = str(seg.get("text", "")).strip()

        words: list[WordTiming] | None = None
        if word_timestamps and "words" in seg and isinstance(seg["words"], list):
            words = []
            for w in seg["words"]:
                w_text = str(w.get("word", "")).strip()
                if w_text:
                    words.append(
                        WordTiming(
                            word=w_text,
                            start=float(w.get("start", start)),
                            end=float(w.get("end", end)),
                            probability=float(w.get("probability", 1.0))
                            if "probability" in w
                            else None,
                        )
                    )

        segments.append(
            TranscriptSegment(
                id=f"seg_{idx + 1:04d}",
                start=start,
                end=end,
                text=text,
                words=words if words else None,
                avg_logprob=float(seg["avg_logprob"]) if "avg_logprob" in seg else None,
                no_speech_prob=(float(seg["no_speech_prob"]) if "no_speech_prob" in seg else None),
            )
        )

    return segments
