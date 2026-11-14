# S06 Reframe Subs

## Overview
Computer vision camera reframing with scene-aware hysteresis deadband and BiDi-compliant Arabic/Arablish ASS subtitle generation.

## Interface
- arabic_ass.py: ArabicBiDiShaper (shape_token, shape_line)
- arabic_ass.py: group_words_into_lines(words: list[WordToken], max_words: int = 4, max_chars: int = 28) -> list[CaptionLine]
- arabic_ass.py: generate_dynamic_ass(lines: list[CaptionLine], config: ASSCaptionConfig | None = None) -> str
- camera_solver.py: CameraSolver(frame_width: int, frame_height: int)
- camera_solver.py: SceneAwareHysteresisSolver
- camera_solver.py: LayoutStateMachine
- camera_solver.py: LayoutMode(StrEnum) (SINGLE_SPEAKER, DUAL_SPLIT, SCREENSHARE_PIP)
- camera_solver.py: ShotSegment(shot_index, start_ms, end_ms, layout, observations, crop_trajectory, metadata)
- camera_solver.py: compute_mouth_aspect_ratio(landmarks: list[tuple[float, float]]) -> float
- camera_solver.py: partition_clip_into_shots(clip_start_ms: int, clip_end_ms: int, scene_cuts_ms: list[int]) -> list[tuple[int, int]]
- __init__.py: run_reframe_subs_stage(manifest: QattaManifest, settings: QattaSettings | None = None, captions_dir: Path | None = None) -> QattaManifest
- __init__.py: register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- BiDi Unicode correctness: Lines prepend RLM (\u200f); all Latin words and numbers are wrapped in First Strong Isolate (\u2068) and Pop Directional Isolate (\u2069)
- Subtitle vertical positioning enforces MarginV=420 to prevent overlap with platform mobile UI elements
- Hysteresis solver maintains 0% pan inside 15% center deadband and snaps instantaneously at scene cuts

## Side Effects
- Writes .ass subtitle files with dynamic word-level karaoke highlight styling into captions/
- Mutates candidate.rendered_paths['ass_captions'] and candidate.evidence_log

## Verification
- Run: `pytest tests/`
