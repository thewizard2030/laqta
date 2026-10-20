"""Faster-whisper local CPU transcription provider implementation (PRD §5 FR-03).

Features:
- CPU-first defaults using int8 quantization for conservative memory on 8 GB RAM.
- Strict lazy model loading (never at import time).
- Segment and word-level timestamps with truthful granularity reporting.
- Cooperative cancellation between transcribed segments.
- Actionable error diagnostics for missing packages, out-of-memory, and download failures.
"""

import asyncio
import importlib.util
import os
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
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
)

# Global lazy cache for loaded models: (model_size, device, compute_type) -> WhisperModel
_LOADED_MODELS: dict[tuple[str, str, str], Any] = {}


def is_faster_whisper_installed() -> bool:
    """Check if faster-whisper package is installed in current Python environment."""
    return importlib.util.find_spec("faster_whisper") is not None


def find_local_whisper_snapshot(
    model_size_or_path: str,
    custom_dirs: list[Path] | None = None,
) -> str | None:
    """Locate an existing faster-whisper CTranslate2 model snapshot on local disk.

    Searches in order:
    1. Direct filesystem directory if model_size_or_path is already an existing path.
    2. Configured custom download directories (e.g. settings.get_whisper_models_dir()).
    3. Hugging Face environment variables ($HF_HUB_CACHE, $HF_HOME/hub).
    4. Default user Hugging Face cache (~/.cache/huggingface/hub).

    Returns the absolute path string to the directory containing model.bin, or None
    if no matching local model is found.
    """
    p = Path(model_size_or_path).expanduser().resolve()
    if p.is_dir() and (p / "model.bin").exists():
        return str(p)

    search_roots: list[Path] = []
    if custom_dirs:
        for cd in custom_dirs:
            if cd:
                search_roots.append(Path(cd).expanduser().resolve())

    if "HF_HUB_CACHE" in os.environ:
        search_roots.append(Path(os.environ["HF_HUB_CACHE"]).expanduser().resolve())
    if "HF_HOME" in os.environ:
        search_roots.append((Path(os.environ["HF_HOME"]) / "hub").expanduser().resolve())
    search_roots.append(Path.home() / ".cache" / "huggingface" / "hub")

    clean_name = model_size_or_path.strip()
    candidate_repo_names = [
        f"models--{clean_name.replace('/', '--')}",
        f"models--Systran--faster-whisper-{clean_name}",
        clean_name,
    ]
    lower = clean_name.lower()
    if lower != clean_name:
        candidate_repo_names.extend(
            [
                f"models--{lower.replace('/', '--')}",
                f"models--Systran--faster-whisper-{lower}",
                lower,
            ]
        )

    for root in search_roots:
        if not root.exists():
            continue
        # Direct folder in root
        direct = root / clean_name
        if direct.is_dir() and (direct / "model.bin").exists():
            return str(direct)

        # HF hub repo folders in root or root/hub
        for repo_name in candidate_repo_names:
            for cand_dir in [root / repo_name, root / "hub" / repo_name]:
                if cand_dir.is_dir():
                    snapshots_dir = cand_dir / "snapshots"
                    if snapshots_dir.is_dir():
                        for snap in sorted(snapshots_dir.iterdir(), reverse=True):
                            if snap.is_dir() and (snap / "model.bin").exists():
                                return str(snap)
                    elif (cand_dir / "model.bin").exists():
                        return str(cand_dir)
    return None


