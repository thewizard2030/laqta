# S03 Multimodal

## Overview
Per-utterance acoustic feature computation (energy RMS normalization, F0 pitch variance proxy, silence ratio) and video scene-cut timestamp detection.

## Interface
- analyzer.py: compute_utterance_acoustics(pcm: np.ndarray, sr: int, utterance: AtomicUtterance) -> dict[str, float | None]
- analyzer.py: estimate_pitch_variance(pcm_slice: np.ndarray, sr: int) -> float | None
- analyzer.py: run_multimodal_stage(manifest: QattaManifest, settings: QattaSettings | None = None) -> QattaManifest
- analyzer.py: register(orchestrator: PipelineOrchestrator) -> None
- analyzer.py: F0_MIN_HZ: int = 75
- analyzer.py: F0_MAX_HZ: int = 400
- analyzer.py: SCENE_DIFF_THRESHOLD: float = 0.12

## Invariants
- audio_rms_norm is strictly normalized in range [0.0, 1.0] relative to the loudest utterance
- Pitch variance is an excitement/emphasis proxy using librosa.pyin or numpy autocorrelation fallback (75-400 Hz), never claiming full prosodic analysis
- Scene detection uses PySceneDetect ContentDetector when available; otherwise degrades to frame-difference streaming via ffmpeg
- In YouTube captions-first mode where source audio/video is not yet downloaded, acoustics and scene cuts degrade honestly to None/empty without failing

## Side Effects
- Streams grayscale video frames via ffmpeg subprocess when PySceneDetect is unavailable
- Mutates QattaManifest.atomic_utterances (setting audio_rms_norm, pitch_variance, silence_ratio) and QattaManifest.scene_cuts_ms

## Verification
- Run: `pytest tests/`
