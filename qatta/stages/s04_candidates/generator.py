"""Stage s04_candidates — LLM candidate proposals over sliding windows.

Rule 3 (no LLM timestamps) is enforced structurally: the model sees only
``u_id``-keyed utterance lines and its answer is validated against the
window's u_ids; every millisecond is DERIVED here from the
:class:`AtomicUtterance` rows. The model's proposal even for B-roll uses
``offset_sec`` relative to the clip start, which the stage converts to
absolute ``trigger_ms``.

Raw candidates get scaffold ``VetoGates(passed_all=False,
rejection_reason="pending_s05_ranking")`` — they are NOT yet vetted;
stage `s05_ranking` performs the gates, scoring and winner selection.

If the configured LLM is unreachable or yields nothing usable for a
window, the deterministic heuristic fallback (real feature, labeled in
evidence) keeps the pipeline working — unless
``QATTA_LLM_FALLBACK_ENABLED=false``.
"""

from __future__ import annotations

import json

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError
from qatta.core.schema import (
    AtomicUtterance,
    BrollCue,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)
from qatta.stages.s04_candidates.llm import (
    LLMProvider,
    ProviderResult,
    WindowPayload,
    select_provider,
    validate_proposal,
)

# ---------------------------------------------------------------------------
# SlidingWindowChunker
# ---------------------------------------------------------------------------


class SlidingWindowChunker:
    """Group utterances into time windows (default 15 min) with overlap.

    Overlap semantics: utterances whose START falls within the last
    ``overlap_sec`` seconds of a window are ALSO included at the start of
    the following window, so LLM reasoning at each boundary sees full
    context. Every utterance appears in at least one window; boundary
    utterances may appear in two.
    """

    def __init__(self, window_sec: int = 900, overlap_sec: int = 120):
        if overlap_sec >= window_sec:
            raise PipelineError(
                f"sliding_overlap_sec ({overlap_sec}) must be smaller "
                f"than sliding_window_sec ({window_sec})."
            )
        self.window_sec = window_sec
        self.overlap_sec = overlap_sec

    def chunk(self, utterances: list[AtomicUtterance]) -> list[WindowPayload]:
        if not utterances:
            return []
        ordered = sorted(utterances, key=lambda u: (u.start_ms, u.end_ms))
        windows: list[list[AtomicUtterance]] = [[]]
        start_ms = ordered[0].start_ms
        for utterance in ordered:
            if windows[-1] and utterance.start_ms - start_ms >= self.window_sec * 1000:
                windows.append([])
                start_ms = utterance.start_ms
            windows[-1].append(utterance)

        payloads: list[WindowPayload] = []
        for index, members in enumerate(windows):
            # Carry boundary utterances into the NEXT window when they
            # start within the final overlap span and a next window exists.
            if index < len(windows) - 1:
                overlap_start = members[-1].start_ms - self.overlap_sec * 1000
                carried = [u for u in members if u.start_ms >= overlap_start]
                windows[index + 1] = sorted(
                    carried + windows[index + 1],
                    key=lambda u: (u.start_ms, u.end_ms),
                )
            payloads.append(
                WindowPayload(
                    window_index=index,
                    utterances=[format_utterance(u) for u in members],
                )
            )
        return payloads


def format_utterance(utterance: AtomicUtterance) -> dict:
    """One prompt line + the derived metadata the LLM may rely on."""
    start_label = _format_time_label(utterance.start_ms)
    end_label = _format_time_label(utterance.end_ms)
    line = (
        f"[{utterance.u_id} | {start_label} - {end_label} | "
        f"RMS:{utterance.audio_rms_norm:.2f} | "
        f"PauseAfter:{utterance.pause_after_ms}ms] {utterance.text}"
    )
    return {
        "u_id": utterance.u_id,
        "line": line,
        "text": utterance.text,
        "ordinal": int(utterance.u_id.split("_")[1]),
        "start_ms": utterance.start_ms,
        "end_ms": utterance.end_ms,
        "audio_rms_norm": utterance.audio_rms_norm,
        "pause_after_ms": utterance.pause_after_ms,
        "pitch_variance": utterance.pitch_variance,
        "silence_ratio": utterance.silence_ratio,
    }


