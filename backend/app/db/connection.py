"""SQLite database connection and lifecycle management for Laqta."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger

_SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    safe_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    video_codec TEXT NOT NULL,
    audio_codec TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    media_id TEXT REFERENCES media_assets(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL,
    error_code TEXT,
    error_message TEXT,
    config_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    text TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    word_timestamps_available INTEGER NOT NULL,
    timing_granularity TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    transcript_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    transcript_span_ids_json TEXT NOT NULL,
    title TEXT,
    hook TEXT,
    rationale_json TEXT NOT NULL,
    feature_scores_json TEXT NOT NULL,
    cps REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rendered_clips (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    media_id TEXT NOT NULL,
    output_path TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    video_probe_json TEXT NOT NULL DEFAULT '{}',
    render_config_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_assets_project_id ON media_assets(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_transcripts_media_id ON transcripts(media_id);
CREATE INDEX IF NOT EXISTS idx_candidates_media_id ON candidates(media_id);
CREATE INDEX IF NOT EXISTS idx_rendered_clips_candidate_id ON rendered_clips(candidate_id);
"""


def get_db_path(custom_path: Path | None = None) -> Path:
    """Return database path."""
    return custom_path or settings.get_db_path()


def init_db(db_path: Path | None = None) -> None:
    """Initialize database tables and indexes."""
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initializing SQLite database at: {path}")

    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database connection."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)

    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
