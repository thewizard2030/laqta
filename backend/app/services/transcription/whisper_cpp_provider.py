"""whisper.cpp local transcription provider implementation.

Runs local whisper.cpp executable using safe subprocess argument arrays
(never shell=True) and normalizes output to TranscriptionResult.
"""

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

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


def _find_whisper_cpp_binary() -> str | None:
    """Find whisper.cpp CLI binary from configuration or system PATH."""
    if (
        settings.WHISPER_CPP_PATH
        and os.path.isfile(settings.WHISPER_CPP_PATH)
        and os.access(settings.WHISPER_CPP_PATH, os.X_OK)
    ):
        return settings.WHISPER_CPP_PATH
    for cand in ("whisper-cli", "whisper-cpp", "main"):
        path = shutil.which(cand)
        if path:
            return path
    return None


def _find_whisper_cpp_model() -> str | None:
    """Find GGML model file from configuration or default paths."""
    if settings.WHISPER_CPP_MODEL_PATH and os.path.isfile(settings.WHISPER_CPP_MODEL_PATH):
        return settings.WHISPER_CPP_MODEL_PATH
    # Look in whisper models dir
    models_dir = settings.get_whisper_models_dir()
    for cand in models_dir.glob("*.bin"):
        if "ggml" in cand.name.lower():
            return str(cand)
    return None


class WhisperCppProvider(TranscriptionProvider):
    """Local ASR provider wrapping the C++ whisper.cpp implementation."""

    def is_available(self) -> bool:
        """Return True if both whisper.cpp binary and a GGML model are available."""
        return _find_whisper_cpp_binary() is not None and _find_whisper_cpp_model() is not None

    def get_capabilities(self) -> ProviderCapabilityInfo:
        binary = _find_whisper_cpp_binary()
        model = _find_whisper_cpp_model()
        available = binary is not None and model is not None
        fallback = None
        if not binary:
            fallback = "whisper.cpp binary not found in PATH or WHISPER_CPP_PATH"
        elif not model:
            fallback = (
                "whisper.cpp GGML model not found in WHISPER_CPP_MODEL_PATH or models directory"
            )

        return ProviderCapabilityInfo(
            provider="whisper.cpp",
            display_name="whisper.cpp (Local C/C++ Lightweight)",
            is_local=True,
            is_cloud=False,
            available=available,
            active=False,
            device="cpu",
            cuda_available=False,
            cuda_device_name=None,
            cuda_device_count=0,
            compute_type="ggml",
            models=[Path(model).name] if model else [],
            supports_word_timestamps=True,
            supports_speaker_diarization=False,
            requires_api_key=False,
            api_key_configured=True,
            privacy_disclosure=(
                "Local C/C++ execution only. Audio is never transmitted outside your machine."
            ),
            fallback_reason=fallback,
        )

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

        binary = _find_whisper_cpp_binary()
        if not binary:
            raise TranscriptionError(
                "whisper.cpp executable not found. "
                "Configure WHISPER_CPP_PATH or install whisper-cli.",
                error_code="BINARY_NOT_FOUND",
            )

        model_path = _find_whisper_cpp_model()
        if not model_path:
            raise TranscriptionError(
                "whisper.cpp GGML model not found. Set WHISPER_CPP_MODEL_PATH.",
                error_code="MODEL_NOT_FOUND",
            )

        if progress_callback:
            progress_callback(10.0, "transcribing")

        with tempfile.TemporaryDirectory(prefix="qatta_wcpp_") as tmpdir:
            out_prefix = str(Path(tmpdir) / "output")
            cmd = [
                binary,
                "-m",
                model_path,
                "-f",
                str(audio_path),
                "-oj",  # JSON output
                "-of",
                out_prefix,
            ]
            if language:
                cmd.extend(["-l", language])
            else:
                cmd.extend(["-l", "auto"])

            if word_timestamps:
                cmd.append("-ml")
                cmd.append("1")

            logger.info("Executing whisper.cpp command: %s", " ".join(cmd[:4]) + " ...")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _poll_cancel():
                while process.returncode is None:
                    if cancel_event and cancel_event.is_set():
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                        raise JobCancelledError()
                    await asyncio.sleep(0.2)

            cancel_task = asyncio.create_task(_poll_cancel())
            try:
                stdout, stderr = await process.communicate()
            finally:
                cancel_task.cancel()
                try:
                    await cancel_task
                except (asyncio.CancelledError, JobCancelledError):
                    pass

            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()

            if process.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                raise TranscriptionError(
                    f"whisper.cpp exited with code {process.returncode}: {err_msg}",
                    error_code="EXECUTION_FAILED",
                )

            json_path = Path(f"{out_prefix}.json")
            if not json_path.is_file():
                raise TranscriptionError(
                    f"whisper.cpp failed to produce expected JSON output file at {json_path}",
                    error_code="OUTPUT_PARSE_ERROR",
                )

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise TranscriptionError(
                    f"Failed to parse whisper.cpp JSON output: {e}",
                    error_code="OUTPUT_PARSE_ERROR",
                ) from e

            # Parse segments from whisper.cpp JSON
            segments: list[TranscriptSegment] = []
            full_text_parts: list[str] = []
            total_duration = 0.0

            transcription_items = data.get("transcription", [])
            for idx, item in enumerate(transcription_items):
                offsets = item.get("offsets", {})
                from_ms = offsets.get("from", 0)

                to_ms = offsets.get("to", 0)
                start_sec = from_ms / 1000.0 if from_ms is not None else 0.0
                end_sec = to_ms / 1000.0 if to_ms is not None else 0.0
                text = str(item.get("text", "")).strip()

                if text:
                    full_text_parts.append(text)

                words: list[WordTiming] = []
                for tok in item.get("tokens", []):
                    tok_text = tok.get("text", "").strip()
                    tok_offsets = tok.get("offsets", {})
                    t_from = tok_offsets.get("from", 0) / 1000.0
                    t_to = tok_offsets.get("to", 0) / 1000.0
                    p = tok.get("p", 1.0)
                    if tok_text:
                        words.append(
                            WordTiming(word=tok_text, start=t_from, end=t_to, probability=p)
                        )

                segments.append(
                    TranscriptSegment(
                        id=f"seg_{idx + 1:04d}",
                        start=start_sec,
                        end=end_sec,
                        text=text,
                        words=words if words else None,
                    )
                )
                total_duration = max(total_duration, end_sec)

            if progress_callback:
                progress_callback(100.0, "completed")

            return TranscriptionResult(
                language=language or "auto",
                duration=total_duration,
                text=" ".join(full_text_parts),
                segments=segments,
                word_timestamps_available=bool(word_timestamps and segments),
                timing_granularity="word" if word_timestamps else "segment",
                provider="whisper.cpp",
                model=Path(model_path).name,
                device="cpu",
                compute_type="ggml",
            )
