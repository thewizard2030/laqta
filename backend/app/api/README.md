# Api

## Overview
REST API subsystem grouping HTTP route controllers mounted under the /api namespace.

## Interface
- [Routes](./routes/README.md): REST API route definitions for health, capabilities, projects, media, jobs, transcription, candidates, renders, and settings

## Invariants
- All endpoints require local requests and obey strict CORS rules [routes/__init__.py]
- Request handlers delegate long-running tasks to background job manager [routes/transcription.py, routes/renders.py]

## Side Effects
- Dispatches background jobs, queries SQLite database, and streams media files [routes/]

## Verification
- Run: `pytest backend/tests`
