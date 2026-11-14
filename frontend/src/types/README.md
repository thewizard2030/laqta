# Types

## Overview
Core TypeScript domain models and API schema interfaces matching the FastAPI backend Pydantic models.

## Interface
- capabilities.ts: CapabilitiesResponse, BinaryCapability, FFmpegCapability - Backend runtime capability schemas
- health.ts: HealthResponse - System health and heartbeat schema
- jobs.ts: JobResponse, JobStatus, JobType - Asynchronous background job schemas
- media.ts: MediaAsset - Video/audio source asset metadata schema
- projects.ts: Project, CreateProjectPayload - Project workspace schemas
- candidates.ts: Candidate, CandidateStatus, ComponentScore - Candidate clip and scoring schemas
- transcription.ts: TranscriptResponse, TranscriptSegment, WordTiming - Speech transcription schemas
- rendering.ts: RenderRequest, RenderedClipResponse, CaptionStyleSettings - Vertical rendering schemas
- settings.ts: SettingsResponse, SettingsUpdateRequest - Application configuration and BYOK schemas

## Invariants
- Interfaces mirror backend schemas without fabricating unsupported fields

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
