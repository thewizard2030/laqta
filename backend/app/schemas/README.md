# Schemas

## Overview
Pydantic v2 data models and type definitions for HTTP requests, API responses, configuration payloads, and domain entities.

## Interface
- app.schemas.capabilities:CapabilitiesResponse, BinaryCapability, FFmpegCapability, HardwareCapabilities, AsrCapabilities, LlmCapabilities, StorageCapabilities, UrlIngestionCapabilities
- app.schemas.health:HealthResponse
- app.schemas.projects:ProjectCreate, ProjectResponse, ProjectUpdate
- app.schemas.media:MediaAssetResponse, UrlIngestRequest, UrlIngestAcceptedResponse
- app.schemas.jobs:JobCreateRequest, JobResponse, JobStatus, JobType, INDETERMINATE_STAGE_NAMES
- app.schemas.transcription:TranscriptionRequest, TranscriptResponse, TranscriptSegment, WordTiming, ProviderCapabilityInfo
- app.schemas.candidates:CandidateGenerationRequest, CandidateResponse, CandidateUpdateRequest, CandidateStatus, ComponentScoreSchema, ScoringWeightsRequest, SCORING_NOTICE
- app.schemas.captions:CaptionStyleSettings, CaptionGenerationRequest, CandidateCaptionsResponse, CandidateArtifactsResponse, CaptionArtifact
- app.schemas.rendering:RenderRequest, RenderResponse, RenderJobRequest
- app.schemas.ranking:LLMRankingResponse, LLMRankedCandidate
- app.schemas.settings:SettingsResponse, SettingsUpdateRequest, VerifyKeyRequest, VerifyKeyResponse, ClearCacheResponse

## Invariants
- Pydantic v2 validation rules enforce input sanitization and value boundaries across all API endpoints
- Explicit disclaimers: SCORING_NOTICE codifies that CPS is a heuristic rather than virality prediction

## Side Effects
- None (pure data validation schemas)

## Verification
- Run: `pytest backend/tests`
