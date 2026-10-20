"""Database record representations."""

from dataclasses import dataclass


@dataclass
class ProjectRecord:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass
class MediaAssetRecord:
    id: str
    project_id: str
    safe_path: str
    original_name: str
    size_bytes: int
    duration_ms: int
    width: int
    height: int
    video_codec: str
    audio_codec: str
    status: str
    created_at: str


@dataclass
class JobRecord:
    id: str
    project_id: str
    media_id: str | None
    type: str
    status: str
    stage: str
    progress: float
    error_code: str | None
    error_message: str | None
    config_json: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass
class TranscriptRecord:
    id: str
    media_id: str
    language: str
    provider: str
    model: str
    status: str
    text: str
    segments_json: str
    word_timestamps_available: bool
    timing_granularity: str
    created_at: str


@dataclass
class CandidateRecord:
    id: str
    media_id: str
    transcript_id: str
    start_ms: int
    end_ms: int
    transcript_span_ids_json: str
    title: str | None
    hook: str | None
    rationale_json: str
    feature_scores_json: str
    cps: float
    status: str
    created_at: str


@dataclass
class RenderedClipRecord:
    id: str
    candidate_id: str
    media_id: str
    output_path: str
    width: int
    height: int
    duration_ms: int
    size_bytes: int
    video_probe_json: str
    render_config_json: str
    created_at: str
