# Core

## Overview
Central configuration, environment variable management via pydantic-settings, and structured console logging.

## Interface
- app.core.config:Settings
- app.core.config:settings: Settings
- app.core.logging:setup_logging(level: int = logging.INFO) -> logging.Logger
- app.core.logging:logger: logging.Logger

## Invariants
- Local binding: default HOST is 127.0.0.1; PORT is 8000 [config.py:Settings]
- Strict CORS: wildcard '*' origins are disallowed; only explicit local origins are accepted [config.py:Settings]
- Privacy defaults: ALLOW_CLOUD_APIS is false and ENABLE_URL_INGESTION is false by default [config.py:Settings]
- Storage location: DATA_DIR resolves to ~/.local/share/qatta on Linux by default [config.py:Settings]

## Side Effects
- Reads environment variables and .env configuration files [config.py]
- Ensures local data directory hierarchy exists on the filesystem [config.py:get_effective_data_dir]
- Initializes root console stream logger on sys.stdout [logging.py]

## Verification
- Run: `pytest backend/tests`
