# Qatta Core Engine

## Overview
Root package for Laqta: local-first, Arabic-first long-video-to-vertical-Shorts engine providing CLI commands, manifest schema, and modular processing stages.

## Interface
- __init__.py: __version__ = '0.1.3'
- cli.py: app (laqta CLI entrypoint: --version, doctor, version, serve, studio, models)
- [Core](./core/README.md): Core schema models, settings, and atomic pipeline orchestrator
- [Stages](./stages/README.md): Modular video and transcript processing pipeline stages

## Invariants
- Local-first architecture: Binds to 127.0.0.1 by default; zero telemetry or mandatory cloud uploads
- Single source of truth: qatta.__version__ is the authoritative version across pyproject.toml, backend, and frontend
- Fail-closed gates: URL ingestion and cloud APIs require explicit operator opt-in
- Subprocess safety: Media commands invoke ffmpeg/ffprobe via strict argv arrays, bounded timeouts, and size-limited stderr capture

## Side Effects
- Inspects local system binaries (ffmpeg, ffprobe, yt-dlp) and hardware resources
- Binds local HTTP ports and launches local subprocess servers

## Verification
- Run: `pytest tests/`
