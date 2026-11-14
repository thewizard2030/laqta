# Laqta Backend

## Overview
The Laqta backend subsystem providing the local FastAPI application, REST endpoints, SQLite persistence, and background job queue.

## Interface
- [App](./app/README.md): FastAPI application core, API routes, database repositories, domain services, and schemas
- [Tools](./tools/README.md): Developer tooling and local maintenance scripts
- pyproject.toml: Python project configuration and dependencies
- requirements*.txt: Runtime, development, and ASR dependency specifications
- uvicorn app.main:app --host 127.0.0.1 --port 8000: Backend server execution command

## Invariants
- Local-first guarantee: binds strictly to 127.0.0.1; zero required cloud API keys; no user telemetry [README.md, app/core/config.py]
- Fail-closed cloud policy: all hosted cloud APIs (Groq, OpenRouter, AssemblyAI) and URL ingestion stay disabled until explicit operator opt-in [README.md, app/core/config.py]
- Subprocess safety: explicit argument arrays only, no shell=True, finite deadlines, and bounded memory limits [README.md, AGENTS.md]

## Side Effects
- Runs FastAPI HTTP web server on local loopback interface
- Creates local SQLite database and file hierarchy under DATA_DIR (~/.local/share/qatta)
- Spawns local FFmpeg and FFprobe worker subprocesses

## Verification
- Run: `pytest backend/tests`
