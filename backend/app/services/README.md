# Services

## Overview
Domain services subsystem coordinating media processing, transcription, candidate generation, heuristic scoring, captions, rendering, state bridging, and user settings.

## Interface
- [Media](./media/README.md): Media probe, validation, FFmpeg audio extraction, thumbnails, and URL ingestion
- [Transcription](./transcription/README.md): Speech-to-text transcription engine manager and local/cloud providers
- [Candidates](./candidates/README.md): Deterministic transcript-anchored candidate segmentation and windowing
- [Scoring](./scoring/README.md): Explainable Clip Potential Score calculation and optional LLM reranking
- [Captions](./captions/README.md): Logical-order subtitle generation (SRT, ASS) with BiDi controls and karaoke rules
- [Rendering](./rendering/README.md): FFmpeg vertical 9:16 video rendering, layouts, and probe validation
- [Bridge](./bridge/README.md): Synchronization bridge between QattaManifest pipeline state and SQLite database
- app.services.settings_service: SettingsService - Service managing SQLite-backed BYOK settings and synchronization

## Invariants
- Local-first execution: all core media processing, transcription, scoring, and rendering run entirely on the local host without mandatory cloud APIs
- SettingsService synchronizes persisted SQLite user settings into in-memory settings and os.environ with QATTA_ prefix [settings_service.py:init_and_sync]

## Side Effects
- Executes FFmpeg/FFprobe subprocesses, local AI models, disk I/O, and database updates across child services

## Verification
- Run: `pytest backend/tests`
