# Database (db)

## Overview
SQLite database connection management, schema initialization, table migrations, and data access repositories.

## Interface
- app.db.connection:get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]
- app.db.connection:init_db(db_path: Path | None = None) -> None
- app.db.models:ProjectRecord, MediaAssetRecord, JobRecord, TranscriptRecord, CandidateRecord, RenderedClipRecord
- app.db.repository:ProjectRepository
- app.db.repository:CandidateRepository
- app.db.repository:RenderRepository

## Invariants
- SQLite WAL mode (PRAGMA journal_mode = WAL) and foreign key enforcement (PRAGMA foreign_keys = ON) enabled on all connections [connection.py:_SCHEMA]
- Cascading deletions: removing a project deletes associated media, transcripts, candidates, jobs, and rendered clip records [connection.py:_SCHEMA]
- Context manager commits on clean exit and rolls back on exception [connection.py:get_connection]

## Side Effects
- Creates SQLite database file and tables at DATA_DIR/app.db [connection.py:init_db]
- Reads and writes rows across tables: projects, media_assets, jobs, transcripts, candidates, rendered_clips, user_settings [repository.py]

## Verification
- Run: `pytest backend/tests`
