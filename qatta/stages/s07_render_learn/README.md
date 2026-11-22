# S07 Render Learn

> ## Status: library-only — not wired into the pipeline
>
> This stage is implemented and unit-tested, but **nothing runs it**. The
> single source of truth for stage order, `qatta/core/runner.py`, does not
> list it, so neither the backend job manager nor `laqta run` registers it.
> `laqta doctor` will not offer it and no manifest records it.
>
> It stays out on purpose: activating a 657-line renderer changes what users
> get without a way to verify the output, and `AGENTS.md` rule 7 forbids
> shipping future phases early. Wiring it needs a real visual verification
> pass, an opt-in flag, and an honest label — not a silent registration.
>
> The same applies to `s06_reframe_subs`: the camera solver exists, but no
> face detector produces its `FaceDetection` input yet, so it is not
> registered either. Only `s06_render` is.

## Overview
YPP-safe single-pass vertical video rendering, pattern interrupt zoom, hook remix dual cut rendering, and channel analytics feedback learning loop.

## Interface
- FFmpegFilterGraphBuilder
- detect_punch_in_zooms(candidate: ClipCandidate, utterances: list[AtomicUtterance], rms_threshold: float = 0.80, zoom_factor: float = 1.12) -> list[PunchZoomInterval]
- compute_visual_transformation_ratio(candidate: ClipCandidate) -> float
- build_render_command(...) -> list[str]
- build_hook_remix_command(...) -> list[str]
- execute_ffmpeg_render(...) -> Path
- ChannelProfileUpdater(learning_rate: float = 0.15)
- PublishedClipRecord(clip_id, archetype, hook_remix_used, stayed_to_watch_pct, avg_percentage_viewed, metadata)
- ChannelProfile(archetype_weights, hook_remix_preference, total_samples, mean_stayed_to_watch, mean_avg_percentage_viewed, last_updated)
- run_render_learn_stage(manifest: QattaManifest, settings: QattaSettings | None = None, renders_dir: Path | None = None, analytics_file: Path | None = None, execute_ffmpeg: bool = True) -> QattaManifest
- register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- YPP monetization compliance: Checks visual_transformation_ratio; flags warning if below 0.35 threshold
- Single-pass filtergraph compiles all cropping, zooms, overlays, and audio normalization (loudnorm=I=-14:TP=-1.5:LRA=11) in one FFmpeg invocation
- Dual rendering produces both chronological cut and hook-first remix cut when enabled
- Channel profile weights and hook preferences update via channel-normalized Z-scores clamped to [0.05, 0.95]

## Side Effects
- Spawns ffmpeg subprocess to encode final vertical MP4 shorts
- Reads analytics CSV/JSON exports and persists updated channel_profile.json in data_dir
- Mutates candidate.monetization and candidate.rendered_paths

## Verification
- Run: `pytest tests/`
