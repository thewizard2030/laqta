"""Stage s02_transcript — Pass 1 (Coarse Discovery).

Goal: transcribe the FULL 16 kHz WAV as fast as possible WITHOUT
word-level timestamps (architectural rule 4). Word timing happens only in
Pass 2 (:mod:`qatta.stages.s02_transcript.fine_pass`) for winning clips.

Selectable strategies (``settings.transcription_backend``):

- ``local_turbo`` (default): faster-whisper CT2 turbo model wrapped in
  ``BatchedInferencePipeline``; ``beam_size=1``, ``word_timestamps=False``,
  ``condition_on_previous_text=False``, ``vad_filter=True``; compute type
  and batch size auto-tuned per device (CUDA → ``int8_float16``/16,
  CPU → ``int8``/4 — the 8 GB-safe default).
- ``groq_api`` (cloud, OPTIONAL, fail-closed): chunks the WAV into
  ``groq_chunk_seconds`` (default 15 min) ``.ogg`` files (32 kbps) and
  transcribes them concurrently through Groq's ``whisper-large-v3-turbo``
  endpoint via ``httpx.AsyncClient``. Requires ``QATTA_ALLOW_CLOUD_APIS``
  plus an API key; the transcript leaves the device — that trade-off is
  exactly what the user opts into.
- ``youtube_subs_first``: captions-first (:mod:`qatta.stages.
  s02_transcript.youtube_subs`). The platform caption track (manual subs
  preferred, auto-generated as fallback) is fetched with a yt-dlp
  ``skip_download`` call — NO local Whisper on the long media, and the
  media itself is NOT downloaded here. Cue timings ARE real platform
  timestamps; they are grouped into utterances with the same acoustic
  pause logic (cue spans act as detected speech runs, so splits occur
  only at caption gaps >= ``pause_split_ms``). All word-level timing
  still happens in Pass 2 locally on the winning clips.

Both real strategies share the Arablish code-switching ``initial_prompt``
so English technical terms stay in Latin script inside Arabic sentences
(architectural rule 5).

After transcription, segments are merged with ACOUSTIC pause detection
(frame-level RMS energy gating on the PCM — the same mechanism
``librosa.effects.split`` uses, implemented locally in numpy so no extra
dependency is required). A split between two ASR segments happens only
when a real silence of at least ``settings.pause_split_ms`` (default
350 ms) occupies the gap; otherwise segments are merged. Every resulting
``AtomicUtterance`` boundary therefore aligns with a real acoustic pause
(or, when no acoustic runs can be detected at all — e.g. pathological
audio — segments are split on long ASR gaps as an honest degraded mode).
"""

from __future__ import annotations

import asyncio
import gc
import io
import json
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import AtomicUtterance, QattaManifest

ARABISH_INITIAL_PROMPT = (
    "محاضرة وبودكاست باللهجة المصرية والعربية مع مصطلحات تقنية مثل "
    "AI, API, SaaS, Startup, Deployment, Marketing, ROI."
)

_CTRANSLATE2_COMPUTE_BY_DEVICE = {"cuda": "int8_float16", "cpu": "int8"}
_BATCH_PER_DEVICE = {"cuda": 16, "cpu": 4}


@dataclass(frozen=True)
class TranscriptSegment:
    """One ASR segment with REAL measured (ms) boundaries."""

    start_ms: int
    end_ms: int
    text: str
    language: str | None = None


@dataclass(frozen=True)
class WordTiming:
    """One word-level timing (Pass 2 vocabulary)."""

    word: str
    start_ms: int
    end_ms: int
    confidence: float


