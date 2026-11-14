# S01 Ingest

## Overview
Media probing, metadata extraction (duration, resolution, fps), and 16 kHz mono PCM WAV extraction, with fail-closed URL ingestion via yt-dlp.

## Interface
- probe_media(media_path: Path, settings: QattaSettings) -> ProbedMedia
- extract_audio_16k(source: Path, destination: Path, settings: QattaSettings) -> Path
- is_url(source: str) -> bool
- ProbedMedia(duration_sec: float, width: int | None, height: int | None, fps: float | None)
- run_ingest_stage(manifest: QattaManifest, settings: QattaSettings | None = None, work_dir: str | Path | None = None) -> QattaManifest
- register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- URL ingestion is fail-closed by default (QATTA_ENABLE_URL_INGESTION=true required); raises PipelineError if disabled
- Subprocess executions of ffprobe and ffmpeg strictly use argument arrays without shell=True, bounded timeouts, and size-limited stderr capture
- Extracted audio output is strictly 16 kHz mono s16le PCM WAV (audio_16k.wav)
- YouTube captions-first mode (youtube_subs_first) skips media downloading and full audio extraction, fetching metadata and platform VTT captions only
- Media duration must be positive (> 0); playlists are rejected rather than truncated

## Side Effects
- Executes ffprobe subprocess to inspect duration, video resolution, and frame rate
- Executes ffmpeg subprocess to extract 16 kHz mono PCM audio to audio_16k.wav
- If URL ingestion is enabled and requested, downloads media or fetches VTT subtitles using yt-dlp into the project work directory
- Mutates QattaManifest fields (duration_sec, video_width, video_height, fps, audio_16k_path, subtitle_path, source_url)

## Verification
- Run: `pytest tests/`
