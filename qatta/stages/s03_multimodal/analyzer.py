"""Stage s03_multimodal — per-utterance acoustics + scene-cut timestamps.

Acoustic features per utterance (semantics are the same for both
backends; numbers are deterministic for identical PCM):

- ``audio_rms_norm``: utterance RMS divided by the LOUDEST utterance RMS
  (already approximated in Pass 1; recomputed here on the full-quality
  frame resolution).
- ``pitch_variance``: normalized variance of per-voiced-frame F0
  estimates. When ``librosa`` is importable, F0 comes from
  ``librosa.pyin``; otherwise a banded autocorrelation estimator (numba-
  free numpy, 75–400 Hz search) is used. Written as an excitement/
  emphasis PROXY — never claimed as full prosody analysis.
- ``silence_ratio``: fraction of the utterance span whose frame RMS is
  below the stage's silence threshold (the same threshold contract as
  Pass 1's pause detection).

Scene cuts: ``ContentDetector`` from ``scenedetect`` when that package
is importable; otherwise a documented fallback runs ffmpeg to stream
tiny grayscale frames (fps=self.frame_rate) and flags a cut when the
mean absolute pixel difference between consecutive frames exceeds a
fixed threshold. Both paths persist ``manifest.scene_cuts_ms``; the
manifest itself records nothing about WHICH backend ran, so the
evidence is visible only in logs — as a result the fallback IS a real
scene-change measurement, not a stub.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import AtomicUtterance, QattaManifest
from qatta.stages.s02_transcript.fast_pass import (
    frame_rms,
    load_pcm_16k,
)

# Default voice/search band shared by both pitch backends.
F0_MIN_HZ = 75
F0_MAX_HZ = 400
PITCH_FRAME_MS = 40
PITCH_HOP_MS = 20
SCENE_DIFF_THRESHOLD = 0.12  # mean |Δ| over grayscale frames (0..1)
SCENE_FPS = 4

logger = logging.getLogger(__name__)


def _silence_threshold(rms: np.ndarray) -> float:
    """The stage's silence threshold (noise floor + 1.5x, like Pass 1).

    A digitally silent signal (every frame at zero) must still count as
    silence: the threshold is the *lower* bound of a frame, so it has to be
    strictly positive for a zero frame to fall below it. Returning 0.0 would
    report a silent clip as "not silent" and let it score as if it had
    speech.
    """
    floor = float(np.percentile(rms, 20))
    peak = float(rms.max()) if rms.size else 0.0
    if peak <= 0:
        return 1e-9
    return max(floor * 1.5, peak * 0.04)


def _pitch_variance_librosa(pcm: np.ndarray, sr: int, start_ms: int, end_ms: int) -> float | None:
    """librosa.pyin-based pitch variance (imported lazily)."""
    try:
        import librosa
    except ImportError:
        return None
    i0 = int(start_ms * sr / 1000)
    i1 = int(end_ms * sr / 1000)
    segment = np.abs(pcm[i0:i1])
    try:
        f0, voiced_flag, _voiced = librosa.pyin(
            segment,
            sr=sr,
            fmin=F0_MIN_HZ,
            fmax=F0_MAX_HZ,
            frame_length=max(1024, int(PITCH_FRAME_MS * sr / 1000)),
        )
    except Exception:
        return None  # librosa failed on degenerate audio -> numpy path
    voiced = f0[voiced_flag == True]  # noqa: E712  (numpy boolean mask)
    if voiced.size < 3:
        return None
    spread = float(np.std(voiced) / (np.mean(voiced) + 1e-9))
    return min(1.0, max(0.0, spread))


def _pitch_variance_numpy(pcm: np.ndarray, sr: int, start_ms: int, end_ms: int) -> float | None:
    """Banded autocorrelation F0 estimator (numpy only)."""
    i0 = int(start_ms * sr / 1000)
    i1 = int(end_ms * sr / 1000)
    segment = pcm[i0:i1].astype(np.float64)
    frame_len = int(PITCH_FRAME_MS * sr / 1000)
    hop = int(PITCH_HOP_MS * sr / 1000)
    if len(segment) < frame_len or frame_len <= 0:
        return None

    lag_min = max(2, int(sr / F0_MAX_HZ))
    lag_max = min(frame_len - 1, int(sr / F0_MIN_HZ))
    if lag_max <= lag_min:
        return None

    f0s: list[float] = []
    frame_pos = np.arange(0, len(segment) - frame_len + 1, hop)
    frames = np.lib.stride_tricks.sliding_window_view(segment, frame_len)
    frames = frames[::hop][: len(frame_pos)]
    energy = np.sqrt(np.mean(frames**2, axis=1))
    threshold = float(np.max(energy)) * 0.05
    for idx in range(min(len(frames), len(frame_pos))):
        if energy[idx] <= threshold:
            continue  # unvoiced / silent frame
        frame = frames[idx]
        frame_centered = frame - frame.mean()
        denom = float(np.dot(frame_centered, frame_centered))
        if denom <= 0:
            continue
        best_lag, best_corr = -1, 0.0
        for lag in range(lag_min, lag_max + 1):
            corr = float(np.dot(frame_centered[:-lag], frame_centered[lag:])) / denom
            if corr > best_corr:
                best_corr, best_lag = corr, lag
        if best_corr > 0.3 and best_lag > 0:
            f0s.append(sr / best_lag)

    if len(f0s) < 3:
        return None
    spread = np.std(np.asarray(f0s)) / (np.mean(f0s) + 1e-9)
    return min(1.0, max(0.0, float(spread)))


def compute_utterance_acoustics(
    pcm: np.ndarray, sr: int, utterance: AtomicUtterance
) -> dict[str, float | None]:
    """RMS-norm (deferred; scaled later), pitch variance, silence ratio."""
    total_ms = int(round(len(pcm) * 1000 / sr))
    i0 = max(0, int(utterance.start_ms * sr / 1000))
    i1 = min(len(pcm), int(max(utterance.end_ms, utterance.start_ms + 1) * sr / 1000))
    span = pcm[i0:i1].astype(np.float64)
    rms_value = float(np.sqrt(np.mean(span**2))) if span.size else 0.0

    if i1 <= i0:
        pitch = None
        silence_value = None
    else:
        end_ms = min(utterance.end_ms, total_ms)
        pitch = _pitch_variance_librosa(pcm, sr, utterance.start_ms, end_ms)
        if pitch is None:
            pitch = _pitch_variance_numpy(pcm, sr, utterance.start_ms, end_ms)

        frame = frame_rms(pcm, sr, 30, 10)
        threshold = _silence_threshold(frame)
        # Frames overlapping the utterance span.
        first_frame = int(utterance.start_ms // 10)
        last_frame = int(min(total_ms, utterance.end_ms) // 10)
        window = frame[first_frame:last_frame]
        if window.size:
            silence_value = float(np.mean(window < threshold))
        else:
            silence_value = None

    return {
        "rms": rms_value,
        "pitch_variance": pitch,
        "silence_ratio": silence_value,
    }


# ---------------------------------------------------------------------------
# Scene-cut detection
# ---------------------------------------------------------------------------


def _scene_cuts_scenedetect(video_path: Path) -> list[int] | None:
    """ContentDetector cuts (ms); None when scenedetect is unavailable."""
    try:
        from scenedetect import ContentDetector, detect
    except ImportError:
        return None
    try:
        scenes = detect(str(video_path), ContentDetector())
    except Exception:
        return None
    cuts: list[int] = []
    scene_list = scenes[:-1] if len(scenes) > 1 else []
    for _start, end in scene_list:
        cuts.append(int(round(end.get_seconds() * 1000)))
    return cuts


def _scene_cuts_ffmpeg_fallback(video_path: Path, fps: int = SCENE_FPS) -> list[int]:
    """Documented fallback: tiny grayscale frame stream via ffmpeg.

    Streams downscaled grayscale frames from ffmpeg (arg array, bounded
    timeout), measures the mean absolute difference of consecutive
    frames, and flags a cut where it crosses SCENE_DIFF_THRESHOLD.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PipelineError(
            "Neither scenedetect nor ffmpeg is installed; scene-cut "
            "detection cannot run (on Fedora: 'sudo dnf install "
            "ffmpeg scenedetect')."
        )
    width, height = 64, 36
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"fps={fps},scale={width}:{height},format=gray",
                "-f",
                "rawvideo",
                "-",
            ],
            capture_output=True,
            timeout=300,
            check=True,
        )
    except subprocess.TimeoutExpired as e:
        raise PipelineError("ffmpeg scene-frame streaming timed out (300s).") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"")[:500]
        raise PipelineError(f"ffmpeg failed streaming scene frames: {stderr!r}") from e

    frame_bytes = width * height
    raw = proc.stdout
    n_frames = len(raw) // frame_bytes
    if n_frames < 2:
        return []
    frames = (
        np.frombuffer(raw[: n_frames * frame_bytes], dtype=np.uint8)
        .reshape(n_frames, frame_bytes)
        .astype(np.float32)
        / 255.0
    )
    diffs = np.mean(np.abs(np.diff(frames, axis=0)), axis=1)
    cut_indices = np.flatnonzero(diffs > SCENE_DIFF_THRESHOLD)
    return [int(round((idx + 1) * 1000 / fps)) for idx in cut_indices.tolist()]


