# S06 Render

## Overview
Vertical 9:16 video rendering engine producing styled burned-in ASS captions and H.264 MP4 videos using atomic file replacement.

## Interface
- utterances_to_segments(utterances: list[AtomicUtterance]) -> list[TranscriptSegment]
- run_render_stage(manifest: QattaManifest, candidate_id: str | None = None, settings: QattaSettings | None = None, work_dir: Path | None = None, quality: str = 'high', layout: str = 'fill_crop', burn_captions: bool = True, cancel_event: asyncio.Event | None = None) -> QattaManifest
- register(orchestrator: PipelineOrchestrator, candidate_id: str | None = None) -> None

## Invariants
- Subprocess execution uses strict argument arrays without shell=True
- Atomic rendering: writes to temporary file (.part-<pid>) first, validates integrity via ffprobe, and renames atomically with os.replace
- Section timeline rebase: If section_media_path exists (captions-first flow), clip cut points are rebased relative to section_start_ms

## Side Effects
- Generates ASS and SRT subtitle files in captions/
- Spawns ffmpeg subprocess to encode 9:16 vertical MP4 video into renders/
- Spawns ffprobe subprocess to validate rendered video streams
- Mutates candidate.rendered_paths['vertical_9_16']

## Verification
- Run: `pytest tests/`