async def load_whisper_model(
    model_size: str,
    device: str | None = None,
    compute_type: str | None = None,
    download_root: Path | None = None,
    on_download_needed: Callable[[], None] | None = None,
) -> Any:
    """Load (or return cached) WhisperModel without blocking the event loop.

    Shared module-level loader used by both the transcription provider and
    the clip alignment service so a second job type never duplicates model
    memory for the same (model, device, compute) key.

    Prioritizes local cached snapshots across all standard locations so
    transcription works offline without making network calls when weights
    already exist on disk.
    """
    from app.services.transcription import faster_whisper_provider  # noqa: F401  # self

    device = device or settings.DEFAULT_WHISPER_DEVICE
    compute_type = compute_type or settings.DEFAULT_WHISPER_COMPUTE_TYPE
    download_root = download_root or settings.get_whisper_models_dir()

    cache_key = (model_size, device, compute_type)
    cached = _LOADED_MODELS.get(cache_key)
    if cached is not None:
        logger.info(f"Using cached faster-whisper model: {cache_key}")
        return cached

    logger.info(
        f"Loading faster-whisper model '{model_size}' "
        f"(device={device}, compute_type={compute_type})..."
    )

    def _do_load() -> Any:
        try:
            from faster_whisper import WhisperModel

            # 1. Discover local snapshot if already present on disk
            custom_dirs = [download_root]
            effective_dir = settings.get_whisper_models_dir()
            if effective_dir != download_root:
                custom_dirs.append(effective_dir)

            local_snap = find_local_whisper_snapshot(model_size, custom_dirs=custom_dirs)
            if local_snap:
                logger.info(
                    f"Loading faster-whisper model '{model_size}' from local cache: {local_snap}"
                )
                return WhisperModel(
                    model_size_or_path=local_snap,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=settings.WHISPER_CPU_THREADS,
                    num_workers=1,
                )

            # 2. Try offline loading via faster-whisper (local_files_only=True)
            for target_root in ([str(download_root)] if download_root else []) + [None]:
                try:
                    kwargs: dict[str, Any] = {
                        "device": device,
                        "compute_type": compute_type,
                        "cpu_threads": settings.WHISPER_CPU_THREADS,
                        "num_workers": 1,
                        "local_files_only": True,
                    }
                    if target_root:
                        kwargs["download_root"] = target_root
                    return WhisperModel(model_size, **kwargs)
                except Exception:
                    continue

            # 3. Model not found locally; download from Hugging Face hub to download_root
            if on_download_needed:
                on_download_needed()

            logger.info(
                f"Model '{model_size}' not found in local cache. "
                f"Downloading weights to {download_root}..."
            )
            return WhisperModel(
                model_size_or_path=model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(download_root),
                cpu_threads=settings.WHISPER_CPU_THREADS,
                num_workers=1,
                local_files_only=False,
            )
        except Exception as e:
            err_text = str(e).lower()
            if "memory" in err_text or "oom" in err_text:
                raise TranscriptionError(
                    f"Insufficient memory to load Whisper model '{model_size}'. "
                    "Try a lighter model such as 'tiny' or 'base' to protect 8 GB RAM.",
                    error_code="OUT_OF_MEMORY",
                ) from e
            elif (
                "download" in err_text
                or "connection" in err_text
                or "404" in err_text
                or "403" in err_text
                or "forbidden" in err_text
                or "policy" in err_text
                or "localentrynotfound" in err_text
                or "not found" in err_text
                or "offline" in err_text
                or "timeout" in err_text
            ):
                raise TranscriptionError(
                    f"Failed to download Whisper model '{model_size}' weights to "
                    f"{download_root}. Check your internet connection or "
                    "pre-download model weights for offline usage.",
                    error_code="MODEL_DOWNLOAD_FAILED",
                ) from e
            else:
                raise TranscriptionError(
                    f"Failed to initialize faster-whisper model '{model_size}': {e}",
                    error_code="MODEL_LOAD_ERROR",
                ) from e

    model = await asyncio.to_thread(_do_load)
    _LOADED_MODELS[cache_key] = model
    return model


def _decode_audio_to_float32(audio_path: Path, max_duration_sec: float | None = None) -> Any:
    """Decode any audio file to a float32 mono 16 kHz ndarray (device-neutral).

    Fast path: Python's standard library ``wave`` reads 16 kHz mono 16-bit PCM
    WAVs (as produced by ``extract_audio_16k``) in <50ms without frame-by-frame
    overhead or memory bloat on multi-hour audio files.

    Fallback: PyAV decoding for non-standard formats, omitting the deprecated
    ``metadata_errors`` argument to preserve PyAV 14+ compatibility.
    """
    import numpy as np

    max_samples = int(max_duration_sec * 16000) if max_duration_sec else None

    try:
        import wave

        with wave.open(str(audio_path), "rb") as wf:
            if wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == 16000:
                total_frames = wf.getnframes()
                if max_samples is not None:
                    total_frames = min(total_frames, max_samples)
                if total_frames <= 0:
                    return np.zeros(0, dtype=np.float32)
                # Streamed fill: allocate exactly one float32 buffer and copy
                # bounded chunks into it. Peak memory stays ~ audio size (4
                # bytes/sample for a full hour => 230 MB) instead of doubling
                # via unbounded readframes + frombuffer + concatenate.
                out = np.empty(total_frames, dtype=np.float32)
                frames_read = 0
                chunk_frames = 1 << 20  # ~2 MB int16 per chunk
                while frames_read < total_frames:
                    want = min(chunk_frames, total_frames - frames_read)
                    block = wf.readframes(want)
                    if not block:
                        break
                    samples = np.frombuffer(block, dtype=np.int16)
                    n = min(len(samples), total_frames - frames_read)
                    out[frames_read : frames_read + n] = samples[:n] / np.float32(32768.0)
                    frames_read += n
                    del block, samples
                if frames_read < total_frames:
                    out = out[:frames_read].copy()
                return out
    except Exception:
        pass

    import av

    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks: list[np.ndarray] = []
    with av.open(str(audio_path), mode="r") as container:
        for frame in container.decode(container.streams.audio[0]):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
            if max_samples and sum(len(c) for c in chunks) >= max_samples:
                break
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0
    if max_samples:
        audio = audio[:max_samples]
    return audio


