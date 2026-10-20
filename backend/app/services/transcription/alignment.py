"""Pass B: clip-scoped word re-timing for animated word-by-word captions.

Honest description of this pass (PRD honesty rules):
- It extracts ONLY the selected clip's audio (typically 30-55 s) as a 16 kHz
  mono WAV and re-runs Whisper decoding on that bounded slice with
  ``word_timestamps=True`` and a wider beam.
- Word times come from Whisper cross-attention token alignment inside the
  clip, then are converted back to absolute source-video timestamps via a
  single offset. This is clipped Whisper re-timing, NOT wav2vec2/WhisperX
  forced alignment and NOT speaker diarization; the API never claims
  millisecond-exact phoneme alignment beyond this.
- On any failure (no speech detected, invalid timings, missing weights,
  cancellation-adjacent errors) the caller keeps the segment-level caption
  fallback; the transcript itself is never discarded.

Peak RAM stays bounded: the model cache is shared with the transcription
provider, and the decoded clip audio is a few megabytes at most.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger
from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.media.audio import JobCancelledError
from app.services.transcription.base import TranscriptionError
from app.services.transcription.faster_whisper_provider import (
    _decode_audio_to_float32,
    load_whisper_model,
)

# Largest gap between consecutive words that is still considered "one
# flowing utterance" for reliability checking.
_MAX_WORD_OVERLAP_SECONDS = 1.0
# Pause that starts a new caption-friendly group of words. Arabic speech
# uses short pauses between phrases, so a 1 s threshold collapsed a whole
# 40 s clip into one group; 0.6 s yields groups that fit on a caption.
_SEGMENT_SPLIT_PAUSE_SECONDS = 0.6
# Words finishing a hair after the nominal clip end are tolerated.
_END_TOLERANCE_SEC = 0.5
_MIN_WORDS_FOR_RELIABLE = 1


@dataclass(frozen=True)
class AlignedClip:
    """Word-level re-timing result in ABSOLUTE source-video timestamps."""

    provider: str
    model: str
    language: str | None
    clip_start_sec: float
    clip_end_sec: float
    segments: list[TranscriptSegment]
    word_count: int
    beam_size: int

    @property
    def words(self) -> list[WordTiming]:
        """All absolute-aligned words in time order (monotonicity verified)."""
        return [w for seg in self.segments for w in (seg.words or [])]


def convert_words_to_absolute(
    words: list[tuple[str, float, float, float | None]], clip_start_sec: float
) -> list[WordTiming]:
    """Convert clip-local (start, end) word timings to absolute source times.

    Pure function: absolute = clip_start_sec + local. Negative local times
    are clamped to 0 so no word ever lands before the video start.
    """
    converted: list[WordTiming] = []
    for word, local_start, local_end, probability in words:
        start = max(0.0, clip_start_sec + float(local_start))
        end = max(start, clip_start_sec + float(local_end))
        converted.append(WordTiming(word=word, start=start, end=end, probability=probability))
    return converted


def validate_word_absolute_timings(
    words: list[WordTiming],
    clip_start_sec: float,
    clip_end_sec: float,
) -> str | None:
    """Consistency checks; returns a failure reason string or None when valid.

    Checks (all deterministic, no heuristic scoring):
    1. Every word has a non-empty token and 0 <= start < end.
    2. Words lie within [clip_start - tolerance, clip_end + tolerance].
    3. Word timings are non-monotonic-free: a later word must not *start*
       far before the previous word started (bounded overlap).
    4. At least one word exists.
    """
    if len(words) < _MIN_WORDS_FOR_RELIABLE:
        return "no_words_detected"
    tolerance = _END_TOLERANCE_SEC
    for w in words:
        if not w.word or w.end <= w.start:
            return "invalid_word_bounds"
        if w.start < clip_start_sec - tolerance or w.end > clip_end_sec + tolerance:
            return "word_outside_clip_range"
    for prev, cur in zip(words, words[1:], strict=False):
        if cur.start + _MAX_WORD_OVERLAP_SECONDS < prev.start:
            return "non_monotonic_words"
    return None


@dataclass
class _ClipModelHandle:
    """Binds the shared whisper model with per-call parameters."""

    model: object
    beam_size: int
    vad_filter: bool


async def align_clip_words(
    clip_audio_path: Path,
    clip_start_ms: int,
    clip_duration_ms: int,
    language: str | None = None,
    model_size: str | None = None,
    compute_type: str | None = None,
    beam_size: int | None = None,
    vad_filter: bool = False,
    cancel_event: asyncio.Event | None = None,
    progress_callback=None,
) -> AlignedClip:
    """Re-time words for one selected clip and convert back to absolute time.

    Args:
        clip_audio_path: 16 kHz mono WAV holding only the clip audio.
        clip_start_ms: Clip start within the source media (absolute).
        clip_duration_ms: Clip length in milliseconds.
        language: Language hint; prefer the stored transcript language to
            avoid re-detection latency and language-switch hallucination.
        model_size: Overlay model; defaults to settings.CLIP_ALIGNMENT_MODEL.
        compute_type: CTranslate2 compute type; defaults to global default.
        beam_size: Beam width; defaults to settings.CLIP_ALIGNMENT_BEAM_SIZE (5).
        vad_filter: VAD switch; disabled by default so short clips keep
            leading/trailing speech context aligned.
        cancel_event: Cooperative cancellation flag.
        progress_callback: Optional (percent, stage) reporter; percent is
            an estimate only when clip duration is known locally.

    Raises:
        TranscriptionError: Model/audio problems surfaced to the caller,
            which falls back to segment-level captions instead of failing
            the render.
        JobCancelledError: When cancel_event is set (propagates).
    """
    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    if not clip_audio_path.is_file():
        raise TranscriptionError(
            f"Clip audio does not exist at {clip_audio_path}",
            error_code="AUDIO_NOT_FOUND",
        )

    effective_model = model_size or settings.CLIP_ALIGNMENT_MODEL
    effective_beam = beam_size if beam_size is not None else settings.CLIP_ALIGNMENT_BEAM_SIZE

    if progress_callback:
        progress_callback(2.0, "loading_clip_alignment_model")

    model = await load_whisper_model(effective_model, compute_type=compute_type)

    if cancel_event and cancel_event.is_set():
        raise JobCancelledError()

    if progress_callback:
        progress_callback(10.0, "aligning_selected_clips")

    clip_start_sec = clip_start_ms / 1000.0
    clip_end_sec = clip_start_sec + clip_duration_ms / 1000.0

    def _start_clip_transcription():
        # Clip files are small; the streamed wave fast path bounds RAM.
        audio = _decode_audio_to_float32(clip_audio_path)
        return model.transcribe(
            audio,
            language=language,
            beam_size=max(1, int(effective_beam)),
            word_timestamps=True,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

    segments_gen, info = await asyncio.to_thread(_start_clip_transcription)
    detected_language = getattr(info, "language", None)

    raw_words: list[tuple[str, float, float, float | None]] = []

    def _next_segment(iterator):
        try:
            return next(iterator), False
        except StopIteration:
            return None, True

    iterator = iter(segments_gen)
    while True:
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        seg, is_done = await asyncio.to_thread(_next_segment, iterator)
        if is_done:
            break
        if seg is None:
            continue
        for w in getattr(seg, "words", None) or []:
            token = str(w.word).strip()
            if not token:
                continue
            raw_words.append(
                (
                    token,
                    float(w.start),
                    float(w.end),
                    float(w.probability) if getattr(w, "probability", None) is not None else None,
                )
            )
            if progress_callback and getattr(info, "duration", 0) > 0:
                pct = min(95.0, 10.0 + 85.0 * (float(w.end) / float(info.duration)))
                progress_callback(pct, "aligning_selected_clips")

    absolute_words = convert_words_to_absolute(raw_words, clip_start_sec)
    failure = validate_word_absolute_timings(absolute_words, clip_start_sec, clip_end_sec)
    if failure:
        raise TranscriptionError(
            f"Clip word re-timing failed consistency check: {failure}. "
            "The transcript itself remains valid; captions fall back to "
            "segment-level timing.",
            error_code=f"ALIGNMENT_{failure.upper()}",
        )

    aligned_segments = _group_words_into_segments(absolute_words)
    if not aligned_segments:
        raise TranscriptionError(
            "Clip word re-timing produced no usable transcript for this clip.",
            error_code="ALIGNMENT_EMPTY",
        )

    logger.info(
        f"Clip alignment succeeded: {len(absolute_words)} words re-timed for "
        f"[{clip_start_ms} ms, {clip_start_ms + clip_duration_ms} ms] "
        f"(model={effective_model}, beam={effective_beam}, "
        f"language={language or detected_language})"
    )
    return AlignedClip(
        provider="faster-whisper-clip",
        model=effective_model,
        language=language or detected_language,
        clip_start_sec=clip_start_sec,
        clip_end_sec=clip_end_sec,
        segments=aligned_segments,
        word_count=len(absolute_words),
        beam_size=effective_beam,
    )


def _group_words_into_segments(words: list[WordTiming]) -> list[TranscriptSegment]:
    """Group absolute words into caption-friendly segments.

    Words are split into a new grouped segment when the pause between them
    exceeds ``_SEGMENT_SPLIT_PAUSE_SECONDS`` (0.6 s) - short enough that
    Arabic phrasing produces readable caption-sized groups. Text uses the
    aligned tokens so visual words match karaoke timings exactly.
    """
    if not words:
        return []
    segments: list[TranscriptSegment] = []
    current: list[WordTiming] = [words[0]]
    for w in words[1:]:
        if w.start - current[-1].end > _SEGMENT_SPLIT_PAUSE_SECONDS:
            segments.append(_segment_from_words(current, len(segments)))
            current = [w]
        else:
            current.append(w)
    segments.append(_segment_from_words(current, len(segments)))
    return segments


def _segment_from_words(words: list[WordTiming], index: int) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg_aligned_{index + 1:04d}",
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(w.word for w in words).strip(),
        words=list(words),
    )
