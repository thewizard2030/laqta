"""Persistent background job worker and queue (PRD §5 FR-10)."""

from app.jobs.manager import JobManager, job_manager

__all__ = ["JobManager", "job_manager"]