class FasterWhisperProvider(TranscriptionProvider):
    """Local ASR provider using faster-whisper on CPU."""

    def is_available(self) -> bool:
        """Return True if faster-whisper library is importable."""
        return is_faster_whisper_installed()

    async def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        model_size: str = "base",
        word_timestamps: bool = True,
        cancel_event: asyncio.Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        max_duration_sec: float | None = None,
        compute_type: str | None = None,
        **kwargs: object,
    ) -> TranscriptionResult:
        """Execute faster-whisper transcription lazily in a thread pool."""
        # 1. Early cancellation check
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        # 2. Check package installation
        if not self.is_available():
            raise TranscriptionError(
                "faster-whisper is not installed in the Python environment. "
                "Install it using 'pip install faster-whisper' to enable local "
                "CPU speech recognition.",
                error_code="PACKAGE_NOT_INSTALLED",
            )

        # 3. Check audio input file existence
        if not audio_path.is_file():
            raise TranscriptionError(
                f"Audio file does not exist at {audio_path}",
                error_code="AUDIO_NOT_FOUND",
            )

        # 4. Lazy model loading in worker thread with GPU runtime verification
        req_device = str(kwargs.get("device") or settings.DEFAULT_WHISPER_DEVICE).lower()
        req_compute = compute_type or settings.DEFAULT_WHISPER_COMPUTE_TYPE
        download_root = settings.get_whisper_models_dir()
        fallback_reason: str | None = None
        effective_device = req_device
        effective_compute = req_compute

        if req_device == "cuda":
            cuda_count = 0
            try:
                import ctranslate2

                cuda_count = ctranslate2.get_cuda_device_count()
            except Exception as e:
                logger.warning("Failed to query CTranslate2 CUDA device count: %s", e)

            if cuda_count == 0:
                fallback_reason = "No CUDA devices detected by CTranslate2; running on CPU INT8"
                effective_device = "cpu"
                effective_compute = "int8"
                logger.info(fallback_reason)

        def _on_download():
            if progress_callback:
                progress_callback(5.0, "downloading_model")

        if progress_callback:
            progress_callback(5.0, "loading_model")

        try:
            model = await self._load_model_lazy(
                model_size,
                effective_device,
                effective_compute,
                download_root,
                on_download_needed=_on_download,
            )
        except Exception as e:
            if effective_device == "cuda":
                fallback_reason = f"CUDA model loading failed ({e}); falling back to CPU INT8"
                logger.warning("%s", fallback_reason)
                effective_device = "cpu"
                effective_compute = "int8"
                model = await self._load_model_lazy(
                    model_size,
                    effective_device,
                    effective_compute,
                    download_root,
                    on_download_needed=_on_download,
                )
            else:
                raise

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        if progress_callback:
            progress_callback(15.0, "transcribing")

        # 5. Run transcription
        return await self._transcribe_stream(
            model=model,
            audio_path=audio_path,
            language=language,
            model_size=model_size,
            word_timestamps=word_timestamps,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            beam_size=beam_size,
            vad_filter=vad_filter,
            max_duration_sec=max_duration_sec,
            device=effective_device,
            compute_type=effective_compute,
            fallback_reason=fallback_reason,
        )

    async def _load_model_lazy(
        self,
        model_size: str,
        device: str,
        compute_type: str,
        download_root: Path,
        on_download_needed: Callable[[], None] | None = None,
    ) -> Any:
        """Load or retrieve cached WhisperModel instance without blocking event loop."""
        return await load_whisper_model(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
            on_download_needed=on_download_needed,
        )

    async def _transcribe_stream(
        self,
        model: Any,
        audio_path: Path,
        language: str | None,
        model_size: str,
        word_timestamps: bool,
        cancel_event: asyncio.Event | None,
        progress_callback: Callable[[float, str], None] | None,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        max_duration_sec: float | None = None,
        device: str = "cpu",
        compute_type: str = "int8",
        fallback_reason: str | None = None,
    ) -> TranscriptionResult:
        """Consume transcription generator with cooperative cancellation."""
        effective_beam = beam_size if beam_size is not None else settings.WHISPER_BEAM_SIZE
        effective_vad = vad_filter if vad_filter is not None else settings.WHISPER_VAD_FILTER

        def _start_transcription():
            # Decode locally: avoids faster-whisper's internal decode_audio,
            # which crashes with PyAV >= 14 on Python 3.14 (metadata_errors).
            audio = _decode_audio_to_float32(audio_path, max_duration_sec=max_duration_sec)
            return model.transcribe(
                audio,
                language=language,
                beam_size=effective_beam,
                word_timestamps=word_timestamps,
                vad_filter=effective_vad,
                vad_parameters=dict(min_silence_duration_ms=500),
            )

        segments_gen, info = await asyncio.to_thread(_start_transcription)
        detected_language = info.language
        language_probability = getattr(info, "language_probability", None)
        duration = getattr(info, "duration", 0.0)

        logger.info(
            f"Transcription started: detected language '{detected_language}' "
            f"(prob={language_probability:.2f}), duration={duration:.2f}s"
        )

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []
        any_words = False

        # Consume generator incrementally
        def _get_next_segment(it):
            try:
                return next(it), False
            except StopIteration:
                return None, True

        iterator = iter(segments_gen)

        while True:
            # Check cancellation between segments
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            seg, is_done = await asyncio.to_thread(_get_next_segment, iterator)
            if is_done:
                break
            if seg is None:
                continue

            # Process word-level timings if returned
            segment_words: list[WordTiming] | None = None
            if hasattr(seg, "words") and seg.words:
                segment_words = []
                for w in seg.words:
                    word_obj = WordTiming(
                        word=w.word.strip(),
                        start=float(w.start),
                        end=float(w.end),
                        probability=float(w.probability) if hasattr(w, "probability") else None,
                    )
                    segment_words.append(word_obj)
                if segment_words:
                    any_words = True

            clean_text = seg.text.strip()
            if clean_text:
                full_text_parts.append(clean_text)

            segment_record = TranscriptSegment(
                id=f"seg_{len(segments) + 1:04d}",
                start=float(seg.start),
                end=float(seg.end),
                text=clean_text,
                words=segment_words,
                avg_logprob=(float(seg.avg_logprob) if hasattr(seg, "avg_logprob") else None),
                no_speech_prob=(
                    float(seg.no_speech_prob) if hasattr(seg, "no_speech_prob") else None
                ),
            )
            segments.append(segment_record)

            # Update progress based on duration completed
            if progress_callback and duration > 0:
                pct = min(95.0, 15.0 + 80.0 * (seg.end / duration))
                progress_callback(pct, "transcribing")

        word_timestamps_available = any_words and word_timestamps
        timing_granularity = "word" if word_timestamps_available else "segment"

        if progress_callback:
            progress_callback(100.0, "completed")

        return TranscriptionResult(
            language=detected_language,
            language_probability=language_probability,
            duration=duration,
            text=" ".join(full_text_parts),
            segments=segments,
            word_timestamps_available=word_timestamps_available,
            timing_granularity=timing_granularity,
            provider="faster-whisper",
            model=model_size,
            device=device,
            compute_type=compute_type,
            fallback_reason=fallback_reason,
        )

    def get_capabilities(self) -> ProviderCapabilityInfo:
        """Return truthful hardware and feature capabilities for faster-whisper."""
        installed = self.is_available()
        cuda_available = False
        cuda_count = 0
        cuda_name = None

        if installed:
            try:
                import ctranslate2

                cuda_count = ctranslate2.get_cuda_device_count()
                cuda_available = cuda_count > 0
                if cuda_available:
                    cuda_name = f"NVIDIA CUDA ({cuda_count} devices)"
            except Exception as e:
                logger.debug("CTranslate2 CUDA inspection error: %s", e)

        device = "cuda" if (cuda_available and settings.DEFAULT_WHISPER_DEVICE == "cuda") else "cpu"
        compute_type = "float16" if device == "cuda" else settings.DEFAULT_WHISPER_COMPUTE_TYPE

        fallback_reason = None
        if not cuda_available and settings.DEFAULT_WHISPER_DEVICE == "cuda":
            fallback_reason = "No CUDA devices detected by CTranslate2; CPU fallback active"

        return ProviderCapabilityInfo(
            provider="faster-whisper",
            display_name="faster-whisper (Local CPU / NVIDIA CUDA)",
            is_local=True,
            is_cloud=False,
            available=installed,
            active=True,
            device=device,
            cuda_available=cuda_available,
            cuda_device_name=cuda_name,
            cuda_device_count=cuda_count,
            compute_type=compute_type,
            models=list(settings.ALLOWED_WHISPER_MODELS),
            supports_word_timestamps=True,
            supports_speaker_diarization=False,
            requires_api_key=False,
            api_key_configured=True,
            privacy_disclosure=(
                "Local execution only. Audio is never transmitted outside your machine."
            ),
            fallback_reason=fallback_reason,
        )
