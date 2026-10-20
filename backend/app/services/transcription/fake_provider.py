"""Deterministic fake transcription provider for unit tests and offline testing."""

import asyncio
from collections.abc import Callable
from pathlib import Path

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


class FakeTranscriptionProvider(TranscriptionProvider):
    """Deterministic, fast mock provider generating Arabic and English transcript fixtures."""

    def __init__(self, simulate_word_timestamps: bool = True):
        self.simulate_word_timestamps = simulate_word_timestamps

    def is_available(self) -> bool:
        return True

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
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        if not audio_path.is_file():
            raise TranscriptionError(
                f"Audio file does not exist at {audio_path}",
                error_code="AUDIO_NOT_FOUND",
            )

        if progress_callback:
            progress_callback(10.0, "loading_model")

        await asyncio.sleep(0.01)

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        lang = language or "ar"
        include_words = word_timestamps and self.simulate_word_timestamps

        if lang == "ar":
            # Realistic Arabic transcript segments
            raw_segments = [
                (
                    0.0,
                    4.5,
                    "أهلاً بكم في بودكاست لقطّة للتقنية وتطوير البرمجيات.",
                    [
                        ("أهلاً", 0.0, 0.8),
                        ("بكم", 0.8, 1.3),
                        ("في", 1.3, 1.6),
                        ("بودكاست", 1.6, 2.5),
                        ("لقطّة", 2.5, 3.1),
                        ("للتقنية", 3.1, 4.5),
                    ],
                ),
                (
                    4.8,
                    9.2,
                    "اليوم سنتحدث عن الذكاء الاصطناعي ومعالجة الصوت محلياً على جهازك.",
                    [
                        ("اليوم", 4.8, 5.4),
                        ("سنتحدث", 5.4, 6.2),
                        ("عن", 6.2, 6.5),
                        ("الذكاء", 6.5, 7.2),
                        ("الاصطناعي", 7.2, 8.1),
                        ("محلياً", 8.1, 9.2),
                    ],
                ),
                (
                    9.5,
                    14.0,
                    "كل المعالجة تتم بسرية تامة دون إرسال بياناتك إلى السحابة.",
                    [
                        ("كل", 9.5, 9.8),
                        ("المعالجة", 9.8, 10.6),
                        ("تتم", 10.6, 11.1),
                        ("بسرية", 11.1, 11.8),
                        ("تامة", 11.8, 12.5),
                        ("دون", 12.5, 13.0),
                        ("السحابة", 13.0, 14.0),
                    ],
                ),
            ]
        else:
            # English transcript segments
            raw_segments = [
                (
                    0.0,
                    4.0,
                    "Welcome to the Laqta open-source video editing workflow.",
                    [
                        ("Welcome", 0.0, 0.8),
                        ("to", 0.8, 1.0),
                        ("the", 1.0, 1.3),
                        ("Laqta", 1.3, 2.0),
                        ("workflow", 2.0, 4.0),
                    ],
                ),
                (
                    4.2,
                    8.5,
                    "Today we are exploring fast and private transcription on modest hardware.",
                    [
                        ("Today", 4.2, 4.8),
                        ("we", 4.8, 5.0),
                        ("are", 5.0, 5.3),
                        ("exploring", 5.3, 6.2),
                        ("local", 6.2, 7.0),
                        ("transcription", 7.0, 8.5),
                    ],
                ),
            ]

        segments: list[TranscriptSegment] = []
        full_text: list[str] = []

        total_segs = len(raw_segments)
        for idx, (start, end, text, words_data) in enumerate(raw_segments):
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            words_list: list[WordTiming] | None = None
            if include_words:
                words_list = [
                    WordTiming(word=w_text, start=w_s, end=w_e, probability=0.98)
                    for w_text, w_s, w_e in words_data
                ]

            segments.append(
                TranscriptSegment(
                    id=f"seg_{idx + 1:04d}",
                    start=start,
                    end=end,
                    text=text,
                    words=words_list,
                    avg_logprob=-0.25,
                    no_speech_prob=0.01,
                )
            )
            full_text.append(text)

            if progress_callback:
                pct = 20.0 + ((idx + 1) / total_segs) * 75.0
                progress_callback(pct, "transcribing")

        word_timestamps_available = include_words
        timing_granularity = "word" if word_timestamps_available else "segment"

        if progress_callback:
            progress_callback(100.0, "completed")

        return TranscriptionResult(
            language=lang,
            language_probability=0.99,
            duration=raw_segments[-1][1],
            text=" ".join(full_text),
            segments=segments,
            word_timestamps_available=word_timestamps_available,
            timing_granularity=timing_granularity,
            provider="fake",
            model=model_size,
        )

    def get_capabilities(self) -> ProviderCapabilityInfo:
        """Return fake capability info for testing."""
        from app.schemas.transcription import ProviderCapabilityInfo

        return ProviderCapabilityInfo(
            provider="fake",
            display_name="Fake Provider (Testing)",
            is_local=True,
            is_cloud=False,
            available=True,
            active=False,
            device="cpu",
            cuda_available=False,
            cuda_device_name=None,
            cuda_device_count=0,
            compute_type="none",
            models=["fake-model"],
            supports_word_timestamps=True,
            supports_speaker_diarization=False,
            requires_api_key=False,
            api_key_configured=True,
            privacy_disclosure=(
                "Local simulated provider for unit tests. Audio never leaves this machine."
            ),
            fallback_reason=None,
        )