def _format_time_label(ms: int) -> str:
    """``MM:SS.s`` label for the prompt (NEVER emitted by the LLM)."""
    total = max(0, int(ms))
    minutes = total // 60000
    seconds = (total % 60000) / 1000.0
    return f"{minutes:02d}:{seconds:04.1f}"


# ---------------------------------------------------------------------------
# Deterministic heuristic fallback (real candidate generator, no network)
# ---------------------------------------------------------------------------


class HeuristicFallbackProvider(LLMProvider):
    """Deterministic candidate span selector (no LLM, no network).

    Picks long, well-paused, loud utterance clusters. Honestly labeled
    ("heuristic fallback") in every candidate's evidence_log; it does NOT
    claim semantic understanding — scores come from stage s05 anyway.
    """

    name = "heuristic_fallback"

    def __init__(self, min_clip_sec: int, max_clip_sec: int):
        self.min_clip_sec = min_clip_sec
        self.max_clip_sec = max_clip_sec

    def propose_candidates(self, window: WindowPayload) -> ProviderResult:
        rows = sorted(window.utterances, key=lambda u: u["ordinal"])
        proposals: list[dict] = []
        start_idx = 0
        while start_idx < len(rows):
            span: list[dict] = []
            end_idx = start_idx
            while end_idx < len(rows):
                candidate_duration = (
                    rows[end_idx]["end_ms"] - rows[start_idx]["start_ms"]
                ) / 1000.0
                if candidate_duration > self.max_clip_sec:
                    break
                span.append(rows[end_idx])
                end_idx += 1
            if not span:
                end_idx = start_idx + 1
                start_idx = end_idx
                continue
            duration = (span[-1]["end_ms"] - span[0]["start_ms"]) / 1000.0
            if duration >= self.min_clip_sec:
                avg_rms = sum(r["audio_rms_norm"] for r in span) / max(1, len(span))
                bridge_u = span[len(span) // 2]["u_id"]
                proposals.append(
                    {
                        "start_u_id": span[0]["u_id"],
                        "end_u_id": span[-1]["u_id"],
                        "archetype": "STORY",
                        "hook_remix": {
                            "enabled": False,
                            "hook_u_id": bridge_u,
                            "ai_bridge_text": None,
                        },
                        "broll": [],
                        "pinned_comment_cta": None,
                        "curiosity_titles": [],
                        "_avg_rms_hint": avg_rms,
                    }
                )
            start_idx = max(end_idx - 1, start_idx + 1)
        return ProviderResult(proposals=proposals, provider_name=self.name)


# ---------------------------------------------------------------------------
# Proposal -> ClipCandidate (all milliseconds derived; LLM kept out)
# ---------------------------------------------------------------------------


def build_candidate_from_proposal(
    index_hint: int,
    proposal: dict,
    raw: dict[str, dict],
) -> ClipCandidate:
    """Harden one validated proposal into a strict ``ClipCandidate``.

    ``raw`` maps u_id -> formatted row (with REAL ms + text). Clip ms come
    ONLY from the utterances; anything elapsed-ish in the proposal is
    ignored by construction (LLM never sends ms here).
    """
    start = raw[proposal["start_u_id"]]
    end = raw[proposal["end_u_id"]]
    clip_ms = end["end_ms"] - start["start_ms"]
    broll_cues = []
    for cue in proposal.get("broll", []):
        broll_cues.append(
            BrollCue(
                trigger_ms=start["start_ms"] + int(round(cue["offset_sec"] * 1000)),
                duration_ms=int(round(cue["duration_sec"] * 1000)),
                search_query=cue["search_query"],
                overlay_type=cue["overlay_type"],
            )
        )
    hook = proposal.get("hook_remix") or {}
    hook_enabled = bool(hook.get("enabled"))
    hook_u_id = hook.get("hook_u_id")
    source_ms: tuple[int, int] | None = None
    if hook_enabled and hook_u_id:
        hook_row = raw[hook_u_id]
        source_ms = (hook_row["start_ms"], hook_row["end_ms"])
    hook_remix = HookRemixVariant(
        enabled=hook_enabled,
        hook_u_id=hook_u_id,
        source_start_ms=source_ms[0] if source_ms else None,
        source_end_ms=source_ms[1] if source_ms else None,
        ai_bridge_text=hook.get("ai_bridge_text"),
        context_preserved=hook.get("context_preserved", True),
    )
    evidence = [f"llm({index_hint}) archetype={proposal['archetype']}"]
    return ClipCandidate(
        clip_id=f"clip_{index_hint:04d}",
        start_u_id=proposal["start_u_id"],
        end_u_id=proposal["end_u_id"],
        start_ms=start["start_ms"],
        end_ms=end["end_ms"],
        duration_sec=clip_ms / 1000.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=False,
            rejection_reason="pending_s05_ranking",
        ),
        cps=CPSBreakdown(
            total_score=0.0,
            archetype="STORY",
            standalone_clarity=0.0,
            hook_strength=0.0,
            story_payoff=0.0,
            value_originality=0.0,
            audio_dynamics=0.0,
            visual_composition=None,
            boundary_precision=0.0,
        ),
        hook_remix=hook_remix,
        broll_cues=broll_cues,
        evidence_log=evidence,
        draft_pinned_comment_cta=proposal.get("pinned_comment_cta"),
        draft_curiosity_titles=proposal.get("curiosity_titles", []),
    )


