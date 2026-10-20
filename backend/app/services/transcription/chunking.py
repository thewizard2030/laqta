"""Long-audio inspection, overlapping chunking, and deduplicating merger.

Features:
- Pre-upload inspection of duration and file size against provider payload limits.
- Overlapping FFmpeg chunking to avoid cutting off mid-word syllables.
- Deduplication of overlapping words at chunk seams with absolute timestamp projection.
- Bounded exponential backoff retry runner for transient network errors and rate limits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.transcription.base import TranscriptionError

logger = logging.getLogger("qatta.transcription.chunking")


@dataclass
class AudioFileInfo:
    """Inspected audio properties."""

    path: Path
    duration_sec: float
    size_bytes: int
    format_name: str

    def __iter__(self):
        """Allow unpacking as (size_bytes, duration_sec)."""
        return iter((self.size_bytes, self.duration_sec))


@dataclass
class AudioChunk:
    """An audio slice with absolute offset timing."""

    chunk_index: int = 0
    file_path: Path = Path(".")
    start_sec: float = 0.0
    duration_sec: float = 0.0
    overlap_sec: float = 0.0
    path: Path | None = None
    index: int | None = None

    def __post_init__(self) -> None:
        if self.path is not None:
            self.file_path = self.path
        elif self.file_path is not None:
            self.path = self.file_path
        if self.index is not None:
            self.chunk_index = self.index
        elif self.chunk_index is not None:
            self.index = self.chunk_index


def inspect_audio_file(audio_path: Path) -> AudioFileInfo:
    """Inspect duration and file size using ffprobe."""
    if not audio_path.is_file():
        raise TranscriptionError(
            f"Audio file not found: {audio_path}",
            error_code="FILE_NOT_FOUND",
        )

    size_bytes = audio_path.stat().st_size
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        # Fallback estimation if ffprobe missing
        return AudioFileInfo(
            path=audio_path,
            duration_sec=0.0,
            size_bytes=size_bytes,
            format_name=audio_path.suffix.lstrip("."),
        )

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name",
        "-of",
        "json",
        str(audio_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0, check=False)
        if proc.returncode == 0:
            data = json.loads(proc.stdout or "{}")
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0.0))
            format_name = str(fmt.get("format_name", audio_path.suffix.lstrip(".")))
            return AudioFileInfo(
                path=audio_path,
                duration_sec=duration,
                size_bytes=size_bytes,
                format_name=format_name,
            )
    except Exception as e:
        logger.warning("ffprobe audio inspection warning for %s: %s", audio_path, e)

    return AudioFileInfo(
        path=audio_path,
        duration_sec=0.0,
        size_bytes=size_bytes,
        format_name=audio_path.suffix.lstrip("."),
    )


def split_audio_overlapping(
    audio_path: Path,
    output_dir: Path | None = None,
    chunk_duration_sec: float = 600.0,  # 10 minutes default
    overlap_sec: float = 2.0,  # 2 seconds overlap buffer
    sample_rate: int = 16000,
) -> list[AudioChunk]:
    """Split audio into overlapping chunks using safe FFmpeg argument arrays."""
    effective_dir = output_dir or Path(tempfile.mkdtemp(prefix="qatta_chunks_"))
    effective_dir.mkdir(parents=True, exist_ok=True)
    info = inspect_audio_file(audio_path)

    total_sec = info.duration_sec

    if total_sec <= 0.0:
        # Cannot determine duration; return single chunk
        return [
            AudioChunk(
                chunk_index=0,
                file_path=audio_path,
                start_sec=0.0,
                duration_sec=0.0,
                overlap_sec=0.0,
            )
        ]

    # If within chunk_duration, no split needed
    if total_sec <= chunk_duration_sec:
        return [
            AudioChunk(
                chunk_index=0,
                file_path=audio_path,
                start_sec=0.0,
                duration_sec=total_sec,
                overlap_sec=0.0,
            )
        ]

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise TranscriptionError(
            "ffmpeg is required to split long audio files into chunks.",
            error_code="FFMPEG_MISSING",
        )

    chunks: list[AudioChunk] = []
    step_sec = chunk_duration_sec - overlap_sec
    curr_start = 0.0
    index = 0

    while curr_start < total_sec:
        curr_dur = min(chunk_duration_sec, total_sec - curr_start)
        chunk_file = effective_dir / f"chunk_{index:04d}.wav"

        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{curr_start:.3f}",
            "-t",
            f"{curr_dur:.3f}",
            "-i",
            str(audio_path),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            str(chunk_file),
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120.0, check=False)
        if proc.returncode != 0 or not chunk_file.exists():
            raise TranscriptionError(
                f"Failed to extract chunk {index} from audio: {(proc.stderr or '')[-500:]}",
                error_code="AUDIO_EXTRACTION_FAILED",
            )

        chunks.append(
            AudioChunk(
                chunk_index=index,
                file_path=chunk_file,
                start_sec=curr_start,
                duration_sec=curr_dur,
                overlap_sec=overlap_sec if index > 0 else 0.0,
            )
        )

        curr_start += step_sec
        index += 1

    return chunks


def _clean_token(t: str) -> str:
    """Normalize token for string equality comparison."""
    return "".join(c for c in t.lower() if c.isalnum())


def merge_overlapping_segments(
    chunks: list[AudioChunk] | list[tuple[AudioChunk, list[TranscriptSegment]]],
    segments_or_overlap: list[list[TranscriptSegment]] | float = 2.0,
    overlap_sec: float = 2.0,
) -> list[TranscriptSegment]:
    """Merge segment lists from overlapping chunks with absolute timestamps and word deduplication.

    Eliminates duplicated words across chunk seams.
    """
    if not chunks:
        return []

    if isinstance(segments_or_overlap, list):
        chunks_results = list(zip(chunks, segments_or_overlap, strict=False))
        eff_overlap = overlap_sec
    else:
        chunks_results = chunks  # type: ignore
        eff_overlap = float(segments_or_overlap)

    merged: list[TranscriptSegment] = []
    seg_counter = 1

    for _chunk_idx, (chunk, segments) in enumerate(chunks_results):
        chunk_offset = chunk.start_sec

        # Project timestamps to absolute timeline
        projected_segments: list[TranscriptSegment] = []
        for s in segments:
            abs_start = round(s.start + chunk_offset, 3)
            abs_end = round(s.end + chunk_offset, 3)

            projected_words: list[WordTiming] | None = None
            if s.words:
                projected_words = [
                    WordTiming(
                        word=w.word,
                        start=round(w.start + chunk_offset, 3),
                        end=round(w.end + chunk_offset, 3),
                        probability=w.probability,
                    )
                    for w in s.words
                ]

            projected_segments.append(
                TranscriptSegment(
                    id=str(seg_counter),
                    start=abs_start,
                    end=abs_end,
                    text=s.text.strip(),
                    words=projected_words,
                    speaker=s.speaker,
                    avg_logprob=s.avg_logprob,
                    no_speech_prob=s.no_speech_prob,
                )
            )
            seg_counter += 1

        if not merged:
            merged.extend(projected_segments)
            continue

        # For subsequent chunks, handle the seam overlap with merged[-1]
        seam_boundary = chunk.start_sec + (eff_overlap / 2.0)

        # Collect recent words from the previous chunk
        recent_words: list[str] = []
        for prev_seg in reversed(merged[-3:]):
            if prev_seg.words:
                recent_words.extend([_clean_token(w.word) for w in reversed(prev_seg.words)])
            else:
                recent_words.extend([_clean_token(t) for t in reversed(prev_seg.text.split())])

        for curr_seg in projected_segments:
            # If segment ends before seam boundary, it was already covered by previous chunk
            if curr_seg.end <= seam_boundary:
                continue

            # If segment starts well after seam, include directly
            if curr_seg.start >= seam_boundary:
                merged.append(curr_seg)
                continue

            # Segment straddles seam: perform word-level deduplication
            if curr_seg.words:
                filtered_words: list[WordTiming] = []
                for w in curr_seg.words:
                    clean_w = _clean_token(w.word)
                    # Skip if word start is before seam and was in recent words
                    if w.start < seam_boundary and clean_w in recent_words[:6]:
                        continue
                    filtered_words.append(w)

                if filtered_words:
                    curr_seg.words = filtered_words
                    curr_seg.text = " ".join(w.word for w in filtered_words)
                    curr_seg.start = filtered_words[0].start
                    curr_seg.end = filtered_words[-1].end
                    merged.append(curr_seg)
            else:
                # Fallback text token deduplication
                tokens = curr_seg.text.split()
                deduped = [t for t in tokens if _clean_token(t) not in recent_words[:4]]
                if deduped:
                    curr_seg.text = " ".join(deduped)
                    curr_seg.start = max(curr_seg.start, seam_boundary)
                    merged.append(curr_seg)

    # Renumber segment IDs cleanly 1..N
    for idx, seg in enumerate(merged, start=1):
        seg.id = str(idx)

    return merged


async def retry_with_backoff(
    action: Callable[[], Coroutine[Any, Any, Any]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
    cancel_event: asyncio.Event | None = None,
    base_delay: float | None = None,
) -> Any:
    """Execute asynchronous action with bounded exponential backoff retries."""
    delay = base_delay if base_delay is not None else initial_delay
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        if cancel_event and cancel_event.is_set():
            raise TranscriptionError("Operation cancelled by user.", error_code="CANCELLED")

        try:
            return await action()
        except TranscriptionError as te:
            if te.error_code in ("AUTHENTICATION_ERROR", "CLOUD_TRANSCRIPTION_DISABLED"):
                raise
            last_exception = te
        except Exception as e:
            last_exception = e

        if attempt < max_retries:
            logger.info(
                "Transient transcription failure (attempt %d/%d). Retrying in %.2fs: %s",
                attempt + 1,
                max_retries,
                delay,
                last_exception,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise TranscriptionError(
                    "Operation cancelled during backoff.", error_code="CANCELLED"
                ) from None
            delay = min(max_delay, delay * 2.0)

    raise TranscriptionError(
        f"Operation failed after {max_retries} retries: {last_exception}",
        error_code="RETRIES_EXHAUSTED",
    ) from last_exception
