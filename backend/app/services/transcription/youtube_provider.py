"""YouTube platform captions transcription provider (PRD FR-12).

Fetches or parses platform-provided caption tracks (manual or auto-captions)
with rolling-deduplication, avoiding heavy local inference when captions exist.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.schemas.transcription import ProviderCapabilityInfo, TranscriptSegment
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)

# The same wording is used for the capability report and the disclosure shown
# to the user, so it lives in exactly one place.
DISCLOSURE = (
    "Platform captions are parsed locally from YouTube metadata without "
    "sending audio to third-party transcription APIs."
)


class YouTubeTranscriptionProvider(TranscriptionProvider):
    """Transcription provider consuming platform-provided YouTube caption tracks."""

    def __init__(self) -> None:
        pass

    def is_available(self) -> bool:
        from app.services.media.url_ingest import detect_yt_dlp

        cap = detect_yt_dlp()
        return bool(cap.available)

    def get_capabilities(self) -> ProviderCapabilityInfo:
        from app.services.media.url_ingest import detect_yt_dlp

        cap = detect_yt_dlp()
        return ProviderCapabilityInfo(
            name="youtube",
            provider="youtube",
            display_name="YouTube Captions",
            is_local=True,
            is_cloud=False,
            available=cap.available,
            active=False,
            device="platform",
            compute_type="vtt",
            supported_models=["captions", "auto_captions"],
            models=["captions", "auto_captions"],
            privacy_disclosure=DISCLOSURE,
            disclosure_text=DISCLOSURE,
        )

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str = "captions",
        word_timestamps: bool = False,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Parse platform captions for the media asset.

        Accepts either an explicit ``subtitle_path`` in kwargs, a ``source_url``
        to fetch via yt-dlp, or scans the project's subtitles folder for an
        associated .vtt file.
        """
        if cancel_event and cancel_event.is_set():
            raise TranscriptionError(
                "Transcription cancelled.", error_code="TRANSCRIPTION_CANCELLED"
            )

        from qatta.stages.s02_transcript.youtube_subs import (
            fetch_info_and_subs,
            segments_from_youtube_subs,
        )

        vtt_file: Path | None = None
        subtitle_arg = kwargs.get("subtitle_path")
        if subtitle_arg and Path(subtitle_arg).is_file():
            vtt_file = Path(subtitle_arg)

        source_url = kwargs.get("source_url")
        if not vtt_file and source_url:
            if progress_callback:
                progress_callback(10.0, "fetching_captions")
            sub_langs = [language] if language else ["ar", "en"]
            try:
                work_dir = audio_path.parent
                _, vtt_file = fetch_info_and_subs(
                    str(source_url),
                    work_dir,
                    sub_languages=sub_langs,
                )
            except Exception as e:
                raise TranscriptionError(
                    f"Failed to fetch YouTube captions: {e}",
                    error_code="YOUTUBE_FETCH_FAILED",
                ) from e

        if not vtt_file:
            # Check adjacent subtitles directory
            project_dir = audio_path.parent.parent
            sub_dir = project_dir / "subtitles"
            if sub_dir.is_dir():
                candidates = sorted(sub_dir.glob("*.vtt"))
                if candidates:
                    vtt_file = candidates[0]

        if not vtt_file or not vtt_file.is_file():
            raise TranscriptionError(
                "No YouTube caption file found or fetched for this media.",
                error_code="NO_YOUTUBE_CAPTIONS",
            )

        if progress_callback:
            progress_callback(50.0, "parsing_captions")

        try:
            vtt_text = vtt_file.read_text(encoding="utf-8", errors="replace")
            raw_segments = segments_from_youtube_subs(vtt_text)
        except Exception as e:
            raise TranscriptionError(
                f"Failed to parse caption file: {e}",
                error_code="CAPTIONS_PARSE_FAILED",
            ) from e

        if not raw_segments:
            raise TranscriptionError(
                "YouTube caption file contained no usable cues.",
                error_code="EMPTY_CAPTIONS",
            )

        segments = [
            TranscriptSegment(
                id=f"u_{idx:04d}",
                start=round(seg.start_ms / 1000.0, 3),
                end=round(seg.end_ms / 1000.0, 3),
                text=seg.text,
                words=None,
                speaker=None,
            )
            for idx, seg in enumerate(raw_segments, start=1)
        ]
        full_text = " ".join(seg.text for seg in raw_segments)
        duration = max(s.end for s in segments) if segments else 0.0

        if progress_callback:
            progress_callback(100.0, "completed")

        return TranscriptionResult(
            language=language or "ar",
            duration=duration,
            text=full_text,
            segments=segments,
            word_timestamps_available=False,
            timing_granularity="segment",
            provider="youtube",
            model="captions",
            device="platform",
            compute_type="vtt",
        )
