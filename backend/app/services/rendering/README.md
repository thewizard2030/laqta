# Rendering

## Overview
FFmpeg-based vertical 9:16 video rendering service with center-crop and blurred-background layouts, burned-in subtitles, and ffprobe validation.

## Interface
- app.services.rendering.render:QUALITY_PRESETS: dict[str, dict[str, Any]]
- app.services.rendering.render:RenderError
- app.services.rendering.render:RenderEnvironmentReport
- app.services.rendering.render:RenderProbeResult
- app.services.rendering.render:ffmpeg_has_libass_filter(ffmpeg_bin: str) -> bool
- app.services.rendering.render:probe_render_environment(custom_ffmpeg: str | None = None) -> RenderEnvironmentReport
- app.services.rendering.render:compute_center_crop(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]
- app.services.rendering.render:build_render_command(ffmpeg_bin: str, input_path: Path, output_path: Path, *, layout: str, quality: str, src_width: int, src_height: int, has_audio: bool, caption_path: str | None, ...) -> list[str]
- app.services.rendering.render:probe_rendered_output(output_path: Path, expected_duration_ms: int, custom_ffprobe: str | None = None, duration_tolerance_ms: int = 1500) -> RenderProbeResult
- app.services.rendering.render:run_render_process(argv: list[str], output_path: Path, *, cancel_event: asyncio.Event | None = None, timeout_sec: float | None = None, progress_callback: Callable[[float, str], None] | None = None, ffmpeg_bin_override: str | None = None) -> tuple[str, str]
- app.services.rendering.render:write_render_diagnostics(diagnostics_path: Path, config: dict, logs: str) -> None

## Invariants
- Subprocess argument arrays only (never shell=True) for FFmpeg render execution [render.py:build_render_command]
- Standardized vertical export: strictly produces 9:16 H.264 video with AAC audio and +faststart flag [render.py:build_render_command]
- Atomic output validation: renders to a temporary file and verifies output video codec, audio codec, and duration against expected bounds via ffprobe before atomic rename [render.py:probe_rendered_output]
- Cancellation and timeout enforcement: immediately terminates subprocess and removes partial files on cancel_event or timeout [render.py:run_render_process]

## Side Effects
- Spawns local FFmpeg and FFprobe subprocesses via asyncio.create_subprocess_exec [render.py:run_render_process]
- Writes finalized vertical MP4 video files, diagnostic JSON metadata, and render log files to disk [render.py:run_render_process, render.py:write_render_diagnostics]
- Deletes temporary video fragments upon failure or cancellation [render.py:run_render_process]

## Verification
- Run: `pytest backend/tests`
