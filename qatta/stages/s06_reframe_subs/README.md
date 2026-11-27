# S06 Reframe Subs

## Overview
Computer vision camera reframing with scene-aware hysteresis deadband and BiDi-compliant Arabic/Arablish ASS subtitle generation.

## Interface
- detector.py: FaceDetector (Protocol: name, detect(frame_bgr, timestamp_ms) -> FrameObservation)
- detector.py: OpenCVHaarDetector(downscale_width=320, max_faces=4, min_face_ratio=0.05, min_face_px=24) — frontal faces only
- detector.py: NullDetector — reports no faces; used when the feature is disabled
- detector.py: detector_status() -> tuple[bool, str | None] — never raises
- detector.py: build_detector(name: str = 'opencv_haar') -> FaceDetector
- detector.py: DetectorUnavailableError(reason)
- detector.py: observe_frames(detector, frames, *, reader=None) -> list[FrameObservation] — decodes sampled JPEGs; unreadable frames are skipped, so len(result) may be < len(frames)
- frame_sampler.py: build_sample_command(*, ffmpeg_bin, input_path, out_dir, start_ms, end_ms, fps=5.0, max_frames=600) -> list[str]
- frame_sampler.py: sample_frames(*, ffmpeg_bin, input_path, out_dir, start_ms, end_ms, fps=5.0, max_frames=600, timeout_seconds=120.0, cancel_event=None) -> list[SampledFrame]
- frame_sampler.py: temporary_sample_dir(parent: Path) — context manager, mode 0700, removed on exit
- frame_sampler.py: FrameSamplingError, SamplingCancelledError, SampledFrame(path, timestamp_ms)
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
- Frame sampling is one bounded FFmpeg argument array: no shell, `-ss` before `-i` (input seek), `-t` bounded, `-frames:v` capped, explicit timeout, bounded stderr
- Detection is local only: OpenCV's bundled Haar cascade (ships inside `opencv-python`, Apache-2.0). No weights are downloaded and nothing leaves the machine
- Haar detects frontal faces only, returns no landmarks, and therefore reports `mar=0.0` and `is_speaking=False` always. `face_id` is a per-frame index, never a tracked identity — no speaker identification is performed or implied
- Face-guided framing is opt-in (`QATTA_FACE_GUIDED_FRAMING`, default false). With it off, no frames are sampled at all — the stage does not do expensive work because it can
- Degradation is recorded, never silent: when the feature is off, the detector is unavailable, ffmpeg is missing or sampling fails, `candidate.framing_meta.degradation_reason` says why and the trajectory falls back to a centred crop
- `framing_meta.enabled` is true only when detection actually ran; every count in it is measured, and `frames_analysed` may be smaller than `frames_sampled` because unreadable frames are skipped
- Timestamps are always on the SOURCE timeline. When sampling a downloaded section, the request is rebased into the section file and the results are rebased back — otherwise observations land in the wrong shot
- `crop_trajectory` holds the solved trajectory, never the raw per-frame observations: the manifest is persisted state and must not grow with sampling density
- Writing v2 fields sets `schema_version = 2`, so an older build reports "newer than this build understands" instead of failing strict validation on an unknown field

## Side Effects
- Writes .ass subtitle files with dynamic word-level karaoke highlight styling into `captions/reframe/` — deliberately namespaced, because the render stage owns `captions/{clip_id}.ass` and sharing the name meant the later stage silently replaced the other's subtitles
- Mutates candidate.rendered_paths['ass_captions'], candidate.crop_trajectory, candidate.framing_meta and candidate.evidence_log
- Creates and removes a private (0700) temporary frame directory next to the captions directory

## Verification
- Run: `pytest tests/`
