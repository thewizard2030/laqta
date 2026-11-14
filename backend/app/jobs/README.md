# Jobs

## Overview
Persistent single-worker background job queue handling asynchronous audio extraction, speech transcription, candidate generation, and video rendering.

## Interface
- app.jobs.manager:JobManager
- app.jobs.manager:job_manager: JobManager
- app.jobs.manager:JobManager.start() -> None
- app.jobs.manager:JobManager.stop() -> None
- app.jobs.manager:JobManager.submit_job(project_id: str, job_type: str, media_id: str | None = None, config: dict | None = None) -> JobRecord
- app.jobs.manager:JobManager.cancel_job(job_id: str) -> bool
- app.jobs.manager:JobManager.is_running() -> bool

## Invariants
- Single concurrent worker: executes jobs strictly serially (1 worker) to prevent out-of-memory errors on 8 GB RAM machines [manager.py]
- Crash recovery: on startup, any orphaned jobs left in 'running' status are marked 'failed' with error_code 'SERVER_SHUTDOWN' [manager.py:start]
- Cooperative cancellation: cancel_job sets an asyncio.Event that immediately aborts child subprocesses and deletes intermediate files [manager.py:cancel_job]

## Side Effects
- Spawns and manages asynchronous background worker task [manager.py:start]
- Invokes media extraction, transcription models, caption writers, and FFmpeg rendering [manager.py:_dispatch_job]
- Updates job status, progress, and error logs in SQLite database [manager.py:_update_job_status]

## Verification
- Run: `pytest backend/tests`
