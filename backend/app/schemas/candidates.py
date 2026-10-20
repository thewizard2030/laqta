"""Pydantic schemas for clip candidate generation and API responses (FR-04/FR-05)."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

SCORING_NOTICE = (
    "Clip Potential Score (CPS) is a heuristic editorial quality score (0-100), "
    "not a probability of views or virality. Weights are configuration, pending "
    "human-rating evaluation (PRD §8)."
)


class CandidateStatus(StrEnum):
    """Persisted candidate review states."""

    SUGGESTED = "suggested"
    PENALIZED = "penalized"
    REJECTED = "rejected"


class ScoringWeightsRequest(BaseModel):
    """Explicit CPS weights (all keys optional; missing keys keep defaults)."""

    self_contained: float = Field(default=0.25, ge=0.0, le=1.0)
    hook: float = Field(default=0.20, ge=0.0, le=1.0)
    completion: float = Field(default=0.20, ge=0.0, le=1.0)
    novelty_emotion: float = Field(default=0.10, ge=0.0, le=1.0)
    clarity: float = Field(default=0.10, ge=0.0, le=1.0)
    visual: float = Field(default=0.05, ge=0.0, le=1.0)
    boundary: float = Field(default=0.10, ge=0.0, le=1.0)


class CandidateGenerationRequest(BaseModel):
    """Request payload to (re)generate candidates for a media asset."""

    min_duration_s: float = Field(
        default=30.0,
        ge=1.0,
        le=3600.0,
        description="Minimum clip duration in seconds",
    )
    max_duration_s: float = Field(
        default=55.0,
        ge=1.0,
        le=3600.0,
        description="Maximum clip duration in seconds",
    )
    weights: ScoringWeightsRequest = Field(default_factory=ScoringWeightsRequest)
    max_overlap_iou: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Candidates with IoU overlap above this are de-duplicated",
    )
    keep_threshold: float = Field(
        default=25.0,
        ge=0.0,
        le=100.0,
        description="Candidates scoring below this CPS are marked rejected (not persisted)",
    )
    suggested_threshold: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        description="Candidates scoring at least this CPS are marked 'suggested'",
    )

    @model_validator(mode="after")
    def validate_durations(self) -> "CandidateGenerationRequest":
        if self.max_duration_s <= self.min_duration_s:
            raise ValueError(
                f"max_duration_s ({self.max_duration_s}) must be strictly greater than "
                f"min_duration_s ({self.min_duration_s})."
            )
        if self.keep_threshold > self.suggested_threshold:
            raise ValueError("keep_threshold must not exceed suggested_threshold.")
        return self


class ComponentScoreSchema(BaseModel):
    """One CPS component with its availability state and explanation."""

    key: str
    label: str
    score: float | None = Field(
        default=None, description="0-100 component score, null when unavailable"
    )
    nominal_weight: float
    effective_weight: float | None = Field(
        default=None,
        description="Weight after renormalization over available components",
    )
    available: bool
    rationale: str


class CandidateResponse(BaseModel):
    """Persisted clip candidate with explainable scoring (no LLM involved)."""

    id: str
    media_id: str
    transcript_id: str
    start_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    duration_ms: int
    status: CandidateStatus
    cps: float = Field(..., ge=0.0, le=100.0)
    cps_interpretation: str = SCORING_NOTICE
    title: str | None = None
    hook: str | None = None
    transcript_span_ids: list[str]
    feature_scores: list[ComponentScoreSchema]
    unavailable_features: list[str]
    rationale: list[str]
    created_at: str
    boundary_edited: bool = Field(
        default=False,
        description="True when the user manually edited boundaries; scores were re-derived "
        "deterministically for the edited span (never invented)",
    )


class CandidateGenerationResponse(BaseModel):
    """Result of a generation run: persisted candidates plus honest warnings."""

    media_id: str
    transcript_id: str
    candidates: list[CandidateResponse]
    warnings: list[str]
    scoring_notice: str = SCORING_NOTICE
    ranking_method: str = Field(
        default="baseline",
        description="'baseline' (deterministic CPS order) or 'llm_reranked' (optional provider)",
    )
    ranking_provider: str | None = Field(
        default=None,
        description="Provider name when an LLM rerank was attempted; never contains secrets",
    )


class CandidateUpdateRequest(BaseModel):
    """Manual boundary/title/hook edit (FR-05 review workflow, user journey step 10).

    Times are in milliseconds and are validated in Python against the media
    duration and the configured duration bounds; no model/LLM input is trusted
    for cut boundaries.
    """

    start_ms: int = Field(..., ge=0, description="New clip start in milliseconds")
    end_ms: int = Field(..., gt=0, description="New clip end in milliseconds")
    title: str | None = Field(default=None, max_length=120)
    hook: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_order(self) -> "CandidateUpdateRequest":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})."
            )
        return self