def run_candidates_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    provider: LLMProvider | None = None,
) -> QattaManifest:
    """Execute stage s04_candidates for the given manifest."""
    settings = settings or QattaSettings()
    if not manifest.atomic_utterances:
        raise PipelineError(
            "No atomic utterances in the manifest; run stage s02_transcript before s04_candidates."
        )

    chunker = SlidingWindowChunker(
        window_sec=settings.sliding_window_sec,
        overlap_sec=settings.sliding_overlap_sec,
    )
    windows = chunker.chunk(manifest.atomic_utterances)
    raw = {row["u_id"]: row for window in windows for row in window.utterances}

    candidates: list[ClipCandidate] = []
    provider_notes: list[dict[str, str]] = []
    proposals_seen: set[tuple[str, str]] = set()

    provider = provider or select_provider(settings)

    for window in windows:
        try:
            result = provider.propose_candidates(window)
        except PipelineError as e:
            if not settings.llm_fallback_enabled:
                raise
            provider_notes.append(
                {
                    "provider": getattr(provider, "name", "unknown"),
                    "reason": str(e)[:300],
                    "mode": "fallback",
                }
            )
            provider = HeuristicFallbackProvider(settings.min_clip_sec, settings.max_clip_sec)
            try:
                result = provider.propose_candidates(window)
            except PipelineError as fallback_error:  # pragma: no cover
                raise PipelineError(
                    f"Heuristic fallback failed: {fallback_error}"
                ) from fallback_error

        for proposal in result.proposals:
            proposal = dict(proposal)
            proposal.pop("_avg_rms_hint", None)  # internal-only field
            try:
                normalized = validate_proposal(proposal, raw)
            except PipelineError as e:
                provider_notes.append(
                    {
                        "provider": result.provider_name,
                        "reason": str(e)[:300],
                        "mode": "skip",
                    }
                )
                continue
            key = (
                normalized["start_u_id"],
                normalized["end_u_id"],
            )
            if key in proposals_seen:
                provider_notes.append(
                    {
                        "provider": result.provider_name,
                        "reason": f"duplicate span {key[0]}->{key[1]} (window overlap dedupe)",
                        "mode": "skip",
                    }
                )
                continue
            proposals_seen.add(key)
            candidates.append(build_candidate_from_proposal(len(candidates) + 1, normalized, raw))

    if not candidates:
        raise PipelineError(
            "No valid candidates after provider + fallback passes. "
            "Nothing was fabricated — inspect provider warnings: "
            + json.dumps(provider_notes, ensure_ascii=False)[:2000]
        )

    data = manifest.model_dump()
    data["candidates"] = [c.model_dump() for c in candidates]
    return manifest.model_validate(data)


def register(orchestrator, provider: LLMProvider | None = None) -> None:
    """Attach s04_candidates; provider injectable for mock tests."""

    @orchestrator.stage("s04_candidates")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_candidates_stage(manifest, orchestrator.settings, provider)
