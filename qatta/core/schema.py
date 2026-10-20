"""Laqta core data schema (Pydantic v2, strict validation).

All pipeline stages read and write through these models, serialized to a
single ``qatta_manifest.json`` per project. This is the only persisted
pipeline state for the core package, which is what makes stage caching
deterministic (a stage is "done" exactly when its artifacts are recorded in
the manifest and listed in ``completed_stages``).

Design rules enforced here (agent architectural rules):
- LLMs never output timestamps. Transcript material is segmented into
  ``AtomicUtterance`` objects (``U_0001`` ... ) bounded by real VAD pauses;
  clip candidates reference ``start_u_id`` / ``end_u_id`` only.
- Every timed field is integer milliseconds (``_*_ms``) to avoid float
  drift; the derived ``duration_sec`` is kept consistent by validators.
- Extra fields are forbidden so a typo in a stage cannot silently corrupt
  the manifest.
"""

import itertools
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Atomic utterance identity: U_ + at least 4 digits (U_0001 ...).
U_ID_PATTERN = re.compile(r"^U_\d{4,}$")

ClipArchetype = Literal["STORY", "TACTICAL_INSIGHT", "HOT_TAKE"]
OverlayType = Literal["STOCK_VIDEO", "TEXT_CARD", "PUNCH_IN_ZOOM"]


class _StrictModel(BaseModel):
    """Common strict config: no unknown fields, validated assignments."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class WordToken(_StrictModel):
    """A single word with REAL measured timing (from Whisper/VAD, never LLM)."""

    word: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    is_latin: bool = Field(
        description=(
            "True when the token is Latin/ASCII (Arablish code-switching). "
            "Caption rendering uses this to wrap tokens in FSI/PDI isolates."
        )
    )

    @model_validator(mode="after")
    def _check_order(self) -> "WordToken":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"WordToken '{self.word}': end_ms ({self.end_ms}) must be "
                f"greater than start_ms ({self.start_ms})."
            )
        return self


class AtomicUtterance(_StrictModel):
    """One utterance bounded by real VAD pauses.

    This is the unit of selection for both human editors and LLM passes:
    models may ONLY reference ``u_id`` values, never raw timestamps.
    """

    u_id: str = Field(pattern=U_ID_PATTERN.pattern)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker: str = Field(default="SPEAKER_00", min_length=1)
    text: str = Field(min_length=1)
    audio_rms_norm: float = Field(default=0.0, ge=0.0, le=1.0)
    # Stage s03 analytic features (None until s03_multimodal ran):
    pitch_variance: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Normalized pitch variance within the utterance — an "
            "excitement/emphasis PROXY, not a claim of real prosody "
            "analysis beyond the deterministic estimator documented in "
            "the stage."
        ),
    )
    silence_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of the utterance span under the silence RMS threshold.",
    )
    pause_after_ms: int = Field(default=0, ge=0)
    words: list[WordToken] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_order(self) -> "AtomicUtterance":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"{self.u_id}: end_ms ({self.end_ms}) must be greater than "
                f"start_ms ({self.start_ms})."
            )
        return self

    @model_validator(mode="after")
    def _check_words_monotonic(self) -> "AtomicUtterance":
        words = self.words
        for prev, cur in itertools.pairwise(words):
            if cur.start_ms < prev.start_ms:
                raise ValueError(
                    f"{self.u_id}: word tokens must be time-ordered "
                    f"({prev.word} at {prev.start_ms} ms before {cur.word} "
                    f"at {cur.start_ms} ms)."
                )
        return self

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class VetoGates(_StrictModel):
    """Deterministic hard gates evaluated BEFORE any scoring.

    A clip failing any gate is vetoed and never scored — qualitative and
    monetization safety outrank clip potential.
    """

    dangling_context: bool = Field(
        description="True when the clip starts/ends mid-sentence or mid-setup."
    )
    clean_audio_boundaries: bool = Field(
        description="True when cut boundaries sit inside real VAD pauses."
    )
    crosstalk_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of clip audio that is crosstalk/overlap speech.",
    )
    passed_all: bool = Field(description="True only when every gate passed.")
    rejection_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_reason_when_vetoed(self) -> "VetoGates":
        if not self.passed_all and not self.rejection_reason:
            raise ValueError("VetoGates: a failed gate must carry a rejection_reason.")
        return self


class CPSBreakdown(_StrictModel):
    """Evidence-based Clip Potential Scoring breakdown (deterministic).

    Components are computed from measurable features with disclosed
    evidence. This is NOT a virality prediction; scores rank candidates
    only.
    """

    total_score: float = Field(ge=0.0)
    archetype: ClipArchetype
    standalone_clarity: float = Field(ge=0.0)
    hook_strength: float = Field(ge=0.0)
    story_payoff: float = Field(ge=0.0)
    value_originality: float = Field(ge=0.0)
    audio_dynamics: float = Field(ge=0.0)
    visual_composition: float | None = Field(default=None, ge=0.0)
    boundary_precision: float = Field(ge=0.0)


class HookRemixVariant(_StrictModel):
    """Optional hook-first remix of a candidate's opening."""

    enabled: bool
    hook_u_id: str | None = Field(default=None, pattern=U_ID_PATTERN.pattern)
    source_start_ms: int | None = Field(default=None, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    ai_bridge_text: str | None = Field(default=None)
    context_preserved: bool = True

    @model_validator(mode="after")
    def _check_enabled_payload(self) -> "HookRemixVariant":
        if self.enabled:
            missing = [
                name
                for name in ("hook_u_id", "source_start_ms", "source_end_ms")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    f"HookRemixVariant: an enabled hook remix requires {', '.join(missing)}."
                )
        return self


class BrollCue(_StrictModel):
    """A timed B-roll/overlay suggestion inside a clip."""

    trigger_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    search_query: str = Field(min_length=1)
    overlay_type: OverlayType
    asset_path: str | None = Field(default=None)


class MonetizationMeta(_StrictModel):
    """Monetization safety metadata (YouTube YPP context)."""

    visual_transformation_ratio: float = Field(ge=0.0, le=1.0)
    seamless_loop_score: float = Field(ge=0.0, le=1.0)
    pinned_comment_cta: str = Field(min_length=1)
    curiosity_titles: list[str] = Field(default_factory=list)
    ypp_safe: bool


class ClipCandidate(_StrictModel):
    """A candidate short, grounded in utterance IDs and real timestamps."""

    clip_id: str = Field(min_length=1)
    start_u_id: str = Field(pattern=U_ID_PATTERN.pattern)
    end_u_id: str = Field(pattern=U_ID_PATTERN.pattern)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    duration_sec: float = Field(gt=0)
    veto_gates: VetoGates
    cps: CPSBreakdown
    hook_remix: HookRemixVariant
    broll_cues: list[BrollCue] = Field(default_factory=list)
    monetization: MonetizationMeta | None = None
    # LLM drafts (stage s04) persist BELOW the final MonetizationMeta
    # object, because visual_transformation_ratio / seamless_loop_score /
    # ypp_safe are NOT measurable by stages s03–s05 and are left to a
    # later verified stage. Storing drafts here avoids fabricating them.
    draft_pinned_comment_cta: str | None = Field(default=None)
    draft_curiosity_titles: list[str] = Field(default_factory=list)
    evidence_log: list[str] = Field(default_factory=list)
    rendered_paths: dict[str, str] = Field(default_factory=dict)
    # Section media (stage s05b_section_fetch, YouTube subs-first flow only):
    # the winning clip's small downloaded video + its 16 kHz audio, and the
    # absolute source_ms that corresponds to t=0 inside the section file.
    # None until s05b ran; plain local-file sources keep the full media.
    section_media_path: str | None = Field(default=None)
    section_audio_16k_path: str | None = Field(default=None)
    section_start_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_span(self) -> "ClipCandidate":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"ClipCandidate '{self.clip_id}': end_ms ({self.end_ms}) must "
                f"be greater than start_ms ({self.start_ms})."
            )
        derived = (self.end_ms - self.start_ms) / 1000.0
        if not math.isclose(self.duration_sec, derived, abs_tol=0.051):
            raise ValueError(
                f"ClipCandidate '{self.clip_id}': duration_sec "
                f"({self.duration_sec}) must equal (end_ms - start_ms) / 1000 "
                f"= {derived:.3f} s."
            )
        if self.start_u_id == self.end_u_id:
            raise ValueError(
                f"ClipCandidate '{self.clip_id}': start_u_id and end_u_id "
                "must reference different utterances."
            )
        return self


