# Backend Application (app)

## Overview
The complete FastAPI backend application package for Laqta, uniting REST routes, background jobs, database repositories, domain services, schemas, and core settings.

## Interface
- app.main:app: FastAPI application instance with CORS middleware, lifespan events, and static studio serving
- [API](./api/README.md): REST API routing layer
- [Core](./core/README.md): Application settings and logging configuration
- [DB](./db/README.md): SQLite connection and repository layer
- [Jobs](./jobs/README.md): Single-worker background job manager
- [Providers](./providers/README.md): Pluggable LLM provider adapters
- [Schemas](./schemas/README.md): Pydantic request and response schemas
- [Services](./services/README.md): Media, transcription, candidate, scoring, caption, and rendering domain services

## Invariants
- Binds strictly to 127.0.0.1 by default with no external telemetry [main.py]
- Lifespan event handler initializes database, synchronizes settings, and manages background worker lifecycle [main.py:lifespan]
- Studio UI is served statically in release mode when frontend/dist is present [main.py:studio_ui]

## Side Effects
- Runs Uvicorn HTTP server on 127.0.0.1:8000 [main.py]
- Reads/writes local SQLite database and project files in DATA_DIR [main.py, db/, services/]

## Verification
- Run: `pytest backend/tests`
