"""Hugging Face Inference Providers transcription adapter (PRD §5 FR-03, FR-12).

Features:
- Cloud-accelerated Whisper models via Hugging Face Serverless Inference API.
- Handles model warmup / loading (503 status code with estimated_time).
- Safe retry with exponential backoff.
- Chunk and segment timestamp extraction.
- Gating: requires QATTA_ALLOW_CLOUD_APIS=true and non-empty HF_TOKEN.
- Redacted logging (HF token never printed in plain text).
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
)
from app.services.media.audio import JobCancelledError
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)
from app.services.transcription.chunking import inspect_audio_file, retry_with_backoff


class HuggingFaceTranscriptionProvider(TranscriptionProvider):
    """Cloud transcription provider via Hugging Face Serverless Inference."""

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._custom_client = http_client

    def is_available(self) -> bool:
        """Return True only if cloud APIs are permitted and an HF token is configured."""
        return settings.ALLOW_CLOUD_APIS and settings.hf_token_configured()

    def get_capabilities(self) -> ProviderCapabilityInfo:
        allowed = settings.ALLOW_CLOUD_APIS
        key_set = settings.hf_token_configured()
        available = allowed and key_set

        fallback = None
        if not allowed:
            fallback = (
                "Cloud APIs are disabled. Enable QATTA_ALLOW_CLOUD_APIS=true to use Hugging Face."
            )
        elif not key_set:
            fallback = "HF_TOKEN is not set."

        return ProviderCapabilityInfo(
            provider="huggingface",
            display_name="Hugging Face Inference API (Serverless)",
            is_local=False,
            is_cloud=True,
            available=available,
            active=False,
            device="cloud",
            cuda_available=False,
            cuda_device_name=None,
            cuda_device_count=0,
            compute_type="fp16",
            models=[settings.HF_WHISPER_MODEL],
            supports_word_timestamps=False,
            supports_speaker_diarization=False,
            requires_api_key=True,
            api_key_configured=key_set,
            privacy_disclosure=(
                "Audio will be transmitted to Hugging Face Inference API cloud infrastructure "
                "for transcription."
            ),
            fallback_reason=fallback,
        )

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str | None = None,
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

        if not settings.hf_token_configured():
            raise TranscriptionError(
                "HF_TOKEN is missing or empty. Please set your HF_TOKEN environment variable.",
                error_code="API_KEY_MISSING",
            )

        if not audio_path.is_file():
            raise TranscriptionError(
                f"Audio file does not exist at {audio_path}",
                error_code="AUDIO_NOT_FOUND",
            )

        model = model_size or settings.HF_WHISPER_MODEL
        url = f"https://api-inference.huggingface.co/models/{model}"

        file_size, duration = inspect_audio_file(audio_path)
        logger.info(
            "Hugging Face transcription starting for file: %s (size=%.2fMB, model=%s, token=%s)",
            audio_path.name,
            file_size / (1024 * 1024),
            model,
            settings.redacted_hf_token,
        )

        if progress_callback:
            progress_callback(15.0, "transcribing")

        headers = {
            "Authorization": f"Bearer {settings.HF_TOKEN}",
            "Content-Type": "audio/flac",  # HF inference accepts flac/wav/mp3
        }

        # Query parameters to ask for timestamps
        params = {
            "return_timestamps": "true",
        }

        file_bytes = audio_path.read_bytes()
        client_ctx = self._custom_client if self._custom_client else httpx.AsyncClient()

        async def _call_hf():
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            async with client_ctx if not self._custom_client else nullcontext(client_ctx) as client:
                res = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    content=file_bytes,
                    timeout=120.0,
                )

                if res.status_code == 401:
                    raise TranscriptionError(
                        "Invalid Hugging Face API token.",
                        error_code="UNAUTHORIZED",
                    )
                if res.status_code == 503:
                    # Model loading, check estimated_time
                    err_json = res.json()
                    est_time = err_json.get("estimated_time", 10.0)
                    logger.info("Hugging Face model %s loading, waiting %.1fs...", model, est_time)
                    await asyncio.sleep(min(est_time, 15.0))
                    res.raise_for_status()

                if res.status_code in (429, 500, 502, 504):
                    res.raise_for_status()

                if res.status_code >= 400:
                    raise TranscriptionError(
                        f"Hugging Face API error ({res.status_code}): {res.text}",
                        error_code=f"HTTP_{res.status_code}",
                    )
                return res.json()

        data = await retry_with_backoff(_call_hf, max_retries=4, base_delay=3.0)

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        return self._format_result(data, duration, model)

    def _format_result(
        self,
        data: dict[str, Any],
        duration: float,
        model: str,
    ) -> TranscriptionResult:
        """Parse HF inference chunks into TranscriptSegment list."""
        segments: list[TranscriptSegment] = []
        chunks = data.get("chunks", [])

        if chunks:
            for idx, c in enumerate(chunks):
                ts = c.get("timestamp", [0.0, 0.0])
                start = float(ts[0]) if ts and ts[0] is not None else 0.0
                end = float(ts[1]) if ts and len(ts) > 1 and ts[1] is not None else start + 1.0
                txt = str(c.get("text", "")).strip()
                segments.append(
                    TranscriptSegment(
                        id=f"seg_{idx + 1:04d}",
                        start=start,
                        end=end,
                        text=txt,
                    )
                )
        else:
            txt = str(data.get("text", "")).strip()
            if txt:
                segments.append(
                    TranscriptSegment(
                        id="seg_0001",
                        start=0.0,
                        end=duration,
                        text=txt,
                    )
                )

        full_text = str(data.get("text", "")).strip()
        if not full_text and segments:
            full_text = " ".join(s.text for s in segments)

        return TranscriptionResult(
            language="auto",
            duration=duration,
            text=full_text,
            segments=segments,
            word_timestamps_available=False,
            timing_granularity="segment",
            provider="huggingface",
            model=model,
            device="cloud",
            compute_type="fp16",
        )