class QattaManifest(_StrictModel):
    """The single source of truth for one project's pipeline state."""

    schema_version: int = Field(default=1, ge=1)
    project_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_url: str | None = None
    audio_16k_path: str | None = None
    # How Pass 1 materialized the utterances: "whisper_local",
    # "groq_api", or "youtube_subs_first" (captions pulled from the
    # platform; Pass 2 still re-times words locally on winning clips).
    transcript_source: str | None = None
    # Absolute path of the YouTube caption (VTT) file when
    # transcript_source == "youtube_subs_first".
    subtitle_path: str | None = None
    video_width: int | None = Field(default=None, ge=0)
    video_height: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, gt=0)
    duration_sec: float = Field(gt=0)
    language_profile: str = Field(default="ar-EG-mixed", min_length=1)
    completed_stages: list[str] = Field(default_factory=list)
    atomic_utterances: list[AtomicUtterance] = Field(default_factory=list)
    candidates: list[ClipCandidate] = Field(default_factory=list)
    scene_cuts_ms: list[int] = Field(
        default_factory=list,
        description=(
            "Scene cut timestamps (ms) recorded by stage s03_multimodal "
            "via scenedetect ContentDetector, or the documented ffmpeg "
            "frame-difference fallback when scenedetect is unavailable."
        ),
    )
    # MEASURED per-stage wall time (ms), written by the orchestrator after
    # each executed stage. Honest benchmark data — no derived claims.
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_unique(self) -> "QattaManifest":
        stages = self.completed_stages
        if len(stages) != len(set(stages)):
            raise ValueError(f"QattaManifest: completed_stages contains duplicates ({stages}).")
        utterance_ids = [u.u_id for u in self.atomic_utterances]
        if len(set(utterance_ids)) != len(utterance_ids):
            raise ValueError("QattaManifest: atomic_utterances contain duplicate u_ids.")
        clip_ids = [c.clip_id for c in self.candidates]
        if len(set(clip_ids)) != len(clip_ids):
            raise ValueError("QattaManifest: candidates contain duplicate clip_ids.")
        return self

    def utterance_index(self) -> dict[str, AtomicUtterance]:
        """Map u_id -> AtomicUtterance for clip grounding lookups."""
        return {u.u_id: u for u in self.atomic_utterances}