class TranscriptionAdapter:
    """Duck-typed adapter API for Pass 1 (segments) and Pass 2 (words).

    Adapters own their heaviness: real adapters import faster-whisper or
    httpx lazily so importing this module stays cheap and unit tests run
    with mock adapters only.
    """

    def transcribe(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        initial_prompt: str | None = None,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        raise NotImplementedError("This adapter does not support segment transcription.")

    def transcribe_words(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        language: str | None = None,
        beam_size: int = 2,
    ) -> list[WordTiming]:
        raise NotImplementedError("This adapter does not support word transcription.")

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release heavy resources (models, HTTP clients)."""


# ---------------------------------------------------------------------------
# Shared audio helpers (stdlib wave only — s01 guarantees the WAV layout)
# ---------------------------------------------------------------------------


def load_pcm_16k(path: str | Path) -> tuple[np.ndarray, int]:
    """Load the s01_ingest WAV as float32 mono 16 kHz pcm.

    The ingest stage guarantees s16le/mono/16 kHz, so the standard library
    is enough. Anything else is an honest, actionable error instead of a
    silent resample.
    """
    try:
        with wave.open(str(path), "rb") as handle:
            sr = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            if (sr, channels, width) != (16000, 1, 2):
                raise PipelineError(
                    f"{path} is {sr} Hz / {channels} ch / {width * 8}-bit; "
                    "stage s02 requires the 16 kHz mono s16le PCM produced "
                    "by s01_ingest. Re-run s01_ingest instead of feeding "
                    "raw media."
                )
            raw = handle.readframes(handle.getnframes())
    except PipelineError:
        raise
    except wave.Error as e:
        raise PipelineError(f"{path} is not a readable WAV file: {e}") from e
    except OSError as e:
        raise PipelineError(f"Cannot read {path}: {e}") from e

    if not raw:
        raise PipelineError(f"{path} contains no audio frames.")
    pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return pcm, sr


def audio_total_ms(pcm: np.ndarray, sr: int) -> int:
    if len(pcm) == 0:
        return 0
    return int(round(len(pcm) * 1000 / sr))


def write_wav_16bit(pcm: np.ndarray, sr: int, path: Path) -> None:
    """Write float32 mono pcm as 16-bit PCM WAV (stdlib only)."""
    samples = np.clip(np.rint(pcm * 32768.0), -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(samples.tobytes())
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Acoustic pause detection (pure numpy; no librosa/silero dependency)
# ---------------------------------------------------------------------------


def frame_rms(pcm: np.ndarray, sr: int, frame_ms: int = 30, hop_ms: int = 10) -> np.ndarray:
    """Per-frame RMS energy (frame/hop in ms) of 16 kHz mono pcm."""
    frame = max(1, int(sr * frame_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    if len(pcm) < frame:
        return np.empty(0, dtype=np.float64)
    n_frames = 1 + (len(pcm) - frame) // hop
    windows = np.lib.stride_tricks.sliding_window_view(pcm, frame)[::hop]
    windows = windows[:n_frames]
    return np.sqrt(np.mean(windows.astype(np.float64) ** 2, axis=1))


def detect_speech_runs(
    pcm: np.ndarray,
    sr: int = 16000,
    silence_ms: int = 350,
    frame_ms: int = 30,
    hop_ms: int = 10,
    noise_factor: float = 1.5,
) -> list[tuple[int, int]]:
    """Detect acoustic speech runs as (start_ms, end_ms) tuples.

    Energy-gated: a frame is "speech" when its RMS exceeds
    ``max(noise_floor * noise_factor, global_peak * 0.04)``. Speech runs
    separated by silence shorter than ``silence_ms`` are merged. The
    result is deterministic for identical PCM.
    """
    rms = frame_rms(pcm, sr, frame_ms, hop_ms)
    if rms.size == 0:
        return []

    peak = float(rms.max())
    if peak <= 0:
        return []
    noise_floor = float(np.percentile(rms, 20))
    threshold = max(noise_floor * noise_factor, peak * 0.04)
    speech = rms >= threshold

    frames: list[tuple[int, int]] = []
    start_idx: int | None = None
    for idx, is_speech in enumerate(speech.tolist()):
        if is_speech and start_idx is None:
            start_idx = idx
        elif not is_speech and start_idx is not None:
            frames.append((start_idx, idx))
            start_idx = None
    if start_idx is not None:
        frames.append((start_idx, len(speech)))

    runs: list[tuple[int, int]] = []
    for a, b in frames:
        start_ms = a * hop_ms
        end_ms = (b - 1) * hop_ms + frame_ms
        if runs and start_ms - runs[-1][1] < silence_ms:
            prev_start = runs[-1][0]
            runs[-1] = (prev_start, end_ms)
        else:
            runs.append((start_ms, end_ms))
    return runs


def silence_intervals_of(runs: list[tuple[int, int]], total_ms: int) -> list[tuple[int, int]]:
    """Complement of speech runs across ``[0, total_ms)``."""
    silences: list[tuple[int, int]] = []
    cursor = 0
    for start, end in runs:
        if start > cursor:
            silences.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_ms:
        silences.append((cursor, total_ms))
    return silences


# ---------------------------------------------------------------------------
# Segment + acoustic merge -> AtomicUtterance
# ---------------------------------------------------------------------------


def _clean_segments(segments: list[TranscriptSegment], total_ms: int) -> list[TranscriptSegment]:
    cleaned: list[TranscriptSegment] = []
    for seg in sorted(segments, key=lambda s: (s.start_ms, s.end_ms)):
        text = seg.text.strip()
        if not text:
            continue
        start = max(0, min(int(seg.start_ms), total_ms))
        end = max(0, min(int(seg.end_ms), total_ms))
        if end <= start:
            end = min(total_ms, start + 10)
        cleaned.append(TranscriptSegment(start, end, text, seg.language))
    return cleaned


def span_rms(pcm: np.ndarray, sr: int, start_ms: int, end_ms: int) -> float:
    """RMS amplitude of [start_ms, end_ms) (0.0 for empty spans)."""
    i0 = max(0, int(start_ms * sr / 1000))
    i1 = max(i0 + 1, int(end_ms * sr / 1000))
    span = pcm[i0:i1].astype(np.float64)
    if span.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(span**2)))


def build_atomic_utterances(
    segments: list[TranscriptSegment],
    speech_runs: list[tuple[int, int]],
    total_ms: int,
    pcm: np.ndarray,
    sr: int,
    pause_ms: int = 350,
) -> list[AtomicUtterance]:
    """Merge ASR segments into utterances split ONLY at real pauses.

    A split between consecutive segments is accepted when a detected
    silence interval of length >= ``pause_ms`` intersects the gap between
    them; the boundary is placed at the midpoint of that intersection
    (clamped into the gap). Otherwise the segments are merged — an
    utterance boundary never floats mid-speech.

    ``audio_rms_norm`` is each utterance's RMS divided by the LOUDEST
    utterance's RMS, clamped to [0, 1]. ``pause_after_ms`` is the real
    distance to the next utterance's start.
    """
    segs = _clean_segments(segments, total_ms)
    if not segs:
        return []

    silences = silence_intervals_of(speech_runs, total_ms)
    groups: list[list[TranscriptSegment]] = [[segs[0]]]
    acoustic_available = bool(speech_runs)

    for prev, nxt in pairwise(segs):
        window_start = max(0, min(prev.end_ms, total_ms))
        window_end = max(window_start, min(nxt.start_ms, total_ms))
        boundary: int | None = None
        if window_end > window_start:
            for s0, s1 in silences:
                if s1 - s0 < pause_ms:
                    continue
                overlap_start = max(s0, window_start)
                overlap_end = min(s1, window_end)
                if overlap_end > overlap_start:
                    boundary = (overlap_start + overlap_end) // 2
                    break
        if boundary is None:
            if acoustic_available:
                # No qualifying acoustic pause in the gap -> merge.
                groups[-1].append(nxt)
                continue
            # Degraded mode: no speech runs detected at all — fall back to
            # splitting on long ASR gaps only, so output still works.
            boundary = (window_start + window_end) // 2
        groups.append([nxt])

    spans: list[tuple[int, int, list[TranscriptSegment]]] = []
    for group in groups:
        start = max(0, min(seg.start_ms for seg in group))
        end = min(total_ms, max(seg.end_ms for seg in group))
        if end <= start:
            end = min(total_ms, start + 10)
        spans.append((start, end, group))

    raw_rms = [span_rms(pcm, sr, start, end) for start, end, _ in spans]
    loudest = max(raw_rms, default=0.0)

    utterances: list[AtomicUtterance] = []
    for index, (start, end, group) in enumerate(spans):
        text = " ".join(seg.text for seg in group)
        utterances.append(
            AtomicUtterance(
                u_id=f"U_{index + 1:04d}",
                start_ms=start,
                end_ms=end,
                text=text,
                audio_rms_norm=(
                    0.0 if loudest <= 0 else min(1.0, max(0.0, raw_rms[index] / loudest))
                ),
                pause_after_ms=0,
                words=[],
            )
        )
    for utt, nxt in pairwise(utterances):
        utt.pause_after_ms = max(0, nxt.start_ms - utt.end_ms)
    return utterances


# ---------------------------------------------------------------------------
# Strategy A: Groq cloud transcriber (OPTIONAL, fail-closed, chunked)
# ---------------------------------------------------------------------------


def _parse_groq_response(data: dict) -> list[TranscriptSegment]:
    """Parse Groq verbose_json into chunk-relative segments."""
    segments_raw = data.get("segments")
    if not segments_raw:
        text = (data.get("text") or "").strip()
        if not text:
            return []
        # Honest fallback when a server omits `segments`.
        return [TranscriptSegment(0, 10, text)]
    out: list[TranscriptSegment] = []
    for seg in segments_raw:
        try:
            start = int(round(float(seg["start"]) * 1000))
            end = int(round(float(seg["end"]) * 1000))
        except (KeyError, TypeError, ValueError):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append(TranscriptSegment(start, max(start, end), text, seg.get("language")))
    return out


def _make_groq_client(timeout_seconds: float):
    import httpx

    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": "qatta-core/0.1"},
    )


class GroqWhisperTranscriber(TranscriptionAdapter):
    """Groq ``whisper-large-v3-turbo`` adapter for Pass 1.

    The 16 kHz WAV is split into ``chunk_seconds`` (default 900 s = 15
    min) slices, each re-encoded to ``.ogg`` at 32 kbps via FFmpeg and
    POSTed concurrently (bounded by ``max_concurrency``) with bounded
    retries on transient errors. Chunk results are offset-corrected back
    to absolute milliseconds. The endpoint used is always Groq's
    OpenAI-compatible ``/audio/transcriptions``.
    """

    model_name = "whisper-large-v3-turbo"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        chunk_seconds: int = 900,
        max_concurrency: int = 4,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        http_client=None,
        sr: int = 16000,
    ):
        if not api_key:
            raise PipelineError(
                "GroqWhisperTranscriber requires an API key; refusing to "
                "send unauthenticated requests."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chunk_seconds = chunk_seconds
        self.max_concurrency = max_concurrency
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._http_client = http_client  # injectable for tests
        self._sr = sr

    def _encode_chunk_ogg(self, chunk_pcm: np.ndarray, out_path: Path) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise PipelineError(
                "ffmpeg is required to encode Groq chunks to .ogg "
                "(on Fedora: 'sudo dnf install ffmpeg')."
            )
        with tempfile.TemporaryDirectory(prefix="qatta_groq_") as tmp:
            wav_path = Path(tmp) / "chunk.wav"
            write_wav_16bit(chunk_pcm, self._sr, wav_path)
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(wav_path),
                    "-vn",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "32k",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise PipelineError(f"FFmpeg failed to encode chunk {out_path.name} to .ogg.")
        return out_path

    async def _post_chunk(
        self,
        client,
        ogg_path: Path,
        initial_prompt: str | None,
        language: str | None,
    ) -> list[TranscriptSegment]:
        payload = ogg_path.read_bytes()
        data: dict[str, str] = {
            "model": self.model_name,
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if initial_prompt:
            data["prompt"] = initial_prompt
        if language:
            data["language"] = language

        attempts = 0
        backoff = 0.5
        while True:
            attempts += 1
            try:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (ogg_path.name, payload, "audio/ogg")},
                    data=data,
                )
            except Exception as e:  # network layer
                if attempts > self.max_retries:
                    raise PipelineError(f"Groq transcription request failed: {e}") from e
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                if attempts > self.max_retries:
                    body = (response.text or "")[:500]
                    raise PipelineError(
                        f"Groq API returned {response.status_code} after "
                        f"{self.max_retries} retries: {body}"
                    )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            if response.status_code != 200:
                body = (response.text or "")[:500]
                raise PipelineError(f"Groq API returned {response.status_code}: {body}")
            try:
                body_json = response.json()
            except json.JSONDecodeError as e:
                raise PipelineError("Groq API returned a non-JSON response.") from e
            return _parse_groq_response(body_json)

    async def transcribe_async(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        initial_prompt: str | None = None,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        if sr != self._sr:
            raise PipelineError(f"Groq adapter expects {self._sr} Hz mono PCM.")
        total_ms = audio_total_ms(pcm, sr)
        chunk_ms = self.chunk_seconds * 1000
        chunks: list[tuple[int, np.ndarray]] = []
        for start in range(0, total_ms, chunk_ms):
            end = min(total_ms, start + chunk_ms)
            chunks.append((start, pcm[int(start * sr / 1000) : int(end * sr / 1000)]))
        if not chunks:
            raise PipelineError("Audio contains no samples to transcribe.")

        with tempfile.TemporaryDirectory(prefix="qatta_groq_") as tmp:
            encoded: dict[int, Path] = {}
            try:
                for idx, (_, part) in enumerate(chunks):
                    encoded[idx] = self._encode_chunk_ogg(part, Path(tmp) / f"chunk_{idx:04d}.ogg")

                client = self._http_client or _make_groq_client(self.timeout_seconds)
                owned = self._http_client is None
                if owned:
                    await client.__aenter__()

                async def one(idx: int):
                    # Bounded concurrency: never open more requests at once
                    # than the caller asked for.
                    async with asyncio.Semaphore(self.max_concurrency):
                        return idx, await self._post_chunk(
                            client,
                            encoded[idx],
                            initial_prompt,
                            language,
                        )

                try:
                    results = await asyncio.gather(*(one(idx) for idx in sorted(encoded)))
                finally:
                    if owned:
                        await client.__aexit__(None, None, None)
            finally:
                for path in encoded.values():
                    path.unlink(missing_ok=True)

        merged: list[TranscriptSegment] = []
        for idx, chunk_segments in results:  # type: ignore[name-defined]
            chunk_start_ms = chunks[idx][0]
            for seg in chunk_segments:
                merged.append(
                    TranscriptSegment(
                        start_ms=chunk_start_ms + seg.start_ms,
                        end_ms=chunk_start_ms + seg.end_ms,
                        text=seg.text,
                        language=seg.language,
                    )
                )
        return _clean_segments(merged, total_ms)

    def transcribe(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        initial_prompt: str | None = None,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        return asyncio.run(self.transcribe_async(pcm, sr, initial_prompt, language))


# ---------------------------------------------------------------------------
# Strategy B: local faster-whisper turbo (batched), CPU/GPU auto-tuned
# ---------------------------------------------------------------------------


class LocalTurboBatchedTranscriber(TranscriptionAdapter):
    """faster-whisper CT2 turbo wrapped in BatchedInferencePipeline.

    Device/compute/batch defaults (auto-tuned, overridable):
    - CUDA detected (via ctranslate2): ``compute_type="int8_float16"``,
      batch 16.
    - Otherwise CPU: ``compute_type="int8"``, batch 4 (8 GB safe).

    Pass 1 (:meth:`transcribe`) uses ``beam_size=1``,
    ``word_timestamps=False``, ``condition_on_previous_text=False``,
    ``vad_filter=True``. Pass 2 (:meth:`transcribe_words`) uses
    ``word_timestamps=True`` with ``vad_filter=False`` — VAD trimming
    would shift slice-relative timestamps and break offset math.
    """

    def __init__(
        self,
        model_name: str = "deepdml/faster-whisper-large-v3-turbo-ct2",
        batch_size: int | None = None,
        compute_type: str | None = None,
        device: str | None = None,
        cpu_threads: int | None = None,
        beam_size: int = 1,
    ):
        self.model_name = model_name
        self.requested_batch = batch_size
        self.requested_compute = compute_type
        self.requested_device = device
        self.beam_size = beam_size
        self._cpu_threads = cpu_threads or min(4, os.cpu_count() or 2)
        self._model = None
        self._pipeline = None

    def resolve_compute_plan(self) -> dict[str, object]:
        """Resolved (device, compute_type, batch) without loading weights."""
        device = self.requested_device
        if device is None:
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        return {
            "device": device,
            "compute_type": self.requested_compute
            or _CTRANSLATE2_COMPUTE_BY_DEVICE.get(device, "int8"),
            "batch_size": self.requested_batch or _BATCH_PER_DEVICE.get(device, 4),
        }

    def _ensure_model(self):
        if self._model is None:
            try:
                from faster_whisper import (
                    BatchedInferencePipeline,
                    WhisperModel,
                )
            except ImportError as e:
                raise PipelineError(
                    "faster-whisper is not installed in this environment; "
                    "install it (pip install faster-whisper) or select a "
                    "different transcription backend. No work was faked."
                ) from e
            plan = self.resolve_compute_plan()
            self._model = WhisperModel(
                self.model_name,
                device=str(plan["device"]),
                compute_type=str(plan["compute_type"]),
                cpu_threads=self._cpu_threads,
            )
            try:
                batch = int(plan["batch_size"])
                self._pipeline = BatchedInferencePipeline(model=self._model) if batch > 1 else None
            except Exception:
                # Batched pipeline unusable on this install: the plain
                # model still produces full transcripts, only slower.
                self._pipeline = None
        return self._model

    def transcribe(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        initial_prompt: str | None = None,
        language: str | None = None,
    ) -> list[TranscriptSegment]:
        if sr != 16000:
            raise PipelineError("LocalTurboBatchedTranscriber expects 16 kHz mono PCM.")
        model = self._ensure_model()
        kwargs = dict(
            audio=pcm,
            language=language,
            initial_prompt=initial_prompt,
            beam_size=self.beam_size,
            word_timestamps=False,
            condition_on_previous_text=False,
            vad_filter=True,
        )
        if self._pipeline is not None:
            iterator, info = self._pipeline.transcribe(**kwargs)
        else:
            iterator, info = model.transcribe(**kwargs)
        segments = [
            TranscriptSegment(
                start_ms=int(round(seg.start * 1000)),
                end_ms=int(round(seg.end * 1000)),
                text=(seg.text or "").strip(),
                language=info.language,
            )
            for seg in iterator
            if (seg.text or "").strip()
        ]
        return segments

    def transcribe_words(
        self,
        pcm: np.ndarray,
        sr: int = 16000,
        language: str | None = None,
        beam_size: int = 2,
    ) -> list[WordTiming]:
        if sr != 16000:
            raise PipelineError("LocalTurboBatchedTranscriber expects 16 kHz mono PCM.")
        model = self._ensure_model()
        iterator, _info = model.transcribe(
            audio=pcm,
            language=language,
            beam_size=beam_size,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,  # trimming would shift slice-relative ms
        )
        words: list[WordTiming] = []
        for seg in iterator:
            for token in seg.words or []:
                text = (token.word or "").strip()
                if not text:
                    continue
                start = int(round(token.start * 1000))
                end = max(start + 1, int(round(token.end * 1000)))
                words.append(
                    WordTiming(
                        word=text,
                        start_ms=start,
                        end_ms=end,
                        confidence=min(1.0, max(0.0, float(token.probability))),
                    )
                )
        return words

    def close(self) -> None:
        """Free model memory (important on the 8 GB target machine)."""
        if self._pipeline is not None:
            del self._pipeline
        if self._model is not None:
            del self._model
        self._pipeline = None
        self._model = None
        gc.collect()


# ---------------------------------------------------------------------------
# Strategy selection (fail-closed) + Pass 1 stage entry point
# ---------------------------------------------------------------------------


def _require_permitted_backend(settings: QattaSettings) -> str:
    """Defense in depth: the orchestrator also gates transcription stages."""
    backend = settings.transcription_backend
    if backend == "local_turbo":
        return backend
    if backend == "groq_api":
        if not settings.cloud_backend_permitted(backend):
            raise PipelineError(
                "Cloud transcription (groq_api) requires BOTH an API key "
                "(QATTA_GROQ_API_KEY) and explicit opt-in "
                "(QATTA_ALLOW_CLOUD_APIS=true). Transcript text would "
                "leave the device; nothing was sent."
            )
        if not settings.groq_api_key:
            raise PipelineError("groq_api selected but QATTA_GROQ_API_KEY is empty.")
        return backend
    if backend == "youtube_subs_first":
        if not settings.cloud_backend_permitted(backend):
            raise PipelineError(
                "Captions-first transcription (youtube_subs_first) "
                "requires URL ingestion to be enabled "
                "(QATTA_ENABLE_URL_INGESTION=true); it is not enabled "
                "on this machine, so nothing was fetched."
            )
        return backend
    raise PipelineError(
        f"Transcription backend '{backend}' is not implemented in the "
        "core package yet; use local_turbo (default) or groq_api "
        "(opt-in). No work was faked or attempted."
    )


def select_transcriber(settings: QattaSettings) -> TranscriptionAdapter:
    """Instantiate the adapter for the (permitted) configured backend."""
    backend = _require_permitted_backend(settings)
    if backend == "groq_api":
        return GroqWhisperTranscriber(
            api_key=settings.groq_api_key or "",
            base_url=settings.groq_base_url,
            chunk_seconds=settings.groq_chunk_seconds,
            max_concurrency=settings.groq_max_concurrency,
            timeout_seconds=settings.groq_timeout_seconds,
        )
    return LocalTurboBatchedTranscriber(
        model_name=settings.turbo_model,
        batch_size=settings.turbo_batch_size,
        compute_type=settings.turbo_compute_type,
        beam_size=settings.turbo_beam_size,
    )


def _whisper_language(language_profile: str) -> str | None:
    lowered = (language_profile or "").lower()
    if lowered.startswith("ar"):
        return "ar"
    if lowered.startswith("en"):
        return "en"
    return None  # let Whisper auto-detect


def transcribe_segments(
    pcm: np.ndarray,
    sr: int,
    settings: QattaSettings,
    adapter: TranscriptionAdapter | None = None,
    language_profile: str = "",
) -> list[TranscriptSegment]:
    """Run Pass 1 with the configured adapter (caller owns the adapter).

    ``language_profile`` comes from the MANIFEST (e.g. ``ar-EG-mixed``);
    it is mapped to a Whisper language code, or None for auto-detect.
    """
    adapter = adapter or select_transcriber(settings)
    initial_prompt = settings.arabish_prompt_text if settings.arabish_initial_prompt else None
    return adapter.transcribe(
        pcm,
        sr,
        initial_prompt=initial_prompt,
        language=_whisper_language(language_profile),
    )


def run_youtube_subs_fast_pass(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
) -> QattaManifest:
    """Execute Pass 1 from the platform caption track (no Whisper).

    Requires the caption file saved by s01_ingest
    (``manifest.subtitle_path``). There is NO full-audio pass here: cue
    spans are the detected speech runs, and the shared acoustic builder
    groups segments the same way it merges ASR segments offline.
    ``audio_rms_norm`` stays 0.0 for all utterances (no local audio was
    measured — a documented limitation of the captions-first mode,
    surfaced instead of being fabricated).
    """
    from qatta.stages.s02_transcript.youtube_subs import (
        segments_from_youtube_subs,
    )

    settings = settings or QattaSettings()
    if not manifest.subtitle_path:
        raise PipelineError(
            "youtube_subs_first requires a caption track fetched by "
            "s01_ingest (manifest.subtitle_path). Pass 1 transcription "
            "did not run and nothing was faked."
        )
    subtitle_path = Path(manifest.subtitle_path)
    try:
        vtt_text = subtitle_path.read_text(encoding="utf-8")
    except OSError as e:
        raise PipelineError(f"Cannot read the stored caption file {subtitle_path}: {e}") from e

    segments = segments_from_youtube_subs(vtt_text)
    if not segments:
        raise PipelineError(
            f"The caption track at {subtitle_path} parsed to zero cues; "
            "Pass 1 produced nothing. Check the caption file or fall "
            "back to local Whisper."
        )

    # Speech runs derive from the REAL platform cue spans; total from the
    # probed duration. No local PCM exists in this mode.
    total_ms = int(round(manifest.duration_sec * 1000))
    runs = [(seg.start_ms, max(seg.end_ms, seg.start_ms + 1)) for seg in segments]
    utterances = build_atomic_utterances(
        segments,
        runs,
        total_ms,
        np.zeros(0, dtype=np.float32),
        16000,
        pause_ms=settings.pause_split_ms,
    )
    manifest.atomic_utterances = utterances
    manifest.transcript_source = "youtube_subs_first"
    return manifest


def run_fast_pass_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    adapter: TranscriptionAdapter | None = None,
) -> QattaManifest:
    """Execute stage s02_transcript (Pass 1) for the given manifest."""
    settings = settings or QattaSettings()
    if settings.transcription_backend == "youtube_subs_first" or (
        manifest.subtitle_path and Path(manifest.subtitle_path).is_file()
    ):
        # Captions-first or pre-downloaded captions: skip the local Whisper pass.
        _require_permitted_backend(settings)
        return run_youtube_subs_fast_pass(manifest, settings)
    if not manifest.audio_16k_path:
        raise PipelineError(
            "No audio_16k.wav in the manifest; run stage s01_ingest before s02_transcript."
        )
    if settings.backend_is_gated():
        # Consistent with the orchestrator gate; honest and fail-closed.
        _require_permitted_backend(settings)

    pcm, sr = load_pcm_16k(manifest.audio_16k_path)
    total_ms = audio_total_ms(pcm, sr)

    owned = adapter is None
    adapter = adapter or select_transcriber(settings)
    try:
        segments = transcribe_segments(
            pcm,
            sr,
            settings,
            adapter,
            language_profile=manifest.language_profile,
        )
        runs = detect_speech_runs(pcm, sr, silence_ms=settings.pause_split_ms)
        utterances = build_atomic_utterances(
            segments,
            runs,
            total_ms,
            pcm,
            sr,
            pause_ms=settings.pause_split_ms,
        )
    finally:
        if owned:
            adapter.close()

    if not utterances:
        raise PipelineError(
            "Pass 1 produced no utterances: the transcript is empty and "
            "the audio has no detectable speech. Nothing was persisted "
            "blindly — check the source audio and the backend."
        )
    manifest.atomic_utterances = utterances
    return manifest


def register(orchestrator, adapter: TranscriptionAdapter | None = None) -> None:
    """Attach s02_transcript; pass an adapter to stay test/mock-friendly."""

    @orchestrator.stage("s02_transcript")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_fast_pass_stage(manifest, orchestrator.settings, adapter=adapter)