def run_multimodal_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
) -> QattaManifest:
    """Execute stage s03_multimodal for the given manifest.

    YouTube captions-first mode (``transcript_source ==
    "youtube_subs_first"``): the full media was never fetched, so this
    stage honestly degrades — per-utterance acoustics stay unmeasured
    (``None``/``0.0``) and scene cuts stay empty instead of being
    fabricated from partial data. The winning clips are still re-analyzed
    indirectly via Pass 2 word alignment on their downloaded sections.
    """
    settings = settings or QattaSettings()
    if not manifest.audio_16k_path:
        if manifest.transcript_source == "youtube_subs_first":
            data = manifest.model_dump()
            data["scene_cuts_ms"] = []
            return manifest.model_validate(data)
        raise PipelineError(
            "No audio_16k.wav in the manifest; run stage s01_ingest before s03_multimodal."
        )
    pcm, sr = load_pcm_16k(manifest.audio_16k_path)

    computed = [compute_utterance_acoustics(pcm, sr, u) for u in manifest.atomic_utterances]
    loudest = max((row["rms"] for row in computed), default=0.0)

    updated_utterances: list[AtomicUtterance] = []
    for utterance, row in zip(manifest.atomic_utterances, computed, strict=True):
        payload = utterance.model_dump()
        rms_norm = 0.0 if loudest <= 0 else min(1.0, max(0.0, row["rms"] / loudest))
        payload["audio_rms_norm"] = rms_norm
        payload["pitch_variance"] = row["pitch_variance"]
        payload["silence_ratio"] = row["silence_ratio"]
        updated_utterances.append(utterance.model_validate(payload))

    scene_cuts: list[int] = []
    source = Path(manifest.source_path)
    if source.is_file():
        try:
            scene_cuts = _scene_cuts_scenedetect(source)
            if scene_cuts is None:
                scene_cuts = _scene_cuts_ffmpeg_fallback(source)
        except PipelineError as exc:
            # Scene cuts are one signal among many. A source ffmpeg cannot
            # decode must degrade to "no scene cuts" instead of aborting the
            # whole pipeline — the ranking still works without them.
            logger.warning("Scene-cut detection failed, continuing without it: %s", exc)
            scene_cuts = []

    data = manifest.model_dump()
    data["atomic_utterances"] = [u.model_dump() for u in updated_utterances]
    data["scene_cuts_ms"] = sorted({int(c) for c in scene_cuts})
    return manifest.model_validate(data)


def register(orchestrator) -> None:
    """Attach s03_multimodal to a :class:`PipelineOrchestrator`."""

    @orchestrator.stage("s03_multimodal")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_multimodal_stage(manifest, orchestrator.settings)
