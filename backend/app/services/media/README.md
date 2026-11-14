# Media

## Overview
Local media inspection, container signature validation, FFmpeg 16 kHz mono WAV audio extraction, video preview frame generation, and SSRF-hardened URL ingestion.

## Interface
- app.services.media.audio:extract_audio_16k(input_path: Path, output_path: Path, cancel_event: asyncio.Event | None, timeout_sec: float | None, progress_callback: Callable[[float, str], None] | None, ffmpeg_bin_override: str | None, total_duration_ms: int | None) -> Path
- app.services.media.audio:extract_clip_audio_16k(input_path: Path, output_path: Path, start_ms: int, duration_ms: int, cancel_event: asyncio.Event | None, timeout_sec: float | None, progress_callback: Callable[[float, str], None] | None, ffmpeg_bin_override: str | None) -> Path
- app.services.media.audio:clean_intermediate_audio(output_path: Path) -> bool
- app.services.media.audio:build_audio_extraction_command(ffmpeg_bin: str, input_path: Path, output_path: Path, progress: bool = False) -> list[str]
- app.services.media.audio:build_clip_audio_extraction_command(ffmpeg_bin: str, input_path: Path, output_path: Path, start_ms: int, duration_ms: int) -> list[str]
- app.services.media.audio:AudioExtractionError
- app.services.media.audio:JobCancelledError
- app.services.media.probe:detect_capabilities() -> CapabilitiesResponse
- app.services.media.probe:detect_ffmpeg(custom_path: str | None) -> FFmpegCapability
- app.services.media.probe:detect_ffprobe(custom_path: str | None) -> BinaryCapability
- app.services.media.probe:probe_media_file(file_path: Path, custom_ffprobe: str | None) -> MediaProbeResult
- app.services.media.probe:MediaProbeResult
- app.services.media.probe:MediaProbeError
- app.services.media.signature:validate_media_signature(header_bytes: bytes) -> tuple[bool, str, str]
- app.services.media.thumbnails:extract_preview_frame(input_path: Path, output_path: Path, at_ms: int, cancel_event: asyncio.Event | None, timeout_sec: float | None, width: int = 160) -> Path
- app.services.media.thumbnails:get_candidate_thumbnail_path(media_id: str, candidate_id: str) -> Path
- app.services.media.url_ingest:run_url_ingest(url: str, output_dir: Path, cancel_event: asyncio.Event | None, timeout_sec: float | None, progress_callback: Callable[[float, str], None] | None) -> Path
- app.services.media.url_ingest:detect_yt_dlp() -> UrlIngestionCapabilities
- app.services.media.url_ingest:validate_target_url(url: str) -> tuple[bool, str]
- app.services.media.url_ingest:UrlIngestError

## Invariants
- Strict subprocess argument arrays only (never shell=True) for FFmpeg, FFprobe, and yt-dlp [audio.py, probe.py, thumbnails.py, url_ingest.py]
- Magic byte validation (ISO-BMFF, EBML/Matroska/WebM) enforces valid media containers before parsing [signature.py:validate_media_signature]
- Finite timeouts (settings.FFMPEG_TIMEOUT_SECONDS) and cooperative cancellation via asyncio.Event on all subprocesses [audio.py, thumbnails.py, url_ingest.py]
- Subprocess memory bounded: stderr output capped to 64 KB and ffprobe output capped to 512 KB to prevent memory exhaustion [audio.py:_read_bounded_stream, probe.py:probe_media_file]
- Intermediate WAV files deleted only inside temp directories when settings.CLEAN_INTERMEDIATE_WAV is true [audio.py:clean_intermediate_audio]
- URL ingestion ships fail-closed: requires settings.ENABLE_URL_INGESTION=true, user rights confirmation, and rejects loopback/private/link-local IP addresses (SSRF prevention) [url_ingest.py:validate_target_url]

## Side Effects
- Executes local FFmpeg, FFprobe, and yt-dlp CLI binaries via asyncio.create_subprocess_exec [audio.py, probe.py, thumbnails.py, url_ingest.py]
- Creates 16 kHz mono WAV files, JPEG thumbnail images, and downloaded video files on the local filesystem [audio.py:extract_audio_16k, thumbnails.py:extract_preview_frame, url_ingest.py:run_url_ingest]
- Removes partial or aborted output files upon error, timeout, or cancellation [audio.py:_cleanup_partial_file, url_ingest.py:run_url_ingest]

## Verification
- Run: `pytest backend/tests`
