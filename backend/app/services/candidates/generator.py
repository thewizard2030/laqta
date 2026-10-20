"""Deterministic candidate range generation (PRD §5 FR-04, §8, §11 Gate C).

Rules enforced here:
- Candidates are windows built ONLY from existing transcript structure:
  segment boundaries, sentence-ending words, and observable pauses between
  segments. No timestamps are invented by a model.
- Every boundary references transcript evidence: segment IDs and, when word
  timings exist, per-word IDs ("seg_0001#w3").
- With word-level timestamps, candidate starts/ends land on word boundaries;
  words are never cut unless the window was clamped to the media duration
  (disclosed in the rationale as a penalty).
- Without word timestamps, boundaries use segment ends only and the lower
  precision is disclosed in the rationale/limitations.
- All ranges are clamped to the media duration; empty or invalid ranges are
  rejected before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.scoring.baseline import (
    CPS_INTERPRETATION,
    ScoringConfig,
    jaccard_text_similarity,
    score_candidate,
)


class CandidateGenerationError(ValueError):
    """Raised for structurally unusable transcript input (clear error, no crash)."""


@dataclass
class BoundaryUnit:
    """A minimal span (sentence when words exist, else a full segment)."""

    start_ms: int
    end_ms: int
    source_end_ms: int  # end before media-duration clamping
    text: str
    seg_id: str
    word_ids: list[str]
    starts_mid_segment: bool
    ends_mid_segment: bool
    ends_sentence: bool
    word_count: int


@dataclass
class CandidateDraft:
    """A validated candidate window with evidence, before scoring/persistence."""

    start_ms: int
    end_ms: int
    units: list[BoundaryUnit]
    span_ids: list[str]
    text: str
    silence_fraction: float
    truncated: bool
    cuts_speech: bool
    starts_mid_segment: bool
    ends_mid_segment: bool
    ends_sentence: bool
    low_boundary_precision: bool


@dataclass
class ScoredCandidate:
    """Final scoring output for one candidate draft."""

    candidate: CandidateDraft
    cps: float
    unavailable_keys: list[str]
    components: dict[str, Any]
    rationale: list[str]


@dataclass
class CandidateGenerationResult:
    """Deterministic generation output + honest warnings about what happened."""

    candidates: list[ScoredCandidate]
    warnings: list[str] = field(default_factory=list)


TERMINAL_CHARS: tuple[str, ...] = tuple(".!?…؟ ؗ")


def make_candidate_id(transcript_id: str, start_ms: int, end_ms: int) -> str:
    """Deterministic candidate ID derived only from evidence coordinates."""
    digest = sha256(f"{transcript_id}:{start_ms}:{end_ms}".encode()).hexdigest()[:12]
    return f"cand_{digest}"


def _seconds_to_ms(value: float) -> int:
    return max(0, int(round(value * 1000.0)))


def _unit_ends_sentence(text: str) -> bool:
    return text.strip().endswith(TERMINAL_CHARS)


def build_boundary_units(
    segments: list[TranscriptSegment],
    word_timestamps_available: bool,
    media_duration_ms: int,
    warnings: list[str],
) -> list[BoundaryUnit]:
    """Split segments into sentence-level units using tokens that exist.

    With word timings, a sentence boundary is recognised at a word whose text
    carries terminal punctuation; unit times derive from that word's own
    start/end. Without word timings, each segment is one unit (lower
    precision, disclosed).
    """
    units: list[BoundaryUnit] = []
    for seg in segments:
        if seg.end < seg.start:
            warnings.append(
                f"Skipped invalid segment '{seg.id}' (end {seg.end}s < start {seg.start}s)."
            )
            continue
        if not seg.text.strip() and not (seg.words and word_timestamps_available):
            warnings.append(f"Skipped empty-text segment '{seg.id}'.")
            continue
        seg_start = _seconds_to_ms(seg.start)
        seg_source_end = _seconds_to_ms(seg.end)
        seg_end = min(seg_source_end, max(seg_start, media_duration_ms))
        if seg_end - seg_start <= 0:
            warnings.append(
                f"Skipped zero/invalid-length segment '{seg.id}' after duration clamping "
                "(starts at or beyond media duration)."
            )
            continue

        words = seg.words if word_timestamps_available else None
        if words:
            words = [w for w in words if w.word.strip() and w.end >= w.start]
        if words:
            group: list[tuple[int, WordTiming]] = []
            for index, word in enumerate(words):
                group.append((index, word))
                last_char = word.word.strip()[-1]
                is_segment_last = index == len(words) - 1
                if last_char in TERMINAL_CHARS or is_segment_last:
                    word_ids = [f"{seg.id}#w{w_idx}" for w_idx, _ in group]
                    text = " ".join(w.word for _, w in group)
                    group_end = _seconds_to_ms(group[-1][1].end)
                    units.append(
                        BoundaryUnit(
                            start_ms=_seconds_to_ms(group[0][1].start),
                            end_ms=min(group_end, seg_end),
                            source_end_ms=group_end,
                            text=text,
                            seg_id=seg.id,
                            word_ids=word_ids,
                            starts_mid_segment=group[0][0] != 0,
                            ends_mid_segment=group[-1][0] != len(words) - 1,
                            ends_sentence=last_char in TERMINAL_CHARS,
                            word_count=len(group),
                        )
                    )
                    group = []
        else:
            if word_timestamps_available and not seg.words:
                warnings.append(
                    f"Segment '{seg.id}' has no word timings despite word-level request; "
                    "falling back to segment-boundary precision."
                )
            units.append(
                BoundaryUnit(
                    start_ms=seg_start,
                    end_ms=seg_end,
                    source_end_ms=seg_source_end,
                    text=seg.text.strip(),
                    seg_id=seg.id,
                    word_ids=[],
                    starts_mid_segment=False,
                    ends_mid_segment=False,
                    ends_sentence=_unit_ends_sentence(seg.text),
                    word_count=len(seg.text.split()),
                )
            )
    units.sort(key=lambda u: (u.start_ms, u.end_ms, u.end_ms - u.start_ms))
    return units


def _generate_windows(
    units: list[BoundaryUnit],
    config: ScoringConfig,
    media_duration_ms: int,
    warnings: list[str],
) -> list[CandidateDraft]:
    """Slide sentence/segment-anchored windows within the configured duration range."""
    min_ms = int(config.min_duration_s * 1000)
    max_ms = int(config.max_duration_s * 1000)
    drafts: list[CandidateDraft] = []
    clamped_any = False
    for i in range(len(units)):
        start = units[i].start_ms
        for j in range(i, len(units)):
            duration = units[j].end_ms - start
            if duration < min_ms:
                continue
            if duration > max_ms:
                # The very first fit already overshoots the maximum; no window
                # starting at unit i can satisfy the configured duration bounds.
                break
            group = units[i : j + 1]
            draft = _make_draft(start, units[j].end_ms, group, media_duration_ms)
            clamped_any = clamped_any or draft.truncated
            drafts.append(draft)
            # Second variant: extend one further boundary while still in range;
            # score-based dedup later keeps the better duration fit.
            if j + 1 < len(units) and units[j + 1].end_ms - start <= max_ms:
                extended = _make_draft(
                    start, units[j + 1].end_ms, units[i : j + 2], media_duration_ms
                )
                drafts.append(extended)
                clamped_any = clamped_any or extended.truncated
            break
    if clamped_any:
        warnings.append(
            "Some windows were clamped to the media duration and their final "
            "speech may be cut; disclosed in candidate rationale."
        )
    return drafts


def _make_draft(
    start_ms: int,
    end_ms: int,
    units: list[BoundaryUnit],
    media_duration_ms: int,
) -> CandidateDraft:
    """Assemble one validated draft; clamp to duration and evaluate cut risks."""
    clipped_end = min(end_ms, media_duration_ms)
    fitting_units = [u for u in units if u.start_ms < clipped_end]
    if not fitting_units:
        return CandidateDraft(
            start_ms=start_ms,
            end_ms=start_ms,
            units=[],
            span_ids=[],
            text="",
            silence_fraction=1.0,
            truncated=False,
            cuts_speech=False,
            starts_mid_segment=False,
            ends_mid_segment=False,
            ends_sentence=False,
            low_boundary_precision=True,
        )

    text = " ".join(u.text for u in fitting_units if u.text)
    cut_unit = any(
        u.source_end_ms > clipped_end and u.start_ms < clipped_end for u in fitting_units
    )
    truncated = cut_unit

    gaps = 0
    previous_end = fitting_units[0].end_ms
    for u in fitting_units[1:]:
        gap = u.start_ms - previous_end
        if gap > 0:
            gaps += gap
        previous_end = max(previous_end, u.end_ms)
    window_duration = max(1, clipped_end - start_ms)
    silence_fraction = min(1.0, gaps / window_duration)

    span_ids: list[str] = []
    for u in fitting_units:
        span_ids.append(u.seg_id)
        span_ids.extend(u.word_ids)

    ends_unit = fitting_units[-1]
    starts_unit = fitting_units[0]

    return CandidateDraft(
        start_ms=start_ms,
        end_ms=clipped_end,
        units=fitting_units,
        span_ids=span_ids,
        text=text,
        silence_fraction=silence_fraction,
        truncated=truncated,
        cuts_speech=cut_unit,
        starts_mid_segment=starts_unit.starts_mid_segment,
        ends_mid_segment=ends_unit.ends_mid_segment,
        ends_sentence=ends_unit.ends_sentence,
        low_boundary_precision=not any(u.word_ids for u in fitting_units),
    )


def _iou(a: CandidateDraft, b: CandidateDraft) -> float:
    intersection = max(0, min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms))
    union = max(a.end_ms, b.end_ms) - min(a.start_ms, b.start_ms)
    return intersection / union if union > 0 else 0.0


def _dedup(
    scored: list[ScoredCandidate], config: ScoringConfig
) -> tuple[list[ScoredCandidate], int]:
    """Keep the best candidate: higher CPS, tie-break earlier start then shorter end.

    Overlap (IoU) and near-duplicate text are both suppressed deterministically.
    """
    ordered = sorted(scored, key=lambda s: (-s.cps, s.candidate.start_ms, s.candidate.end_ms))
    kept: list[ScoredCandidate] = []
    dropped = 0
    for cand in ordered:
        duplicate: bool = False
        for keeper in kept:
            if _iou(cand.candidate, keeper.candidate) > config.max_overlap_iou:
                duplicate = True
                break
            if (
                jaccard_text_similarity(cand.candidate.text, keeper.candidate.text)
                > config.max_text_jaccard
            ):
                duplicate = True
                break
        if duplicate:
            dropped += 1
        else:
            kept.append(cand)
    kept.sort(key=lambda s: (-s.cps, s.candidate.start_ms, s.candidate.end_ms))
    return kept, dropped


def generate_candidates(
    segments: list[TranscriptSegment],
    media_duration_ms: int,
    config: ScoringConfig | None = None,
    word_probabilities_by_segment: dict[str, list[float]] | None = None,
    avg_logprob_by_segment: dict[str, list[float]] | None = None,
) -> CandidateGenerationResult:
    """Generate and score candidate ranges deterministically.

    Raises:
        CandidateGenerationError: structurally unusable input (empty
            transcript, negative duration, no valid segments). Callers turn
            this into a clear API error; the rest of the app keeps working.
    """
    cfg = config or ScoringConfig()
    warnings: list[str] = []
    if media_duration_ms <= 0:
        raise CandidateGenerationError("Media duration must be positive to bound candidates.")
    if not segments:
        raise CandidateGenerationError(
            "Transcript has no segments; candidate generation requires transcript content."
        )

    words_available = any(seg.words for seg in segments)
    units = build_boundary_units(segments, words_available, media_duration_ms, warnings)
    if not units:
        raise CandidateGenerationError(
            "No valid transcript segments survived validation; cannot generate candidates."
        )

    drafts = _generate_windows(units, cfg, media_duration_ms, warnings)
    scored: list[ScoredCandidate] = []
    for draft in drafts:
        word_probs: list[float] | None = None
        avg_lps: list[float] | None = None
        if word_probabilities_by_segment:
            probs = [
                p
                for u in draft.units
                for p in (word_probabilities_by_segment.get(u.seg_id) or [])
                if p is not None
            ]
            word_probs = probs or None
        if avg_logprob_by_segment:
            lps = [
                lp
                for u in draft.units
                for lp in (avg_logprob_by_segment.get(u.seg_id) or [])
                if lp is not None
            ]
            avg_lps = lps or None
        result = score_candidate(
            duration_ms=draft.end_ms - draft.start_ms,
            text=draft.text,
            silence_fraction=draft.silence_fraction,
            truncated=draft.truncated,
            cuts_speech=draft.cuts_speech,
            starts_mid_segment=draft.starts_mid_segment,
            ends_mid_segment=draft.ends_mid_segment,
            ends_sentence=draft.ends_sentence,
            first_unit_text=draft.units[0].text,
            first_unit_word_count=draft.units[0].word_count,
            word_probabilities=word_probs,
            avg_logprobs=avg_lps,
            low_boundary_precision=draft.low_boundary_precision,
            config=cfg,
        )
        scored.append(
            ScoredCandidate(
                candidate=draft,
                cps=result.cps,
                unavailable_keys=result.unavailable_keys,
                components=result.components,
                rationale=result.rationale,
            )
        )

    kept, dropped = _dedup(scored, cfg)
    if dropped:
        warnings.append(
            f"Dropped {dropped} candidate(s) due to overlap IoU > {cfg.max_overlap_iou:.2f} "
            "or near-duplicate text."
        )

    result_list = [s for s in kept if s.cps >= cfg.keep_threshold]
    rejected = len(kept) - len(result_list)
    if rejected:
        warnings.append(
            f"{rejected} candidate(s) below the keep threshold ({cfg.keep_threshold:.1f}) "
            "were marked rejected."
        )
    if not result_list:
        warnings.append(
            "No candidate passed the configured duration/scoring rules. Check transcript "
            "length, duration bounds, and thresholds."
        )

    return CandidateGenerationResult(candidates=result_list, warnings=warnings)


CPS_NOTICE = CPS_INTERPRETATION
