# Routes

## Overview
FastAPI endpoint handlers defining the public HTTP interface for health checks, system capabilities, application settings, media assets, background jobs, transcription, candidate curation, and video renders.

## Interface
- __init__.py: api_router - Root APIRouter mounting all route modules
- GET /api/health -> HealthResponse [health.py:get_health]
- GET /api/capabilities -> CapabilitiesResponse [capabilities.py:get_capabilities]
- GET /api/settings -> SettingsResponse [settings.py:get_settings]
- PATCH /api/settings -> SettingsResponse [settings.py:update_settings]
- POST /api/settings/verify -> VerifyKeyResponse [settings.py:verify_provider_key]
- POST /api/settings/clear-cache -> ClearCacheResponse [settings.py:clear_cache]
- GET /api/projects -> list[ProjectResponse] [projects.py:list_projects]
- POST /api/projects -> ProjectResponse [projects.py:create_project]
- GET /api/projects/{project_id} -> ProjectResponse [projects.py:get_project]
- DELETE /api/projects/{project_id} -> None [projects.py:delete_project]
- POST /api/projects/{project_id}/media/upload -> MediaAssetResponse [projects.py:upload_media]
- GET /api/media/{media_id} -> MediaAssetResponse [media.py:get_media]
- GET /api/media/{media_id}/file -> StreamingResponse / FileResponse [media.py:stream_media_file]
- POST /api/media/ingest-url -> UrlIngestAcceptedResponse [media.py:ingest_url]
- GET /api/media/candidates/{candidate_id}/thumbnail -> FileResponse [media.py:get_candidate_thumbnail]
- POST /api/jobs -> JobResponse [jobs.py:submit_job]
- GET /api/jobs -> list[JobResponse] [jobs.py:list_jobs]
- GET /api/jobs/{job_id} -> JobResponse [jobs.py:get_job]
- POST /api/jobs/{job_id}/cancel -> JobResponse [jobs.py:cancel_job]
- GET /api/transcription/providers -> list[ProviderCapabilityInfo] [transcription.py:list_transcription_providers]
- POST /api/media/{media_id}/transcribe -> JobResponse [transcription.py:start_transcription_job]
- GET /api/media/{media_id}/transcript -> TranscriptResponse [transcription.py:get_media_transcript]
- POST /api/media/{media_id}/candidates/generate -> CandidateGenerationResponse [candidates.py:generate_media_candidates]
- GET /api/media/{media_id}/candidates -> list[CandidateResponse] [candidates.py:list_media_candidates]
- GET /api/candidates/{candidate_id} -> CandidateResponse [candidates.py:get_candidate]
- PATCH /api/candidates/{candidate_id} -> CandidateResponse [candidates.py:update_candidate]
- POST /api/candidates/{candidate_id}/captions -> CandidateCaptionsResponse [renders.py:generate_captions_endpoint]
- GET /api/candidates/{candidate_id}/captions -> CandidateCaptionsResponse [renders.py:get_captions_endpoint]
- POST /api/candidates/{candidate_id}/render -> JobResponse [renders.py:submit_render_job]
- GET /api/renders/{render_id} -> RenderResponse [renders.py:get_render_endpoint]
- GET /api/renders/{render_id}/stream -> StreamingResponse / FileResponse [renders.py:stream_rendered_clip]
- GET /api/candidates/{candidate_id}/artifacts -> CandidateArtifactsResponse [renders.py:list_artifacts_endpoint]

## Invariants
- No heavy media processing in request handlers: audio extraction, transcription, rendering, and ingestion are dispatched to the background job manager [projects.py, transcription.py, renders.py, jobs.py]
- Truthful health reporting: /health reports 'degraded' if the background job worker task is not running [health.py:get_health]
- Strict file validation: uploaded media files must pass magic byte container validation [projects.py:upload_media]
- HTTP range request compliance: audio and video streaming endpoints support RFC 7233 partial content requests [media.py:stream_media_file, renders.py:stream_rendered_clip]

## Side Effects
- Queries and mutates SQLite database records via ProjectRepository, CandidateRepository, and RenderRepository
- Streams media chunks and writes uploaded files to local disk under DATA_DIR
- Submits and cancels asynchronous background jobs in JobManager

## Verification
- Run: `pytest backend/tests`
