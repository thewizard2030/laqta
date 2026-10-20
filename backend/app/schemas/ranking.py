"""Strict Pydantic validation models for LLM reranker output (PRD §5 FR-05/FR-11).

The LLM is treated as an unreliable, partially adversarial component:
- Its raw text is parsed as JSON; anything that does not parse is rejected.
- Its output must reference ONLY candidate/evidence IDs that were offered in
  the prompt (allow-list enforcement happens in the ranker; schemas enforce
  shape and size here).
- Suggested titles/hooks/rationales are bounded display strings: control
  characters are stripped and lengths are capped so nothing can smuggle UI
  markup or overflow storage.
- The schema deliberately contains NO timestamp fields. The LLM never supplies
  cut boundaries; start/end times are owned by the deterministic generator.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Control characters (except tab/newline handled below) cannot be displayed
# safely and are a common injection vector into terminal/UI rendering.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_RANKED_ITEMS = 50
MAX_EVIDENCE_IDS = 200
MAX_RATIONALE_CHARS = 1_000
MAX_TITLE_CHARS = 120
MAX_HOOK_CHARS = 200
MAX_RANKING_NOTE_CHARS = 500


def _clean_text(value: str, max_chars: int) -> str:
    """Strip control characters and cap length for any LLM-supplied display text."""
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    return cleaned[:max_chars]


class LLMRankedCandidate(BaseModel):
    """One validated rerank verdict from the model for a known candidate ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=MAX_RATIONALE_CHARS)
    suggested_title: str | None = Field(default=None, max_length=MAX_TITLE_CHARS)
    suggested_hook: str | None = Field(default=None, max_length=MAX_HOOK_CHARS)
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)

    @field_validator("candidate_id", "rationale")
    @classmethod
    def _no_control_chars(cls, v: str) -> str:
        cleaned = _clean_text(v, MAX_RATIONALE_CHARS)
        if not cleaned:
            raise ValueError("empty after control-character sanitization")
        return cleaned

    @field_validator("suggested_title")
    @classmethod
    def _clean_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _clean_text(v, MAX_TITLE_CHARS)
        return cleaned or None

    @field_validator("suggested_hook")
    @classmethod
    def _clean_hook(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _clean_text(v, MAX_HOOK_CHARS)
        return cleaned or None

    @field_validator("evidence_ids")
    @classmethod
    def _clean_evidence_ids(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError("evidence_ids entries must be strings")
            item = _clean_text(item, 128)
            if item:
                cleaned.append(item)
        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique = [e for e in cleaned if not (e in seen or seen.add(e))]
        return unique


class LLMRankingResponse(BaseModel):
    """Top-level validated rerank response.

    ``ranking`` order IS the model's proposed order (best first). Duplicated
    candidate IDs are rejected outright: a duplicated ID is a sign of a
    malformed or manipulated response.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ranking: list[LLMRankedCandidate] = Field(min_length=1, max_length=MAX_RANKED_ITEMS)
    note: str | None = Field(default=None, max_length=MAX_RANKING_NOTE_CHARS)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _clean_text(v, MAX_RANKING_NOTE_CHARS) or None

    @field_validator("ranking")
    @classmethod
    def _no_duplicate_ids(cls, v: list[LLMRankedCandidate]) -> list[LLMRankedCandidate]:
        ids = [item.candidate_id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate_id in ranking")
        return v
