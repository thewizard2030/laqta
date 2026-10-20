"""Repository layer for database operations."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.db.connection import get_connection
from app.db.models import (
    CandidateRecord,
    JobRecord,
    MediaAssetRecord,
    ProjectRecord,
    RenderedClipRecord,
    TranscriptRecord,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectRepository:
    """Repository for managing Project and MediaAsset entities."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path

    def create_project(self, name: str) -> ProjectRecord:
        """Create a new project record."""
        project_id = f"proj_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO projects (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, name, now, now),
            )
        return ProjectRecord(id=project_id, name=name, created_at=now, updated_at=now)

    def list_projects(self) -> list[ProjectRecord]:
        """List all projects sorted by creation date descending."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, name, created_at, updated_at FROM projects ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()
            return [
                ProjectRecord(
                    id=row["id"],
                    name=row["name"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def get_project(self, project_id: str) -> ProjectRecord | None:
        """Retrieve a project by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, name, created_at, updated_at FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ProjectRecord(
                id=row["id"],
                name=row["name"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def update_project(self, project_id: str, name: str) -> ProjectRecord | None:
        """Update a project's name and updated_at timestamp."""
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name, now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and cascading child entities."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cursor.rowcount > 0

    def create_media_asset(
        self,
        project_id: str,
        safe_path: str,
        original_name: str,
        size_bytes: int,
        duration_ms: int,
        width: int,
        height: int,
        video_codec: str,
        audio_codec: str,
        status: str = "ready",
    ) -> MediaAssetRecord:
        """Create a new media asset for a project."""
        media_id = f"med_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO media_assets (
                    id, project_id, safe_path, original_name, size_bytes,
                    duration_ms, width, height, video_codec, audio_codec, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    project_id,
                    safe_path,
                    original_name,
                    size_bytes,
                    duration_ms,
                    width,
                    height,
                    video_codec,
                    audio_codec,
                    status,
                    now,
                ),
            )
            # Update project updated_at timestamp
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        return MediaAssetRecord(
            id=media_id,
            project_id=project_id,
            safe_path=safe_path,
            original_name=original_name,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            width=width,
            height=height,
            video_codec=video_codec,
            audio_codec=audio_codec,
            status=status,
            created_at=now,
        )

    def get_media_asset(self, media_id: str) -> MediaAssetRecord | None:
        """Retrieve a media asset by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, safe_path, original_name, size_bytes,
                       duration_ms, width, height, video_codec, audio_codec, status, created_at
                FROM media_assets WHERE id = ?
                """,
                (media_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return MediaAssetRecord(
                id=row["id"],
                project_id=row["project_id"],
                safe_path=row["safe_path"],
                original_name=row["original_name"],
                size_bytes=row["size_bytes"],
                duration_ms=row["duration_ms"],
                width=row["width"],
                height=row["height"],
                video_codec=row["video_codec"],
                audio_codec=row["audio_codec"],
                status=row["status"],
                created_at=row["created_at"],
            )

    def list_project_media(self, project_id: str) -> list[MediaAssetRecord]:
        """List all media assets for a given project."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, safe_path, original_name, size_bytes,
                       duration_ms, width, height, video_codec, audio_codec, status, created_at
                FROM media_assets WHERE project_id = ? ORDER BY created_at DESC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            return [
                MediaAssetRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    safe_path=row["safe_path"],
                    original_name=row["original_name"],
                    size_bytes=row["size_bytes"],
                    duration_ms=row["duration_ms"],
                    width=row["width"],
                    height=row["height"],
                    video_codec=row["video_codec"],
                    audio_codec=row["audio_codec"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def create_job(
        self,
        project_id: str,
        job_type: str,
        media_id: str | None = None,
        config_json: str | None = None,
    ) -> JobRecord:
        """Create a new Job record."""
        job_id = f"job_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, project_id, media_id, type, status, stage, progress,
                    error_code, error_message, config_json, created_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    media_id,
                    job_type,
                    "queued",
                    "initialized",
                    0.0,
                    None,
                    None,
                    config_json,
                    now,
                    None,
                    None,
                ),
            )
        return JobRecord(
            id=job_id,
            project_id=project_id,
            media_id=media_id,
            type=job_type,
            status="queued",
            stage="initialized",
            progress=0.0,
            error_code=None,
            error_message=None,
            config_json=config_json,
            created_at=now,
            started_at=None,
            finished_at=None,
        )

    def get_job(self, job_id: str) -> JobRecord | None:
        """Retrieve a job by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, media_id, type, status, stage, progress,
                       error_code, error_message, config_json, created_at, started_at, finished_at
                FROM jobs WHERE id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return JobRecord(
                id=row["id"],
                project_id=row["project_id"],
                media_id=row["media_id"],
                type=row["type"],
                status=row["status"],
                stage=row["stage"],
                progress=row["progress"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                config_json=row["config_json"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )

    def list_project_jobs(self, project_id: str) -> list[JobRecord]:
        """List all jobs associated with a project."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, media_id, type, status, stage, progress,
                       error_code, error_message, config_json, created_at, started_at, finished_at
                FROM jobs WHERE project_id = ? ORDER BY created_at DESC
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
            return [
                JobRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    media_id=row["media_id"],
                    type=row["type"],
                    status=row["status"],
                    stage=row["stage"],
                    progress=row["progress"],
                    error_code=row["error_code"],
                    error_message=row["error_message"],
                    config_json=row["config_json"],
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                )
                for row in rows
            ]

    def clear_project_jobs(self, project_id: str, keep_active: bool = True) -> int:
        """Delete historical (succeeded, failed, cancelled) jobs for a project.

        If keep_active is True, queued or running jobs are retained.
        """
        with get_connection(self.db_path) as conn:
            if keep_active:
                cursor = conn.execute(
                    """
                    DELETE FROM jobs
                    WHERE project_id = ? AND status IN ('succeeded', 'failed', 'cancelled')
                    """,
                    (project_id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM jobs WHERE project_id = ?",
                    (project_id,),
                )
            return cursor.rowcount

    def update_job(
        self,
        job_id: str,
        status: str | None = None,
        stage: str | None = None,
        progress: float | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        config_json: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> JobRecord | None:
        """Update job fields dynamically."""
        updates: list[str] = []
        params: list[object] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if stage is not None:
            updates.append("stage = ?")
            params.append(stage)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if error_code is not None:
            updates.append("error_code = ?")
            params.append(error_code)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if config_json is not None:
            updates.append("config_json = ?")
            params.append(config_json)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)

        if not updates:
            return self.get_job(job_id)

        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
        with get_connection(self.db_path) as conn:
            conn.execute(query, params)

        return self.get_job(job_id)

    def recover_interrupted_jobs(self) -> int:
        """Mark interrupted running jobs as failed/retryable upon server restart."""
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    stage = 'interrupted',
                    error_code = 'INTERRUPTED_ON_RESTART',
                    error_message = (
                        'Job was interrupted by server shutdown/restart. It can be safely retried.'
                    ),
                    finished_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            return cursor.rowcount

    def list_queued_jobs(self) -> list[JobRecord]:
        """List all queued jobs ordered by creation time ascending."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, project_id, media_id, type, status, stage, progress,
                       error_code, error_message, config_json, created_at, started_at, finished_at
                FROM jobs WHERE status = 'queued' ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            return [
                JobRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    media_id=row["media_id"],
                    type=row["type"],
                    status=row["status"],
                    stage=row["stage"],
                    progress=row["progress"],
                    error_code=row["error_code"],
                    error_message=row["error_message"],
                    config_json=row["config_json"],
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                )
                for row in rows
            ]

    def create_transcript(
        self,
        media_id: str,
        language: str,
        provider: str,
        model: str,
        text: str,
        segments_json: str,
        word_timestamps_available: bool,
        timing_granularity: str,
        status: str = "completed",
    ) -> TranscriptRecord:
        """Create and persist a new Transcript record.

        Preserves existing transcripts to support re-transcribing with different models.
        """
        transcript_id = f"tr_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO transcripts (
                    id, media_id, language, provider, model, status,
                    text, segments_json, word_timestamps_available, timing_granularity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transcript_id,
                    media_id,
                    language,
                    provider,
                    model,
                    status,
                    text,
                    segments_json,
                    1 if word_timestamps_available else 0,
                    timing_granularity,
                    now,
                ),
            )
        return TranscriptRecord(
            id=transcript_id,
            media_id=media_id,
            language=language,
            provider=provider,
            model=model,
            status=status,
            text=text,
            segments_json=segments_json,
            word_timestamps_available=word_timestamps_available,
            timing_granularity=timing_granularity,
            created_at=now,
        )

    def get_transcript(self, transcript_id: str) -> TranscriptRecord | None:
        """Retrieve a specific transcript by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, language, provider, model, status,
                       text, segments_json, word_timestamps_available,
                       timing_granularity, created_at
                FROM transcripts WHERE id = ?
                """,
                (transcript_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return TranscriptRecord(
                id=row["id"],
                media_id=row["media_id"],
                language=row["language"],
                provider=row["provider"],
                model=row["model"],
                status=row["status"],
                text=row["text"],
                segments_json=row["segments_json"],
                word_timestamps_available=bool(row["word_timestamps_available"]),
                timing_granularity=row["timing_granularity"],
                created_at=row["created_at"],
            )

    def update_transcript(
        self,
        transcript_id: str,
        text: str,
        segments_json: str,
        word_timestamps_available: bool,
        timing_granularity: str,
    ) -> TranscriptRecord | None:
        """Update an existing transcript record."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE transcripts
                SET text = ?, segments_json = ?,
                    word_timestamps_available = ?, timing_granularity = ?
                WHERE id = ?
                """,
                (
                    text,
                    segments_json,
                    1 if word_timestamps_available else 0,
                    timing_granularity,
                    transcript_id,
                ),
            )
        return self.get_transcript(transcript_id)

    def list_media_transcripts(self, media_id: str) -> list[TranscriptRecord]:
        """List all transcripts associated with a media asset ordered by newest first."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, language, provider, model, status,
                       text, segments_json, word_timestamps_available,
                       timing_granularity, created_at
                FROM transcripts WHERE media_id = ? ORDER BY created_at DESC
                """,
                (media_id,),
            )
            rows = cursor.fetchall()
            return [
                TranscriptRecord(
                    id=row["id"],
                    media_id=row["media_id"],
                    language=row["language"],
                    provider=row["provider"],
                    model=row["model"],
                    status=row["status"],
                    text=row["text"],
                    segments_json=row["segments_json"],
                    word_timestamps_available=bool(row["word_timestamps_available"]),
                    timing_granularity=row["timing_granularity"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def get_latest_media_transcript(self, media_id: str) -> TranscriptRecord | None:
        """Retrieve the latest completed transcript for a media asset."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, media_id, language, provider, model, status,
                       text, segments_json, word_timestamps_available,
                       timing_granularity, created_at
                FROM transcripts WHERE media_id = ? AND status = 'completed'
                ORDER BY created_at DESC LIMIT 1
                """,
                (media_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return TranscriptRecord(
                id=row["id"],
                media_id=row["media_id"],
                language=row["language"],
                provider=row["provider"],
                model=row["model"],
                status=row["status"],
                text=row["text"],
                segments_json=row["segments_json"],
                word_timestamps_available=bool(row["word_timestamps_available"]),
                timing_granularity=row["timing_granularity"],
                created_at=row["created_at"],
            )


class CandidateRepository:
    """Repository for ClipCandidate persistence (PRD §5 FR-04, §7).

    Candidate IDs are derived deterministically from (transcript_id, start_ms,
    end_ms) so identical generation runs are idempotent and reproducible.
    """

    _COLUMNS = (
        "id, media_id, transcript_id, start_ms, end_ms, transcript_span_ids_json, "
        "title, hook, rationale_json, feature_scores_json, cps, status, created_at"
    )

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path

    def _row_to_record(self, row: sqlite3.Row) -> CandidateRecord:
        return CandidateRecord(
            id=row["id"],
            media_id=row["media_id"],
            transcript_id=row["transcript_id"],
            start_ms=row["start_ms"],
            end_ms=row["end_ms"],
            transcript_span_ids_json=row["transcript_span_ids_json"],
            title=row["title"],
            hook=row["hook"],
            rationale_json=row["rationale_json"],
            feature_scores_json=row["feature_scores_json"],
            cps=row["cps"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def put_candidate(
        self,
        candidate_id: str,
        media_id: str,
        transcript_id: str,
        start_ms: int,
        end_ms: int,
        transcript_span_ids_json: str,
        title: str | None,
        hook: str | None,
        rationale_json: str,
        feature_scores_json: str,
        cps: float,
        status: str,
        created_at: str,
    ) -> CandidateRecord:
        """Insert or replace a candidate record (idempotent for regenerated IDs)."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO candidates ({self._COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    media_id,
                    transcript_id,
                    start_ms,
                    end_ms,
                    transcript_span_ids_json,
                    title,
                    hook,
                    rationale_json,
                    feature_scores_json,
                    cps,
                    status,
                    created_at,
                ),
            )
        return CandidateRecord(
            id=candidate_id,
            media_id=media_id,
            transcript_id=transcript_id,
            start_ms=start_ms,
            end_ms=end_ms,
            transcript_span_ids_json=transcript_span_ids_json,
            title=title,
            hook=hook,
            rationale_json=rationale_json,
            feature_scores_json=feature_scores_json,
            cps=cps,
            status=status,
            created_at=created_at,
        )

    def get_candidate(self, candidate_id: str) -> CandidateRecord | None:
        """Retrieve a specific persisted candidate by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                f"SELECT {self._COLUMNS} FROM candidates WHERE id = ?",
                (candidate_id,),
            )
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None

    def update_candidate(
        self,
        candidate_id: str,
        *,
        start_ms: int,
        end_ms: int,
        title: str | None,
        hook: str | None,
        rationale_json: str,
        feature_scores_json: str,
        transcript_span_ids_json: str,
        cps: float,
        status: str,
    ) -> CandidateRecord | None:
        """Update a candidate's reviewed boundaries and re-derived scores.

        The deterministic ID stays stable so list/edit flows can address the
        same record; rationale_json must disclose that boundaries were edited.
        Returns None when the candidate does not exist.
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE candidates SET
                    start_ms = ?, end_ms = ?, title = ?, hook = ?,
                    rationale_json = ?, feature_scores_json = ?,
                    transcript_span_ids_json = ?, cps = ?, status = ?
                WHERE id = ?
                """,
                (
                    start_ms,
                    end_ms,
                    title,
                    hook,
                    rationale_json,
                    feature_scores_json,
                    transcript_span_ids_json,
                    cps,
                    status,
                    candidate_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_candidate(candidate_id)

    def list_media_candidates(self, media_id: str) -> list[CandidateRecord]:
        """List persisted candidates for a media asset, ranked by CPS descending.

        Ties are broken deterministically by start time ascending, then ID.
        """
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                f"""
                SELECT {self._COLUMNS} FROM candidates
                WHERE media_id = ?
                ORDER BY cps DESC, start_ms ASC, id ASC
                """,
                (media_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def delete_media_candidates(self, media_id: str) -> int:
        """Delete all candidates for a media asset (used before regeneration)."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM candidates WHERE media_id = ?", (media_id,))
            return cursor.rowcount


class RenderRepository:
    """Repository for RenderedClip persistence (PRD §5 FR-09, §7).

    A row is created ONLY after a render passed its exit-code check and the
    ffprobe output validation, so a record here always refers to a verified
    MP4.
    """

    _COLUMNS = (
        "id, candidate_id, media_id, output_path, width, height, duration_ms, "
        "size_bytes, video_probe_json, render_config_json, created_at"
    )

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path

    def _row_to_record(self, row: sqlite3.Row) -> RenderedClipRecord:
        return RenderedClipRecord(
            id=row["id"],
            candidate_id=row["candidate_id"],
            media_id=row["media_id"],
            output_path=row["output_path"],
            width=row["width"],
            height=row["height"],
            duration_ms=row["duration_ms"],
            size_bytes=row["size_bytes"],
            video_probe_json=row["video_probe_json"],
            render_config_json=row["render_config_json"],
            created_at=row["created_at"],
        )

    def create_rendered_clip(
        self,
        candidate_id: str,
        media_id: str,
        output_path: str,
        width: int,
        height: int,
        duration_ms: int,
        size_bytes: int,
        video_probe_json: str,
        render_config_json: str,
    ) -> RenderedClipRecord:
        """Persist a validated rendered clip record."""
        render_id = f"rnd_{uuid4().hex[:12]}"
        now = _utc_now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO rendered_clips ({self._COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    render_id,
                    candidate_id,
                    media_id,
                    output_path,
                    width,
                    height,
                    duration_ms,
                    size_bytes,
                    video_probe_json,
                    render_config_json,
                    now,
                ),
            )
        return RenderedClipRecord(
            id=render_id,
            candidate_id=candidate_id,
            media_id=media_id,
            output_path=output_path,
            width=width,
            height=height,
            duration_ms=duration_ms,
            size_bytes=size_bytes,
            video_probe_json=video_probe_json,
            render_config_json=render_config_json,
            created_at=now,
        )

    def get_rendered_clip(self, render_id: str) -> RenderedClipRecord | None:
        """Retrieve one validated rendered clip by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                f"SELECT {self._COLUMNS} FROM rendered_clips WHERE id = ?",
                (render_id,),
            )
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None

    def list_candidate_renders(self, candidate_id: str) -> list[RenderedClipRecord]:
        """List all validated renders for a candidate, newest first."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                f"""
                SELECT {self._COLUMNS} FROM rendered_clips
                WHERE candidate_id = ?
                ORDER BY created_at DESC
                """,
                (candidate_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]
