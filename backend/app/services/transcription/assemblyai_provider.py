"""AssemblyAI transcription provider with speaker diarization (PRD §5 FR-03, FR-12).

Features:
- Cloud transcription with speaker diarization ("who spoke when").
- Two-step async workflow: file upload to /v2/upload followed by /v2/transcript.
- Polling loop with progressive progress reporting and cooperative cancellation.
- Millisecond-to-second timestamp normalization.
- Strict gating: requires QATTA_ALLOW_CLOUD_APIS=true and ASSEMBLYAI_API_KEY.
- Redacted logging.
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
from app.services.transcription.chunking import retry_with_backoff

ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"


class AssemblyAITranscriptionProvider(TranscriptionProvider):
    """Cloud transcription provider via AssemblyAI with speaker diarization."""

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._custom_client = http_client

    def is_available(self) -> bool:
        """Return True only if cloud APIs are permitted and an API key is configured."""
        return settings.ALLOW_CLOUD_APIS and settings.assemblyai_api_key_configured()

    def get_capabilities(self) -> ProviderCapabilityInfo:
        allowed = settings.ALLOW_CLOUD_APIS
        key_set = settings.assemblyai_api_key_configured()
        available = allowed and key_set

        fallback = None
        if not allowed:
            fallback = (
                "Cloud APIs are disabled. Enable QATTA_ALLOW_CLOUD_APIS=true to use AssemblyAI."
            )
        elif not key_set:
            fallback = "ASSEMBLYAI_API_KEY is not set."

        return ProviderCapabilityInfo(
            provider="assemblyai",
            display_name="AssemblyAI Cloud (Diarization & Multi-Speaker)",
            is_local=False,
            is_cloud=True,
            available=available,
            active=False,
            device="cloud",
            cuda_available=False,
            cuda_device_name=None,
            cuda_device_count=0,
            compute_type="cloud",
            models=["universal-1", "conformer-2"],
            supports_word_timestamps=True,
            supports_speaker_diarization=True,
            requires_api_key=True,
            api_key_configured=key_set,
            privacy_disclosure=(
                "Audio will be securely uploaded to AssemblyAI Inc. cloud infrastructure "
                "for transcription and speaker diarization."
            ),
            fallback_reason=fallback,
        )

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str = "universal-1",
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

        if not settings.assemblyai_api_key_configured():
            raise TranscriptionError(
                "ASSEMBLYAI_API_KEY is missing or empty. "
                "Please set your ASSEMBLYAI_API_KEY env var.",
                error_code="API_KEY_MISSING",
            )

        if not audio_path.is_file():
            raise TranscriptionError(
                f"Audio file does not exist at {audio_path}",
                error_code="AUDIO_NOT_FOUND",
            )

        logger.info(
            "AssemblyAI transcription starting for file: %s (key=%s)",
            audio_path.name,
            settings.redacted_assemblyai_key,
        )

        headers = {
            "Authorization": settings.ASSEMBLYAI_API_KEY,
            "Content-Type": "application/octet-stream",
        }

        client_ctx = self._custom_client if self._custom_client else httpx.AsyncClient()

        async with client_ctx if not self._custom_client else nullcontext(client_ctx) as client:
            # 1. Upload audio file
            if progress_callback:
                progress_callback(10.0, "uploading_audio")

            upload_url = await self._upload_audio(client, audio_path, headers, cancel_event)

            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            # 2. Submit transcription job
            if progress_callback:
                progress_callback(25.0, "submitting_job")

            transcript_id = await self._submit_job(
                client=client,
                upload_url=upload_url,
                language=language,
                headers={"Authorization": settings.ASSEMBLYAI_API_KEY},
            )

            # 3. Poll for completion
            if progress_callback:
                progress_callback(35.0, "transcribing")

            result_data = await self._poll_job(
                client=client,
                transcript_id=transcript_id,
                headers={"Authorization": settings.ASSEMBLYAI_API_KEY},
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )

        return self._format_result(result_data, word_timestamps, model_size)

    async def _upload_audio(
        self,
        client: httpx.AsyncClient,
        audio_path: Path,
        headers: dict[str, str],
        cancel_event: asyncio.Event | None,
    ) -> str:
        """Upload audio binary to AssemblyAI."""
        file_bytes = audio_path.read_bytes()

        async def _upload():
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()
            res = await client.post(
                f"{ASSEMBLYAI_BASE_URL}/upload",
                headers=headers,
                content=file_bytes,
                timeout=120.0,
            )
            if res.status_code == 401:
                raise TranscriptionError("Invalid AssemblyAI API key.", error_code="UNAUTHORIZED")
            if res.status_code in (429, 500, 502, 503, 504):
                res.raise_for_status()
            if res.status_code >= 400:
                raise TranscriptionError(
                    f"AssemblyAI upload failed ({res.status_code}): {res.text}",
                    error_code=f"HTTP_{res.status_code}",
                )
            return res.json()["upload_url"]

        return await retry_with_backoff(_upload, max_retries=3, base_delay=2.0)

    async def _submit_job(
        self,
        client: httpx.AsyncClient,
        upload_url: str,
        language: str | None,
        headers: dict[str, str],
    ) -> str:
        """Submit transcript request with speaker labels enabled."""
        payload: dict[str, Any] = {
            "audio_url": upload_url,
            "speaker_labels": True,
        }
        if language:
            payload["language_code"] = language

        res = await client.post(
            f"{ASSEMBLYAI_BASE_URL}/transcript",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        if res.status_code >= 400:
            raise TranscriptionError(
                f"AssemblyAI transcript request failed ({res.status_code}): {res.text}",
                error_code=f"HTTP_{res.status_code}",
            )
        return res.json()["id"]

    async def _poll_job(
        self,
        client: httpx.AsyncClient,
        transcript_id: str,
        headers: dict[str, str],
        cancel_event: asyncio.Event | None,
        progress_callback: Callable[[float, str], None] | None,
    ) -> dict[str, Any]:
        """Poll AssemblyAI until status is completed or error."""
        poll_url = f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}"
        elapsed = 0.0

        while True:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            res = await client.get(poll_url, headers=headers, timeout=30.0)
            if res.status_code >= 400:
                raise TranscriptionError(
                    f"AssemblyAI polling failed ({res.status_code}): {res.text}",
                    error_code=f"HTTP_{res.status_code}",
                )
            data = res.json()
            status = data.get("status")

            if status == "completed":
                return data
            elif status == "error":
                err_msg = data.get("error", "Unknown error from AssemblyAI")
                raise TranscriptionError(
                    f"AssemblyAI transcription error: {err_msg}",
                    error_code="TRANSCRIPTION_FAILED",
                )

            elapsed += 3.0
            if progress_callback:
                pct = min(92.0, 35.0 + (elapsed / 45.0) * 55.0)
                progress_callback(pct, "transcribing")

            await asyncio.sleep(3.0)

    def _format_result(
        self,
        data: dict[str, Any],
        word_timestamps: bool,
        model_size: str,
    ) -> TranscriptionResult:
        """Convert AssemblyAI JSON response to Laqta TranscriptSegment and WordTiming."""
        segments: list[TranscriptSegment] = []
        utterances = data.get("utterances")

        if utterances:
            # Diarized utterances
            for idx, utt in enumerate(utterances):
                start = float(utt.get("start", 0)) / 1000.0
                end = float(utt.get("end", 0)) / 1000.0
                text = str(utt.get("text", "")).strip()
                speaker_tag = utt.get("speaker")
                speaker_id = f"SPEAKER_{speaker_tag}" if speaker_tag else None

                words: list[WordTiming] | None = None
                if word_timestamps and "words" in utt and isinstance(utt["words"], list):
                    words = [
                        WordTiming(
                            word=str(w.get("text", "")).strip(),
                            start=float(w.get("start", 0)) / 1000.0,
                            end=float(w.get("end", 0)) / 1000.0,
                            probability=float(w.get("confidence", 1.0)),
                        )
                        for w in utt["words"]
                        if str(w.get("text", "")).strip()
                    ]

                segments.append(
                    TranscriptSegment(
                        id=f"seg_{idx + 1:04d}",
                        start=start,
                        end=end,
                        text=text,
                        words=words if words else None,
                        speaker=speaker_id,
                    )
                )
        else:
            # Fallback to plain words or full text
            words_raw = data.get("words", [])
            words = None
            if word_timestamps and words_raw:
                words = [
                    WordTiming(
                        word=str(w.get("text", "")).strip(),
                        start=float(w.get("start", 0)) / 1000.0,
                        end=float(w.get("end", 0)) / 1000.0,
                        probability=float(w.get("confidence", 1.0)),
                    )
                    for w in words_raw
                    if str(w.get("text", "")).strip()
                ]

            audio_dur = float(data.get("audio_duration", 0.0))
            full_txt = str(data.get("text", "")).strip()
            if full_txt:
                segments.append(
                    TranscriptSegment(
                        id="seg_0001",
                        start=0.0,
                        end=audio_dur,
                        text=full_txt,
                        words=words,
                    )
                )

        total_dur = float(data.get("audio_duration", 0.0))
        full_text = str(data.get("text", "")).strip()

        return TranscriptionResult(
            language=data.get("language_code", "en"),
            language_probability=float(data.get("confidence", 1.0) or 1.0),
            duration=total_dur,
            text=full_text,
            segments=segments,
            word_timestamps_available=bool(word_timestamps and segments),
            timing_granularity="word" if word_timestamps else "segment",
            provider="assemblyai",
            model=model_size,
            device="cloud",
            compute_type="cloud",
            speaker_diarization_available=True,
        )
