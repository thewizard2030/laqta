# S05B Section Fetch

## Overview
Selective download stage for YouTube captions-first pipelines that fetches keyframe-aligned video ranges and extracts audio only for winning ranked clips.

## Interface
- run_section_fetch_stage(manifest: QattaManifest, settings: QattaSettings | None = None, work_dir: str | Path | None = None) -> QattaManifest
- register(orchestrator: PipelineOrchestrator) -> None

## Invariants
- No-op for local-file sources; only executes when transcript_source == 'youtube_subs_first'
- Slices only the exact winning clip time ranges plus fine_padding_ms with force_keyframes_at_cuts=True
- Fail-closed gate: Requires QATTA_ENABLE_URL_INGESTION=true; raises PipelineError if url ingestion is disabled
- Transcodes fetched section video to 16 kHz mono s16le PCM WAV for Pass 2 word alignment

## Side Effects
- Downloads video slices via yt-dlp into sections/ directory
- Spawns ffmpeg subprocess to extract 16 kHz PCM audio from downloaded sections
- Mutates winning candidates: sets section_media_path, section_audio_16k_path, and section_start_ms

## Verification
- Run: `pytest tests/`
