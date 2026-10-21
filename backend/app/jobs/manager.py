"""Persistent single-worker background job manager (PRD §5 FR-02 & FR-10).

Ensures:
- Strictly serial execution (1 worker by default) to protect 8 GB RAM machines.
- Request handlers never block on media/FFmpeg processing.
- Persistent state, progress, and safe diagnostic logging in SQLite.
- Immediate cancellation and cleanup of subprocesses and partial artifacts.
- Safe recovery of interrupted jobs upon server restart (never pretend running).
"""

import asyncio
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.logging import logger
from app.db.models import JobRecord
from app.db.repository import CandidateRepository, ProjectRepository, RenderRepository
from app.schemas.captions import CaptionStyleSettings
from app.schemas.jobs import JobStatus, JobType
from app.schemas.transcription import TranscriptSegment
from app.services.bridge.manifest_sync import sync_manifest_to_db
from app.services.captions.service import generate_candidate_captions
from app.services.media.audio import (
    AudioExtractionError,
    JobCancelledError,
    clean_intermediate_audio,
    extract_audio_16k,
    extract_clip_audio_16k,
)
from app.services.media.probe import MediaProbeError, probe_media_file
from app.services.media.thumbnails import (
    extract_preview_frame,
    get_candidate_thumbnail_path,
)
from app.services.media.url_ingest import (
    UrlIngestError,
    detect_yt_dlp,
    run_url_ingest,
)
from app.services.rendering.render import (
    QUALITY_PRESETS as RENDER_PRESETS,
)
from app.services.rendering.render import (
    RenderError,
    build_render_command,
    probe_render_environment,
    probe_render_output,
    run_render_process,
    write_render_diagnostics,
)
from app.services.transcription import (
    TranscriptionError,
    get_transcription_provider,
)
from app.services.transcription.alignment import align_clip_words
from app.services.transcription.base import TranscriptionResult
from app.services.transcription.cache import (
    CACHE_SCHEMA_VERSION,
    compute_cache_key,
    load_cached_transcript,
    store_transcript,
)
from app.services.transcription.profiles import resolve_transcription_profile
from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineOrchestrator
from qatta.core.schema import AtomicUtterance, WordToken
from qatta.stages.s01_ingest import ingestor
from qatta.stages.s02_transcript import fast_pass, fine_pass
from qatta.stages.s03_multimodal import analyzer
from qatta.stages.s04_candidates import generator
from qatta.stages.s05_ranking import scorer
from qatta.stages.s06_render import renderer


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    """Manages the in-memory queue and persistent execution of background jobs."""

    def __init__(self, repo: ProjectRepository | None = None):
        self.repo = repo or ProjectRepository()
        self.candidates_repo = CandidateRepository()
        self.render_repo = RenderRepository()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._running_job_id: str | None = None
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the background worker and recover any interrupted jobs."""
        async with self._lock:
            if self._running:
                return

            # 1. Recover jobs that were left running when server died
            interrupted_count = self.repo.recover_interrupted_jobs()
            if interrupted_count > 0:
                logger.warning(
                    f"Recovered {interrupted_count} job(s) interrupted by prior server restart."
                )

            # 2. Re-enqueue any queued jobs that haven't started yet
            queued_jobs = self.repo.list_queued_jobs()
            for q_job in queued_jobs:
                logger.info(f"Re-enqueuing pending job on startup: {q_job.id}")
                await self._queue.put(q_job.id)

            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop(), name="job_worker_loop")
            logger.info("JobManager worker started (max_workers=1).")

    def is_running(self) -> bool:
        """Whether the background worker is alive.

        The health endpoint uses this: a stopped worker means queued jobs
        would never run, so the API must not report "healthy".
        """
        return self._running

    async def stop(self) -> None:
        """Stop worker task gracefully and cancel any in-flight work."""
        async with self._lock:
            if not self._running:
                return
            self._running = False

            # Signal cancellation to active job if any
            if self._running_job_id and self._running_job_id in self._cancel_events:
                self._cancel_events[self._running_job_id].set()

            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
                self._worker_task = None
            logger.info("JobManager worker stopped.")

    async def submit_job(
        self,
        project_id: str,
        job_type: str = JobType.AUDIO_EXTRACTION.value,
        media_id: str | None = None,
        config: dict | None = None,
    ) -> JobRecord:
        """Create and enqueue a background job. Non-blocking to HTTP request handlers."""
        # 1. Validate project existence
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # 2. Validate media existence if specified
        if media_id:
            media = self.repo.get_media_asset(media_id)
            if not media:
                raise ValueError(f"Media asset '{media_id}' not found.")
            if media.project_id != project_id:
                raise ValueError(
                    f"Media asset '{media_id}' does not belong to project '{project_id}'."
                )

        config_str = json.dumps(config) if config else None

        # 3. Create persistent record in SQLite
        job_record = self.repo.create_job(
            project_id=project_id,
            job_type=job_type,
            media_id=media_id,
            config_json=config_str,
        )

        # 4. Enqueue job ID
        await self._queue.put(job_record.id)
        logger.info(f"Submitted job {job_record.id} (type={job_type}) for project {project_id}")
        return job_record

    async def cancel_job(self, job_id: str) -> JobRecord | None:
        """Cancel a queued or currently executing job."""
        job = self.repo.get_job(job_id)
        if not job:
            return None

        # If already in a terminal state, cannot cancel
        terminal_statuses = {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }
        if job.status in terminal_statuses:
            return job

        # If still in queue (not currently running)
        if job.status == JobStatus.QUEUED.value and self._running_job_id != job_id:
            updated = self.repo.update_job(
                job_id=job_id,
                status=JobStatus.CANCELLED.value,
                stage="cancelled",
                error_code="CANCELLED",
                error_message="Job cancelled by user before execution started.",
                finished_at=_utc_now_iso(),
            )
            logger.info(f"Cancelled queued job {job_id}")
            return updated

        # If currently running, signal cancellation event
        if job_id in self._cancel_events:
            self._cancel_events[job_id].set()
            logger.info(f"Signalled cancellation event for running job {job_id}")

        # Wait briefly up to 2 seconds for worker to finalize cancellation
        for _ in range(20):
            await asyncio.sleep(0.1)
            current = self.repo.get_job(job_id)
            if current and current.status == JobStatus.CANCELLED.value:
                return current

        # Fallback update if worker hasn't updated yet
        return self.repo.update_job(
            job_id=job_id,
            status=JobStatus.CANCELLED.value,
            stage="cancelled",
            error_code="CANCELLED",
            error_message="Job was cancelled by user.",
            finished_at=_utc_now_iso(),
        )

    async def _worker_loop(self) -> None:
        """Single-worker consumer loop executing jobs sequentially."""
        logger.info("Background job worker loop active.")
        while self._running:
            try:
                # Wait for next job with timeout to allow checking self._running
                try:
                    job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                try:
                    await self._process_job(job_id)
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}")

    async def _process_job(self, job_id: str) -> None:
        """Execute a single background job safely."""
        job = self.repo.get_job(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found in database; skipping.")
            return

        # If job was cancelled while waiting in queue, skip execution
        if job.status == JobStatus.CANCELLED.value:
            logger.info(f"Job {job_id} was already cancelled in queue; skipping execution.")
            return

        cancel_event = asyncio.Event()
        self._cancel_events[job_id] = cancel_event
        self._running_job_id = job_id

        # Mark as running
        self.repo.update_job(
            job_id=job_id,
            status=JobStatus.RUNNING.value,
            stage="starting",
            progress=5.0,
            started_at=_utc_now_iso(),
        )

        try:
            if job.type == JobType.AUDIO_EXTRACTION.value:
                await self._execute_audio_extraction(job, cancel_event)
            elif job.type == JobType.TRANSCRIPTION.value:
                await self._execute_transcription(job, cancel_event)
            elif job.type == JobType.MULTIMODAL.value:
                await self._execute_multimodal(job, cancel_event)
            elif job.type == JobType.CANDIDATE_GENERATION.value:
                await self._execute_candidates(job, cancel_event)
            elif job.type == JobType.CANDIDATE_THUMBNAILS.value:
                await self._execute_candidate_thumbnails(job, cancel_event)
            elif job.type == JobType.URL_INGESTION.value:
                await self._execute_url_ingest(job, cancel_event)
            elif job.type == JobType.RENDER.value:
                await self._execute_render(job, cancel_event)
            elif job.type == JobType.PIPELINE.value:
                await self._execute_pipeline(job, cancel_event)
            else:
                raise AudioExtractionError(
                    f"Unsupported job type: '{job.type}'",
                    error_code="UNSUPPORTED_JOB_TYPE",
                )

        except JobCancelledError:
            logger.info(f"Job {job_id} cancelled.")
            self.repo.update_job(
                job_id=job_id,
                status=JobStatus.CANCELLED.value,
                stage="cancelled",
                error_code="CANCELLED",
                error_message="Job was cancelled by user request.",
                finished_at=_utc_now_iso(),
            )
            # Clean up temporary artifacts so cancelled jobs never leak
            # partial WAVs or .part render files to disk.
            self._cleanup_job_temp_dir(job_id)
        except (AudioExtractionError, TranscriptionError, RenderError, UrlIngestError) as e:
            logger.error(f"Job {job_id} failed with {e.error_code}: {e.message}")
            self.repo.update_job(
                job_id=job_id,
                status=JobStatus.FAILED.value,
                stage="failed",
                error_code=e.error_code,
                error_message=e.message,
                finished_at=_utc_now_iso(),
            )
        except Exception as e:
            logger.exception(f"Job {job_id} encountered unexpected error: {e}")
            self.repo.update_job(
                job_id=job_id,
                status=JobStatus.FAILED.value,
                stage="failed",
                error_code="INTERNAL_ERROR",
                error_message=f"Unexpected processing error: {e}",
                finished_at=_utc_now_iso(),
            )
        finally:
            self._cancel_events.pop(job_id, None)
            self._running_job_id = None

    def _cleanup_job_temp_dir(self, job_id: str) -> None:
        """Best-effort removal of a job's temp artifacts after cancellation."""
        job = self.repo.get_job(job_id)
        if not job:
            return
        try:
            settings.cleanup_job_temp_dir(job.project_id, job_id)
        except Exception as e:  # pragma: no cover - cleanup is best-effort
            logger.warning(f"Temp cleanup failed for job {job_id}: {e}")

    async def _execute_audio_extraction(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Run 16 kHz mono WAV audio extraction for a job."""
        if not job.media_id:
            raise AudioExtractionError(
                "Audio extraction job requires a media_id.",
                error_code="MISSING_MEDIA_ID",
            )

        media = self.repo.get_media_asset(job.media_id)
        if not media:
            raise AudioExtractionError(
                f"Media asset '{job.media_id}' not found.",
                error_code="MEDIA_NOT_FOUND",
            )

        input_path = Path(media.safe_path)
        output_path = settings.get_job_audio_path(job.project_id, job.id)

        # Progress reporting helper
        def on_progress(pct: float, stage: str) -> None:
            self.repo.update_job(job.id, progress=pct, stage=stage)

        # Execute extraction (real out_time-based percent when duration known)
        await extract_audio_16k(
            input_path=input_path,
            output_path=output_path,
            cancel_event=cancel_event,
            timeout_sec=float(settings.FFMPEG_TIMEOUT_SECONDS),
            progress_callback=on_progress,
            total_duration_ms=media.duration_ms,
        )

        # Prepare config JSON with output diagnostic metadata
        current_cfg = json.loads(job.config_json or "{}")
        current_cfg["output_wav_path"] = str(output_path)
        current_cfg["wav_size_bytes"] = output_path.stat().st_size if output_path.exists() else 0
        current_cfg["sample_rate"] = 16000
        current_cfg["channels"] = 1
        # Check configurable cleanup of intermediate WAV after successful completion
        if settings.CLEAN_INTERMEDIATE_WAV:
            cleaned = clean_intermediate_audio(output_path)
            current_cfg["intermediate_wav_cleaned"] = cleaned

        # Update manifest state
        try:
            orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
            orch.manifest.audio_16k_path = str(output_path.resolve())
            if "s01_ingest" not in orch.manifest.completed_stages:
                orch.manifest.completed_stages.append("s01_ingest")
            orch.save_manifest()
            sync_manifest_to_db(
                orch.manifest,
                job.project_id,
                self.repo,
                self.candidates_repo,
                self.render_repo,
            )
        except Exception as e:
            logger.warning(f"Could not update manifest during audio extraction: {e}")

        # Mark succeeded
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            config_json=json.dumps(current_cfg),
            finished_at=_utc_now_iso(),
        )

    async def _execute_transcription(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Run speech-to-text transcription for a media asset using audio extraction stage."""
        if not job.media_id:
            raise TranscriptionError(
                "Transcription job requires a media_id.",
                error_code="MISSING_MEDIA_ID",
            )

        media = self.repo.get_media_asset(job.media_id)
        if not media:
            raise TranscriptionError(
                f"Media asset '{job.media_id}' not found.",
                error_code="MEDIA_NOT_FOUND",
            )

        cfg = json.loads(job.config_json or "{}")

        # Step 1: Resolve performance profile + explicit overrides.
        # Explicit request fields always win; profile fills the rest.
        resolved = resolve_transcription_profile(
            cfg.get("profile"),
            model_size=cfg.get("model_size"),
            beam_size=cfg.get("beam_size"),
            word_timestamps=cfg.get("word_timestamps"),
            vad_filter=cfg.get("vad_filter"),
            compute_type=cfg.get("compute_type"),
        )
        model_size = resolved.config.model_size
        language = cfg.get("language", None)
        word_timestamps = resolved.config.word_timestamps
        provider_name = cfg.get("provider", "faster-whisper")
        beam_size = resolved.config.beam_size
        max_duration_sec = cfg.get("max_duration_sec", None)

        cfg["profile_resolved"] = resolved.to_dict()
        if resolved.config.accuracy_warning:
            cfg["accuracy_warning"] = resolved.config.accuracy_warning

        # Stage 1: Audio Extraction (re-use existing or extract)
        audio_path = settings.get_job_audio_path(job.project_id, job.id)
        if not audio_path.exists():

            def on_audio_progress(pct: float, stage: str) -> None:
                self.repo.update_job(job.id, progress=min(25.0, pct * 0.25), stage=stage)

            await extract_audio_16k(
                input_path=Path(media.safe_path),
                output_path=audio_path,
                cancel_event=cancel_event,
                progress_callback=on_audio_progress,
                total_duration_ms=media.duration_ms,
            )

        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        # Persist resolved profile into the job config for auditability.
        self.repo.update_job(job.id, config_json=json.dumps(cfg))

        cache_dir = settings.get_transcript_cache_dir()
        result: TranscriptionResult | None = None

        # Step 2 (optional): Reuse a cached transcript for identical audio and
        # identical transcription settings. Captions/layout/export-quality
        # changes never invalidate the cache, so re-opening or re-styling a
        # project skips ASR entirely.
        if settings.TRANSCRIPT_CACHE_ENABLED:
            try:
                settings_map = {
                    "model_size": model_size,
                    "language": language,
                    "beam_size": beam_size,
                    "vad_filter": resolved.config.vad_filter,
                    "compute_type": resolved.config.compute_type,
                    "word_timestamps": word_timestamps,
                    "profile": resolved.config.name,
                    "provider": provider_name,
                    "wav_sample_rate": 16000,
                    "wav_channels": 1,
                    "cache_schema_version": CACHE_SCHEMA_VERSION,
                }
                cache_key = compute_cache_key(audio_path, settings_map)
                cached = load_cached_transcript(cache_dir, cache_key)
                if cached is not None:
                    cached_result = cached["result"]
                    cached_segments = [TranscriptSegment(**s) for s in cached_result["segments"]]
                    result = TranscriptionResult(
                        language=cached_result.get("language") or "unknown",
                        language_probability=cached_result.get("language_probability"),
                        duration=float(cached_result.get("duration") or 0.0),
                        text=cached_result.get("text") or "",
                        segments=cached_segments,
                        word_timestamps_available=bool(
                            cached_result.get("word_timestamps_available")
                        ),
                        timing_granularity=cached_result.get("timing_granularity") or "segment",
                        provider=cached_result.get("provider") or "cached",
                        model=cached_result.get("model") or model_size,
                    )
                    cfg["cache"] = {
                        "hit": True,
                        "key": cache_key,
                        "stored_at": cached.get("stored_at"),
                    }
                    self.repo.update_job(
                        job.id,
                        progress=85.0,
                        stage="restored_from_cache",
                    )
                    logger.info(
                        f"Transcript cache hit for job {job.id} (key={cache_key[:12]}...); "
                        "ASR skipped."
                    )
            except Exception as e:
                # Cache problems must never break transcription: fall through
                # to a fresh ASR pass and disclose the cache failure.
                logger.warning(f"Transcript cache read failed (proceeding with ASR): {e}")

        if result is None:
            # Stage 2: Transcription (Pass A: full video without word-level
            # alignment unless the profile or explicit override enables it).
            self.repo.update_job(
                job.id,
                progress=30.0,
                stage="transcribing",
            )

            def on_transcribe_progress(pct: float, stage: str) -> None:
                scaled = 30.0 + (pct * 0.6)  # 30% -> 90%
                self.repo.update_job(job.id, progress=min(95.0, scaled), stage=stage)

            provider = get_transcription_provider(provider_name)
            result = await provider.transcribe(
                audio_path=audio_path,
                language=language,
                model_size=model_size,
                word_timestamps=word_timestamps,
                cancel_event=cancel_event,
                progress_callback=on_transcribe_progress,
                beam_size=beam_size,
                vad_filter=resolved.config.vad_filter,
                max_duration_sec=max_duration_sec,
                compute_type=resolved.config.compute_type,
            )

            if settings.TRANSCRIPT_CACHE_ENABLED:
                try:
                    settings_map = {
                        "model_size": model_size,
                        "language": language,
                        "beam_size": beam_size,
                        "vad_filter": resolved.config.vad_filter,
                        "compute_type": resolved.config.compute_type,
                        "word_timestamps": word_timestamps,
                        "profile": resolved.config.name,
                        "provider": provider_name,
                        "wav_sample_rate": 16000,
                        "wav_channels": 1,
                        "cache_schema_version": CACHE_SCHEMA_VERSION,
                    }
                    cache_key = compute_cache_key(audio_path, settings_map)
                    stored = store_transcript(
                        cache_dir,
                        cache_key,
                        settings_map,
                        {
                            "language": result.language,
                            "language_probability": result.language_probability,
                            "duration": result.duration,
                            "text": result.text,
                            "segments": [s.model_dump() for s in result.segments],
                            "word_timestamps_available": result.word_timestamps_available,
                            "timing_granularity": result.timing_granularity,
                            "provider": result.provider,
                            "model": result.model,
                        },
                    )
                    if stored is not None:
                        cfg["cache"] = {"hit": False, "key": cache_key}
                except Exception as e:
                    logger.warning(f"Transcript cache write failed (transcript preserved): {e}")

        # Stage 3: Persist Transcript
        self.repo.update_job(job.id, progress=95.0, stage="persisting_transcript")
        segments_json = json.dumps([s.model_dump() for s in result.segments])
        transcript_record = self.repo.create_transcript(
            media_id=media.id,
            language=result.language,
            provider=result.provider,
            model=result.model,
            text=result.text,
            segments_json=segments_json,
            word_timestamps_available=result.word_timestamps_available,
            timing_granularity=result.timing_granularity,
            status="completed",
        )

        # Configurable cleanup of intermediate WAV after successful downstream completion
        if settings.CLEAN_INTERMEDIATE_WAV:
            cleaned = clean_intermediate_audio(audio_path)
            cfg["intermediate_wav_cleaned"] = cleaned

        cfg["transcript_id"] = transcript_record.id
        cfg["detected_language"] = result.language
        cfg["word_timestamps_available"] = result.word_timestamps_available
        cfg["timing_granularity"] = result.timing_granularity
        cfg["device"] = result.device
        cfg["compute_type"] = result.compute_type
        cfg["fallback_reason"] = result.fallback_reason
        cfg["speaker_diarization_available"] = result.speaker_diarization_available

        # Update manifest state
        try:
            orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
            import re

            utterances = []
            for idx, s in enumerate(result.segments, start=1):
                u_id = f"U_{idx:04d}"
                start_ms = int(round(s.start * 1000))
                end_ms = max(start_ms + 1, int(round(s.end * 1000)))
                words = []
                for w in getattr(s, "words", []):
                    w_start = int(round(w.start * 1000))
                    w_end = max(w_start + 1, int(round(w.end * 1000)))
                    is_lat = bool(re.search(r"[A-Za-z]", w.word))
                    words.append(
                        WordToken(
                            word=w.word,
                            start_ms=w_start,
                            end_ms=w_end,
                            confidence=min(1.0, max(0.0, float(w.probability))),
                            is_latin=is_lat,
                        )
                    )
                utterances.append(
                    AtomicUtterance(
                        u_id=u_id,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=s.text.strip() or "...",
                        words=words,
                    )
                )
            orch.manifest.atomic_utterances = utterances
            if "s02_transcript" not in orch.manifest.completed_stages:
                orch.manifest.completed_stages.append("s02_transcript")
            orch.save_manifest()
        except Exception as e:
            logger.warning(f"Could not update manifest during transcription: {e}")

        # Succeeded
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            config_json=json.dumps(cfg),
            finished_at=_utc_now_iso(),
        )

    async def _execute_render(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Render one approved candidate to a vertical MP4 (PRD FR-09, Gate D).

        Success is only possible after: FFmpeg exit code 0, an ffprobe
        validation of the output (resolution, H.264/AAC, duration), and an
        atomic rename of a `.part-*` temp file. Failed and cancelled renders
        are never marked successful.
        """
        if not job.media_id:
            raise RenderError(
                "Render job requires a media_id.",
                error_code="MISSING_MEDIA_ID",
            )

        media = self.repo.get_media_asset(job.media_id)
        if not media:
            raise RenderError(
                f"Media asset '{job.media_id}' not found.",
                error_code="MEDIA_NOT_FOUND",
            )

        cfg = json.loads(job.config_json or "{}")
        candidate_id = cfg.get("candidate_id")
        if not candidate_id:
            raise RenderError(
                "Render config must reference a candidate_id.",
                error_code="MISSING_CANDIDATE_ID",
            )
        candidate = self.candidates_repo.get_candidate(candidate_id)
        if not candidate or candidate.media_id != media.id:
            raise RenderError(
                f"Candidate '{candidate_id}' not found for this media asset.",
                error_code="CANDIDATE_NOT_FOUND",
            )

        layout = cfg.get("layout", "center_crop")
        quality = cfg.get("quality", "high")
        caption_format = cfg.get("caption_format", "ass")
        overwrite = bool(cfg.get("overwrite", False))
        style = CaptionStyleSettings(**(cfg.get("style") or {}))
        preset = RENDER_PRESETS.get(quality)
        if preset is None:
            raise RenderError(
                f"Unknown quality preset '{quality}'.",
                error_code="INVALID_CONFIG",
            )

        # 1. Honest environment probe with actionable diagnostics (FR-02/FR-09)
        env = probe_render_environment()
        if not env["ffmpeg_available"]:
            raise RenderError(
                f"FFmpeg is unavailable. {env['install_hint']}",
                error_code="FFMPEG_NOT_FOUND",
            )
        if caption_format != "none" and not env["libass_available"]:
            raise RenderError(
                "This FFmpeg build has no libass subtitles filter, so burnt-in "
                "captions are unavailable. Install an ffmpeg build with libass "
                "(e.g. 'sudo dnf install ffmpeg' on Fedora) or choose "
                "caption_format='none'.",
                error_code="LIBASS_UNAVAILABLE",
            )
        if not env["h264_encoder_available"]:
            raise RenderError(
                "FFmpeg without a libx264 encoder found; MP4 H.264 output is "
                "impossible with this build.",
                error_code="ENCODER_UNAVAILABLE",
            )
        if not env["aac_encoder_available"]:
            raise RenderError(
                "FFmpeg without an AAC encoder found; MP4 AAC audio output is "
                "impossible with this build.",
                error_code="ENCODER_UNAVAILABLE",
            )

        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            raise RenderError(
                "ffprobe is unavailable; rendered output cannot be validated.",
                error_code="FFPROBE_NOT_FOUND",
            )

        # 2. Decode transcript and generate captions (pure Python text work)
        transcript = self.repo.get_transcript(candidate.transcript_id)
        if transcript is None:
            raise RenderError(
                f"Transcript '{candidate.transcript_id}' no longer exists; "
                "re-run candidate generation before rendering.",
                error_code="TRANSCRIPT_NOT_FOUND",
            )
        try:
            segments = [TranscriptSegment(**s) for s in json.loads(transcript.segments_json)]
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            raise RenderError(
                f"Stored transcript segments are not parseable: {e}",
                error_code="INVALID_TRANSCRIPT",
            ) from e

        caption_path: str | None = None
        aligned_for_captions = None
        if caption_format != "none":
            cfg["captions"] = None

            # Pass B: clip-scoped word re-timing for precise speech sync and animated
            # word-by-word captions. Runs when the stored transcript lacks word timings
            # AND the clip is small enough to bound work. Re-times spoken words to provide
            # exact speaker timing alignment. Failures fall back to the existing
            # segment-level caption path; the transcript is never discarded.
            alignment_info: dict = {"attempted": False}
            if not transcript.word_timestamps_available and settings.CLIP_ALIGNMENT_ENABLED:
                alignment_info["attempted"] = True
                clip_duration_ms = candidate.end_ms - candidate.start_ms
                if clip_duration_ms / 1000.0 > settings.MAX_CLIP_ALIGNMENT_SECONDS:
                    alignment_info["reason"] = "clip_too_long_for_alignment"
                    logger.info(
                        f"Skipping clip alignment: clip is {clip_duration_ms} ms "
                        "> MAX_CLIP_ALIGNMENT_SECONDS."
                    )
                else:
                    self.repo.update_job(job.id, stage="aligning_selected_clips", progress=10.0)
                    temp_dir = settings.get_job_temp_dir(job.project_id, job.id)
                    clip_wav_path = temp_dir / "clip_slice_16k.wav"
                    try:
                        await extract_clip_audio_16k(
                            input_path=Path(media.safe_path),
                            output_path=clip_wav_path,
                            start_ms=candidate.start_ms,
                            duration_ms=clip_duration_ms,
                            cancel_event=cancel_event,
                            timeout_sec=float(settings.FFMPEG_TIMEOUT_SECONDS),
                        )
                        aligned_for_captions = await align_clip_words(
                            clip_audio_path=clip_wav_path,
                            clip_start_ms=candidate.start_ms,
                            clip_duration_ms=clip_duration_ms,
                            language=transcript.language,
                            model_size=settings.CLIP_ALIGNMENT_MODEL,
                            compute_type=settings.CLIP_ALIGNMENT_COMPUTE_TYPE,
                            cancel_event=cancel_event,
                        )
                        alignment_info.update(
                            {
                                "accepted": True,
                                "word_count": aligned_for_captions.word_count,
                                "provider": aligned_for_captions.provider,
                                "model": aligned_for_captions.model,
                                "beam_size": aligned_for_captions.beam_size,
                            }
                        )
                    except JobCancelledError:
                        raise
                    except Exception as e:
                        # Never fail the render because word re-timing could
                        # not run: disclose the reason and keep segment-level
                        # captions from the full-video transcript.
                        reason = getattr(e, "error_code", None) or str(e)
                        logger.warning(
                            f"Clip alignment failed for candidate {candidate.id} "
                            f"({reason}); falling back to segment-level captions."
                        )
                        alignment_info.update({"accepted": False, "reason": str(reason)})
            cfg["captions_alignment"] = alignment_info

            segments_for_captions = (
                aligned_for_captions.segments if aligned_for_captions is not None else segments
            )
            captions = generate_candidate_captions(
                captions_dir=settings.get_project_captions_dir(job.project_id),
                candidate_id=candidate.id,
                start_ms=candidate.start_ms,
                end_ms=candidate.end_ms,
                segments=segments_for_captions,
                style=style,
                formats=("srt", "ass"),
            )
            caption_path = captions.ass_path if caption_format == "ass" else captions.srt_path
            if caption_path is None:
                raise RenderError(
                    f"Caption file could not be generated ({caption_format}).",
                    error_code="CAPTION_GENERATION_FAILED",
                )
            cfg["captions"] = {
                "timing_granularity": captions.timing_granularity,
                "karaoke_used": captions.karaoke_used,
                "warnings": captions.warnings,
                "srt_path": captions.srt_path,
                "ass_path": captions.ass_path,
                "alignment": alignment_info,
            }
            if aligned_for_captions is not None:
                cfg["captions"]["note"] = (
                    "Word timings were re-derived on the selected clip "
                    "(Pass B); karaoke text comes from that clip pass and "
                    "may differ slightly from the full-video transcript."
                )

        # 3. Safe overwrite handling: refuse silently clobbering user outputs.
        # The output name is STABLE per candidate (FR-09); re-rendering the
        # same candidate replaces it only with explicit `overwrite: true`.
        renders_dir = settings.get_project_renders_dir(job.project_id)
        final_output = renders_dir / f"{candidate.id}.mp4"
        if final_output.exists() and not overwrite:
            raise RenderError(
                f"Output already exists at {final_output}. Re-run with "
                "'overwrite': true to replace it (FR-09 safe overwrite).",
                error_code="OUTPUT_EXISTS",
            )
        if final_output.exists() and overwrite:
            logger.warning(f"Explicit overwrite requested for existing render {final_output}.")
        else:
            logger.info(f"Render output target: {final_output}")

        temp_output_dir = settings.get_job_temp_dir(job.project_id, job.id)
        temp_output = temp_output_dir / ".part-render.mp4"
        if temp_output.exists():
            temp_output.unlink(missing_ok=True)

        # 4. Build deterministic argv (persisted for debuggability)
        argv = build_render_command(
            ffmpeg_bin=env["ffmpeg_path"],
            input_path=Path(media.safe_path),
            output_path=temp_output,
            layout=layout,
            quality=quality,
            src_width=media.width,
            src_height=media.height,
            has_audio=media.audio_codec != "none",
            caption_path=caption_path,
            caption_format=caption_format,
            start_ms=candidate.start_ms,
            duration_ms=candidate.end_ms - candidate.start_ms,
            video_encoder=env["h264_encoder"],
        )
        cfg["render"] = {
            "layout": layout,
            "quality": quality,
            "width": preset["width"],
            "height": preset["height"],
            "crf": preset["crf"],
            "video_preset": preset["video_preset"],
            "caption_format": caption_format,
            "input_path": str(media.safe_path),
            "temp_output": str(temp_output),
            "final_output": str(final_output),
            "overwrite": overwrite,
        }
        self.repo.update_job(job.id, stage="rendering", progress=20.0)

        # 5. Execute (arg array, timeout, cancellation) and validate output
        _, stderr_log = await run_render_process(
            argv=argv,
            output_path=temp_output,
            cancel_event=cancel_event,
            timeout_sec=float(settings.FFMPEG_TIMEOUT_SECONDS),
        )
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        expected_duration_ms = candidate.end_ms - candidate.start_ms
        probe = probe_render_output(
            ffprobe_bin=ffprobe_bin,
            output_path=temp_output,
            expected_width=int(preset["width"]),
            expected_height=int(preset["height"]),
            expected_duration_ms=expected_duration_ms,
        )
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()

        # 6. Atomic rename and persisted per-render diagnostics (FR-09)
        os.replace(temp_output, final_output)
        diag = write_render_diagnostics(
            log_dir=renders_dir / "logs",
            render_id=job.id,
            argv=argv,
            config={
                "layout": layout,
                "quality": quality,
                "caption_format": caption_format,
                "input_path": str(media.safe_path),
                "output_path": str(final_output),
                "overwrite": overwrite,
                "probe": probe.to_dict(),
                "candidate_id": candidate.id,
            },
            stderr_log=stderr_log,
        )

        # 7. Persist the validated RenderedClip record, then mark success
        self.repo.update_job(job.id, progress=95.0, stage="persisting_render")
        self.render_repo.create_rendered_clip(
            candidate_id=candidate.id,
            media_id=media.id,
            output_path=str(final_output),
            width=probe.width,
            height=probe.height,
            duration_ms=probe.duration_ms,
            size_bytes=probe.size_bytes,
            video_probe_json=json.dumps(probe.to_dict()),
            render_config_json=json.dumps({**cfg["render"], **diag}, ensure_ascii=False),
        )
        cfg["output_path"] = str(final_output)
        cfg["render_id_diag"] = diag
        cfg["probe"] = probe.to_dict()

        # Update manifest state
        try:
            orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
            for c in orch.manifest.candidates:
                if c.clip_id == candidate.id:
                    c.rendered_paths["vertical_9_16"] = str(final_output)
            if "s06_render" not in orch.manifest.completed_stages:
                orch.manifest.completed_stages.append("s06_render")
            orch.save_manifest()
        except Exception as e:
            logger.warning(f"Could not update manifest during render: {e}")

        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            config_json=json.dumps(cfg, ensure_ascii=False),
            finished_at=_utc_now_iso(),
        )
        logger.info(f"Render job {job.id} completed successfully: {final_output}")

    def _get_or_create_orchestrator(
        self, project_id: str, media_id: str | None = None
    ) -> PipelineOrchestrator:
        """Initialize or load a PipelineOrchestrator for the project, with all stages registered."""
        project_dir = settings.get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = project_dir / "qatta_manifest.json"

        source_path = None
        if media_id:
            media = self.repo.get_media_asset(media_id)
            if media:
                source_path = Path(media.safe_path)
        if not source_path and not manifest_path.exists():
            media_list = self.repo.list_project_media(project_id)
            if media_list:
                source_path = Path(media_list[0].safe_path)

        if not manifest_path.exists() and source_path and not Path(source_path).is_file():
            from qatta.core.schema import QattaManifest

            duration = 10.0
            if media_id:
                m = self.repo.get_media_asset(media_id)
                if m and m.duration_ms:
                    duration = max(0.1, m.duration_ms / 1000.0)
            init_manifest = QattaManifest(
                project_id=project_id,
                source_path=str(source_path),
                duration_sec=duration,
            )
            manifest_path.write_text(init_manifest.model_dump_json(), encoding="utf-8")
            source_path = None

        q_settings = QattaSettings()
        orch = PipelineOrchestrator(
            project_id=project_id,
            source_path=source_path,
            work_dir=project_dir,
            settings=q_settings,
        )
        from qatta.stages.s05b_section_fetch import section_fetch

        ingestor.register(orch)
        fast_pass.register(orch)
        fine_pass.register(orch)
        analyzer.register(orch)
        generator.register(orch)
        scorer.register(orch)
        section_fetch.register(orch)
        renderer.register(orch)
        return orch

    async def _execute_multimodal(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Run Stage s03 multimodal analysis (scene cuts & acoustic features)."""
        orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        self.repo.update_job(job.id, progress=30.0, stage="analyzing_multimodal")
        orch.run_stage("s03_multimodal", force=True)
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        sync_manifest_to_db(
            orch.manifest,
            job.project_id,
            self.repo,
            self.candidates_repo,
            self.render_repo,
        )
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            finished_at=_utc_now_iso(),
        )

    async def _execute_candidates(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Run Stage s04 candidate generation and Stage s05 CPS ranking."""
        orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        self.repo.update_job(job.id, progress=20.0, stage="generating_candidates")
        orch.run_stage("s04_candidates", force=True)
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        self.repo.update_job(job.id, progress=70.0, stage="ranking_candidates")
        orch.run_stage("s05_ranking", force=True)
        if cancel_event and cancel_event.is_set():
            raise JobCancelledError()
        sync_manifest_to_db(
            orch.manifest,
            job.project_id,
            self.repo,
            self.candidates_repo,
            self.render_repo,
        )
        # Thumbnail extraction runs as its own background job (never blocks
        # this handler, never blocks a request handler).
        await self._enqueue_candidate_thumbnails(job.project_id, job.media_id)
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            finished_at=_utc_now_iso(),
        )

    async def _enqueue_candidate_thumbnails(self, project_id: str, media_id: str | None) -> None:
        """Submit a candidate-thumbnails job for a media asset (best effort).

        Thumbnail images are decorative previews; a failure to enqueue them
        must never break candidate generation, so every error is only logged.
        """
        if not media_id:
            return
        try:
            await self.submit_job(
                project_id=project_id,
                job_type=JobType.CANDIDATE_THUMBNAILS.value,
                media_id=media_id,
            )
        except Exception as e:  # pragma: no cover - enqueue is best-effort
            logger.warning(f"Could not enqueue candidate thumbnails job: {e}")

    async def _execute_candidate_thumbnails(
        self, job: JobRecord, cancel_event: asyncio.Event
    ) -> None:
        """Extract one small preview JPEG per candidate (fail-open per frame)."""
        if not job.media_id:
            raise AudioExtractionError(
                "Thumbnail job requires a media_id.",
                error_code="MISSING_MEDIA_ID",
            )
        media = self.repo.get_media_asset(job.media_id)
        if not media:
            raise AudioExtractionError(
                f"Media asset '{job.media_id}' not found.",
                error_code="MEDIA_NOT_FOUND",
            )

        candidates = self.candidates_repo.list_media_candidates(job.media_id)
        # Honest summary state persisted into the job record at the end.
        extracted = skipped = failed = 0

        if candidates:
            input_path = Path(media.safe_path)
            for idx, cand in enumerate(candidates):
                if cancel_event and cancel_event.is_set():
                    raise JobCancelledError()

                out_path = get_candidate_thumbnail_path(job.project_id, job.media_id, cand.id)
                if out_path.is_file():
                    skipped += 1
                else:
                    # Never seek into the last half second: frames are for
                    # preview only, and probing beyond the stream would fail.
                    at_ms = min(cand.start_ms, max(0, media.duration_ms - 500))
                    try:
                        await extract_preview_frame(
                            input_path,
                            out_path,
                            at_ms,
                            cancel_event=cancel_event,
                        )
                        extracted += 1
                    except JobCancelledError:
                        raise
                    except Exception as e:
                        failed += 1
                        logger.warning(f"Thumbnail extraction failed for candidate {cand.id}: {e}")

                self.repo.update_job(
                    job.id,
                    progress=5.0 + 90.0 * (idx + 1) / len(candidates),
                    stage=f"extracting_frames ({idx + 1}/{len(candidates)})",
                )

        if candidates and extracted == 0 and failed > 0 and skipped == 0:
            raise AudioExtractionError(
                f"All {failed} thumbnail extractions failed; "
                "FFmpeg may be incompatible with this media file.",
                error_code="FRAME_EXTRACT_FAILED",
            )

        summary = {
            "candidates_total": len(candidates),
            "extracted": extracted,
            "cached": skipped,
            "failed": failed,
        }
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            config_json=json.dumps(summary),
            finished_at=_utc_now_iso(),
        )

    async def _execute_url_ingest(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Download one externally hosted video via local yt-dlp (PRD FR-12).

        Gating is re-verified here too: even a queued/created job refuses to
        run if the operator flag was turned off after enqueueing — nothing
        may run silently. The downloaded file is ffprobe-validated and then
        imported exactly like a local upload (same media directory, same DB
        record path), and the per-job temp/chunk directory is cleaned up.
        """
        if not settings.ENABLE_URL_INGESTION:
            raise UrlIngestError(
                "URL ingestion is disabled; the operator flag "
                "QATTA_ENABLE_URL_INGESTION is required to run this job.",
                error_code="URL_INGEST_DISABLED",
            )

        cfg = json.loads(job.config_json or "{}")
        url = cfg.get("url")
        if not url or not cfg.get("rights_confirmed"):
            raise UrlIngestError(
                "Job config is missing the validated URL or the explicit "
                "rights confirmation; refusing to download.",
                error_code="URL_INGEST_INVALID_CONFIG",
            )

        yt_dlp = detect_yt_dlp()
        if not yt_dlp.available:
            raise UrlIngestError(
                "yt-dlp is not installed; install it to enable URL ingestion.",
                error_code="YT_DLP_NOT_FOUND",
            )

        download_dir = settings.get_job_temp_dir(job.project_id, job.id)

        def on_progress(pct: float, stage: str) -> None:
            self.repo.update_job(job.id, progress=pct, stage=stage)

        download_result = await run_url_ingest(
            url,
            download_dir,
            cancel_event=cancel_event,
            progress_callback=on_progress,
        )

        if isinstance(download_result, Path):
            downloaded = download_result
            subtitle_path = None
            detected_lang = None
        else:
            downloaded = download_result.media_path
            subtitle_path = download_result.subtitle_path
            detected_lang = download_result.language

        # Validate the container/codecs with ffprobe before trusting it.
        try:
            probe_result = probe_media_file(downloaded)
        except MediaProbeError as e:
            raise UrlIngestError(
                f"Downloaded file failed media probe: {e}",
                error_code="URL_INGEST_PROBE_FAILED",
            ) from e

        media_dir = settings.get_project_media_dir(job.project_id)
        target_path = media_dir / f"med_{uuid4().hex[:12]}{downloaded.suffix.lower()}"
        shutil.move(str(downloaded), target_path)

        media_asset = self.repo.create_media_asset(
            project_id=job.project_id,
            safe_path=str(target_path),
            original_name=downloaded.name,
            size_bytes=target_path.stat().st_size,
            duration_ms=probe_result.duration_ms,
            width=probe_result.width,
            height=probe_result.height,
            video_codec=probe_result.video_codec,
            audio_codec=probe_result.audio_codec,
            status="ready",
        )
        cfg["media_id"] = media_asset.id
        cfg["media_path"] = str(target_path.resolve())

        # Ingest subtitles/captions if downloaded from YouTube
        if (
            subtitle_path
            and Path(subtitle_path).is_file()
            and Path(subtitle_path).stat().st_size > 0
        ):
            try:
                from qatta.core.schema import QattaManifest
                from qatta.stages.s02_transcript.fast_pass import (
                    run_youtube_subs_fast_pass,
                )
                from qatta.stages.s02_transcript.youtube_subs import (
                    segments_from_youtube_subs,
                )

                vtt_text = Path(subtitle_path).read_text(encoding="utf-8", errors="replace")
                raw_segments = segments_from_youtube_subs(
                    vtt_text, total_ms=probe_result.duration_ms
                )
                if raw_segments:
                    # Save subtitle file permanently in project subtitles directory
                    subtitles_dir = settings.get_project_dir(job.project_id) / "subtitles"
                    subtitles_dir.mkdir(parents=True, exist_ok=True)
                    perm_vtt = subtitles_dir / f"{media_asset.id}.vtt"
                    shutil.copyfile(str(subtitle_path), str(perm_vtt))

                    api_segments = [
                        {
                            "id": f"u_{idx:04d}",
                            "start": round(seg.start_ms / 1000.0, 3),
                            "end": round(seg.end_ms / 1000.0, 3),
                            "text": seg.text,
                            "words": None,
                            "speaker": None,
                        }
                        for idx, seg in enumerate(raw_segments, start=1)
                    ]
                    full_text = " ".join(seg.text for seg in raw_segments)
                    tr_rec = self.repo.create_transcript(
                        media_id=media_asset.id,
                        language=detected_lang or "ar",
                        provider="youtube",
                        model="captions",
                        text=full_text,
                        segments_json=json.dumps(api_segments),
                        word_timestamps_available=False,
                        timing_granularity="segment",
                        status="completed",
                    )
                    cfg["transcript_created"] = True
                    cfg["transcript_id"] = tr_rec.id
                    cfg["transcript_language"] = detected_lang or "ar"
                    cfg["transcript_segments"] = len(raw_segments)

                    # Initialize or update qatta_manifest.json with atomic utterances
                    manifest_path = settings.get_project_dir(job.project_id) / "qatta_manifest.json"
                    init_manifest = QattaManifest(
                        project_id=job.project_id,
                        source_path=str(target_path.resolve()),
                        source_url=url,
                        subtitle_path=str(perm_vtt.resolve()),
                        duration_sec=max(0.1, probe_result.duration_ms / 1000.0),
                        video_width=probe_result.width,
                        video_height=probe_result.height,
                    )
                    try:
                        populated_manifest = run_youtube_subs_fast_pass(init_manifest)
                        populated_manifest.completed_stages = ["s01_ingest", "s02_transcript"]
                        manifest_path.write_text(
                            populated_manifest.model_dump_json(indent=2), encoding="utf-8"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to populate manifest from YouTube subs: {e}")
                else:
                    cfg["transcript_created"] = False
                    cfg["transcript_note"] = (
                        "YouTube captions file was empty or could not be parsed."
                    )
            except Exception as e:
                logger.warning(f"YouTube transcript extraction skipped: {e}")
                cfg["transcript_created"] = False
                cfg["transcript_error"] = str(e)
        else:
            cfg["transcript_created"] = False
            cfg["transcript_note"] = "No caption track found on YouTube; local Whisper available."

        # Tier 3 fallback: if no platform captions were found, auto-enqueue
        # the local Whisper transcription job.
        if not cfg.get("transcript_created") and getattr(
            settings, "AUTO_TRANSCRIBE_ON_INGEST_FALLBACK", True
        ):
            try:
                await self.submit_job(
                    project_id=job.project_id,
                    job_type=JobType.TRANSCRIPTION.value,
                    media_id=media_asset.id,
                    config={
                        "profile": settings.DEFAULT_WHISPER_PROFILE,
                        "word_timestamps": False,
                    },
                )
                cfg["fallback_transcription_enqueued"] = True
                logger.info(
                    f"Auto-enqueued fallback Whisper transcription job for media {media_asset.id}"
                )
            except Exception as e:
                logger.warning(f"Could not auto-enqueue fallback transcription job: {e}")
                cfg["fallback_transcription_enqueued"] = False

        # The downloaded file has been moved out; drop leftover yt-dlp temp
        # files (parts, subtitles, metadata) from this job's temp dir.
        settings.cleanup_job_temp_dir(job.project_id, job.id)

        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            config_json=json.dumps(cfg),
            finished_at=_utc_now_iso(),
        )

    async def _execute_pipeline(self, job: JobRecord, cancel_event: asyncio.Event) -> None:
        """Execute full end-to-end Laqta manifest pipeline sequentially."""
        orch = self._get_or_create_orchestrator(job.project_id, job.media_id)
        stages = [
            ("s01_ingest", 15.0, "ingesting_media"),
            ("s02_transcript", 35.0, "transcribing_audio"),
            ("s03_multimodal", 50.0, "analyzing_multimodal"),
            ("s04_candidates", 60.0, "generating_candidates"),
            ("s05_ranking", 70.0, "ranking_candidates"),
            ("s05b_section_fetch", 80.0, "fetching_clip_sections"),
            ("s02b_fine_alignment", 90.0, "aligning_clip_words"),
            ("s06_render", 96.0, "rendering_shorts"),
        ]
        for stage_name, pct, stage_label in stages:
            if cancel_event and cancel_event.is_set():
                raise JobCancelledError()
            self.repo.update_job(job.id, progress=pct, stage=stage_label)
            orch.run_stage(stage_name, force=False)
            sync_manifest_to_db(
                orch.manifest,
                job.project_id,
                self.repo,
                self.candidates_repo,
                self.render_repo,
            )

        # Pipeline overwrites candidates (s04/s05) — refresh their thumbnails.
        await self._enqueue_candidate_thumbnails(job.project_id, job.media_id)
        self.repo.update_job(
            job_id=job.id,
            status=JobStatus.SUCCEEDED.value,
            stage="completed",
            progress=100.0,
            finished_at=_utc_now_iso(),
        )


# Global singleton instance
job_manager = JobManager()
