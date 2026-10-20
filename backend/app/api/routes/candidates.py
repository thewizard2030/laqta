"""Candidate generation and listing endpoints (PRD §5 FR-04/FR-05, §11 Gate C).

Generation is pure deterministic Python over the already-persisted transcript:
no media processing occurs inside request handlers. Ranking is baseline CPS by
default; an OPTIONAL provider-backed LLM reranker (FR-11) may reorder
candidates and attach rationale/title/hook suggestions, but CPS itself always
remains the deterministic baseline heuristic (never a virality probability),
and any LLM failure falls back to the baseline order.
"""

import html
import ipaddress
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.logging import logger
from app.db.models import CandidateRecord
from app.db.repository import CandidateRepository, ProjectRepository
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from app.providers.llm.openrouter import OpenRouterProvider
from app.schemas.candidates import (
    SCORING_NOTICE,
    CandidateGenerationRequest,
    CandidateGenerationResponse,
    CandidateResponse,
    CandidateStatus,
    CandidateUpdateRequest,
    ComponentScoreSchema,
)
from app.schemas.transcription import TranscriptSegment
from app.services.candidates.generator import (
    CandidateGenerationError,
    ScoredCandidate,
    _make_draft,
    build_boundary_units,
    generate_candidates,
    make_candidate_id,
)
from app.services.media.probe import TRANSCRIPT_LEAVES_DEVICE_NOTICE
from app.services.scoring.baseline import COMPONENT_LABELS, ScoringConfig, score_candidate
from app.services.scoring.ranker import (
    BaselineClipRanker,
    LLMClipRanker,
    RankCandidateInput,
    RankedSet,
)

router = APIRouter()
repo = ProjectRepository()
candidates_repo = CandidateRepository()


def _clean_str(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = html.unescape(text)
    cleaned = re.sub(r"^\s*>>*\s*", "", cleaned)
    cleaned = cleaned.replace(">>", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_record(record: CandidateRecord) -> CandidateResponse:
    """Deserialize a persisted candidate into the API response model."""
    try:
        span_ids = json.loads(record.transcript_span_ids_json)
    except json.JSONDecodeError:
        span_ids = []
    try:
        components_raw = json.loads(record.feature_scores_json)
    except json.JSONDecodeError:
        components_raw = []
    try:
        rationale = json.loads(record.rationale_json)
    except json.JSONDecodeError:
        rationale = []

    components = [
        ComponentScoreSchema(**c) if isinstance(c, dict) else ComponentScoreSchema(key=c)
        for c in components_raw
    ]
    unavailable = [c.key for c in components if not c.available]

    return CandidateResponse(
        id=record.id,
        media_id=record.media_id,
        transcript_id=record.transcript_id,
        start_ms=record.start_ms,
        end_ms=record.end_ms,
        duration_ms=record.end_ms - record.start_ms,
        status=CandidateStatus(record.status),
        cps=record.cps,
        title=_clean_str(record.title),
        hook=_clean_str(record.hook),
        transcript_span_ids=span_ids,
        feature_scores=components,
        unavailable_features=unavailable,
        rationale=rationale,
        created_at=record.created_at,
    )


def _persist_scored(
    media_id: str,
    transcript_id: str,
    scored_items: list[ScoredCandidate],
    config: ScoringConfig,
    ranked_set: RankedSet,
) -> list[CandidateResponse]:
    """Persist suggested/penalized candidates idempotently (deterministic IDs).

    Persistence order follows ``ranked_set`` (baseline CPS order unless an LLM
    rerank succeeded). CPS is never overwritten by the LLM; LLM title/hook/
    rationale annotations are clearly labelled as suggestions.
    """
    now_iso = datetime.now(UTC).isoformat()
    scored_by_id = {
        make_candidate_id(transcript_id, s.candidate.start_ms, s.candidate.end_ms): s
        for s in scored_items
    }
    persisted: list[CandidateResponse] = []
    for ranked in ranked_set.ranked:
        scored = scored_by_id.get(ranked.candidate_id)
        if scored is None:  # defensive: ranker may only return known IDs
            continue
        draft = scored.candidate
        if scored.cps >= config.suggested_threshold:
            candidate_status = CandidateStatus.SUGGESTED
        else:
            candidate_status = CandidateStatus.PENALIZED

        baseline_title = _clean_str(" ".join(draft.text.split())[:80])
        # LLM-suggested title/hook are validated/bounded upstream (Pydantic)
        # and fall back to the baseline title when absent.
        title = _clean_str(ranked.title) if ranked.reranked and ranked.title else baseline_title
        hook = _clean_str(ranked.hook) if ranked.reranked and ranked.hook else None

        rationale_lines = list(scored.rationale)
        for extra in ranked.rationale_extra:
            rationale_lines.append(f"LLM rerank suggestion (not a CPS input): {extra}")

        components_json = json.dumps(
            [
                {
                    "key": c.key,
                    "label": COMPONENT_LABELS.get(c.key, c.key),
                    "score": c.score,
                    "nominal_weight": c.weight,
                    "effective_weight": c.effective_weight,
                    "available": c.available,
                    "rationale": c.rationale,
                }
                for c in scored.components.values()
            ]
        )
        record = candidates_repo.put_candidate(
            candidate_id=ranked.candidate_id,
            media_id=media_id,
            transcript_id=transcript_id,
            start_ms=draft.start_ms,
            end_ms=draft.end_ms,
            transcript_span_ids_json=json.dumps(draft.span_ids),
            title=title,
            hook=hook,
            rationale_json=json.dumps(rationale_lines),
            feature_scores_json=components_json,
            cps=scored.cps,
            status=candidate_status.value,
            created_at=now_iso,
        )
        persisted.append(_parse_record(record))
    return persisted


def _endpoint_is_loopback(base_url: str) -> bool:
    """True when the LLM endpoint host is loopback (text stays on device)."""
    host = urlparse(base_url).hostname or ""
    if not host:
        return False
    host = host.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _build_llm_provider():
    """Instantiate the configured LLM adapter (never raises for a missing key).

    ``openai_compatible`` targets a user-run LOCAL server; ``openrouter``
    targets OpenRouter's HOSTED gateway (zero-price ``:free`` models are
    available there). The hosted adapter is a separate, explicit choice and
    is still gated by the hosted opt-in below.
    """
    if settings.LLM_PROVIDER == "openrouter":
        return OpenRouterProvider(
            api_key=settings.LLM_OPENROUTER_API_KEY or "",
            model=settings.LLM_OPENROUTER_MODEL,
            base_url=settings.LLM_OPENROUTER_BASE_URL,
            site_url=settings.LLM_OPENROUTER_SITE_URL,
            app_title=settings.LLM_OPENROUTER_APP_TITLE,
        )
    return OpenAICompatibleProvider(
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,  # secret; header-only transport
    )


async def _maybe_llm_rank(
    rank_inputs: list[RankCandidateInput],
) -> tuple[RankedSet, list[str]]:
    """Optionally rerank via the configured provider (FR-11), baseline otherwise.

    Returns (ranked_set, extra_warnings). Never raises: any provider failure
    is degraded to baseline ordering inside the ranker and disclosed.
    """
    if not settings.LLM_RANKER_ENABLED:
        ranked = await BaselineClipRanker().rank(rank_inputs)
        return ranked, []

    provider = _build_llm_provider()
    if not provider.is_available():
        ranked = await BaselineClipRanker().rank(rank_inputs)
        reason = (
            "OpenRouter API key is missing (set QATTA_LLM_OPENROUTER_API_KEY)."
            if settings.LLM_PROVIDER == "openrouter"
            else "LLM provider unavailable."
        )
        return ranked, [
            f"LLM ranker enabled but provider unavailable: {reason} Kept baseline ranking."
        ]

    # Remote (non-loopback) endpoints send transcript text off-device. That is
    # only allowed with explicit hosted opt-in, mirroring the disclosure
    # requirement for future hosted provider adapters (PRD §9, FR-11).
    # ``endpoint`` is optional on the provider interface (test doubles and
    # custom adapters may not expose it), so fall back to the configured URL.
    endpoint = getattr(provider, "endpoint", None) or settings.LLM_BASE_URL
    if not _endpoint_is_loopback(endpoint) and not settings.LLM_HOSTED_OPT_IN:
        ranked = await BaselineClipRanker().rank(rank_inputs)
        return ranked, [
            "LLM ranker skipped: endpoint is remote and transcript text would "
            f"leave the device. {TRANSCRIPT_LEAVES_DEVICE_NOTICE}",
        ]

    ranker = LLMClipRanker(
        provider,
        max_candidates=settings.LLM_MAX_CANDIDATES,
        timeout_s=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
    )
    ranked = await ranker.rank(rank_inputs)
    return ranked, list(ranked.warnings)


@router.post(
    "/media/{media_id}/candidates",
    response_model=CandidateGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist clip candidates from the latest transcript",
)
async def create_candidates(
    media_id: str,
    payload: CandidateGenerationRequest | None = None,
) -> CandidateGenerationResponse:
    """Generate deterministic, transcript-grounded candidate ranges.

    Uses the latest completed transcript; requires no API key by default.
    Generation is pure Python over stored transcript structure. Ranking is the
    deterministic baseline unless LLM reranking is explicitly enabled in
    settings (then bounded, validated, with baseline fallback).
    """
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )

    transcript = repo.get_latest_media_transcript(media_id)
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No completed transcript is available for this media asset. "
                "Run a transcription job before generating candidates."
            ),
        )

    req = payload or CandidateGenerationRequest()
    config = ScoringConfig(
        min_duration_s=req.min_duration_s,
        max_duration_s=req.max_duration_s,
        weights=tuple(
            (k, getattr(req.weights, k))
            for k in (
                "self_contained",
                "hook",
                "completion",
                "novelty_emotion",
                "clarity",
                "visual",
                "boundary",
            )
        ),
        max_overlap_iou=req.max_overlap_iou,
        keep_threshold=req.keep_threshold,
        suggested_threshold=req.suggested_threshold,
    )

    try:
        segments = [TranscriptSegment(**s) for s in json.loads(transcript.segments_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored transcript segments are not parseable: {e}",
        ) from e

    # Collect confidence proxies per segment id, when present (deterministic).
    word_probabilities_by_segment: dict[str, list[float]] = {}
    avg_logprob_by_segment: dict[str, list[float]] = {}
    for seg in segments:
        if seg.words and all(w.probability is not None for w in seg.words):
            word_probabilities_by_segment[seg.id] = [w.probability for w in seg.words]
        if seg.avg_logprob is not None:
            avg_logprob_by_segment[seg.id] = [seg.avg_logprob]

    try:
        result = generate_candidates(
            segments=segments,
            media_duration_ms=media.duration_ms,
            config=config,
            word_probabilities_by_segment=word_probabilities_by_segment,
            avg_logprob_by_segment=avg_logprob_by_segment,
        )
    except CandidateGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    persisted_items = result.candidates
    rank_inputs = [
        RankCandidateInput(
            candidate_id=make_candidate_id(transcript.id, s.candidate.start_ms, s.candidate.end_ms),
            cps_baseline=s.cps,
            start_ms=s.candidate.start_ms,
            end_ms=s.candidate.end_ms,
            text=s.candidate.text,
            evidence_ids=tuple(s.candidate.span_ids),
        )
        for s in persisted_items
    ]
    ranked_set, rank_warnings = await _maybe_llm_rank(rank_inputs)

    persisted = _persist_scored(
        media_id=media.id,
        transcript_id=transcript.id,
        scored_items=result.candidates,
        config=config,
        ranked_set=ranked_set,
    )

    # Sync generated candidates into project manifest
    try:
        from qatta.core.config import QattaSettings
        from qatta.core.pipeline import PipelineOrchestrator
        from qatta.core.schema import (
            ClipCandidate,
            CPSBreakdown,
            HookRemixVariant,
            QattaManifest,
            VetoGates,
        )

        project_dir = settings.get_project_dir(media.project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = project_dir / "qatta_manifest.json"

        if manifest_file.exists():
            orch = PipelineOrchestrator(
                project_id=media.project_id,
                work_dir=project_dir,
                settings=QattaSettings(),
            )
            manifest = orch.manifest
        elif Path(media.safe_path).is_file():
            orch = PipelineOrchestrator(
                project_id=media.project_id,
                source_path=Path(media.safe_path),
                work_dir=project_dir,
                settings=QattaSettings(),
            )
            manifest = orch.manifest
        else:
            manifest = QattaManifest(
                project_id=media.project_id,
                source_path=str(media.safe_path),
                duration_sec=max(0.1, media.duration_ms / 1000.0),
            )
            orch = None

        u_index = manifest.utterance_index()
        u_ids = list(u_index.keys()) if u_index else []
        manifest_candidates = []
        for p in persisted:
            start_u = u_ids[0] if u_ids else "U_0001"
            end_u = u_ids[-1] if len(u_ids) > 1 else "U_0002"
            is_u_span = len(p.transcript_span_ids) >= 2 and all(
                str(sid).startswith("U_") for sid in p.transcript_span_ids[:2]
            )
            if is_u_span:
                start_u, end_u = p.transcript_span_ids[0], p.transcript_span_ids[1]
            dur_sec = round((p.end_ms - p.start_ms) / 1000.0, 3)
            rej_reason = None if p.status.value == "suggested" else "Below threshold"
            mc = ClipCandidate(
                clip_id=p.id,
                start_u_id=start_u,
                end_u_id=end_u,
                start_ms=p.start_ms,
                end_ms=p.end_ms,
                duration_sec=dur_sec,
                veto_gates=VetoGates(
                    dangling_context=False,
                    clean_audio_boundaries=True,
                    crosstalk_ratio=0.0,
                    passed_all=(p.status.value == "suggested"),
                    rejection_reason=rej_reason,
                ),
                cps=CPSBreakdown(
                    total_score=p.cps,
                    archetype="TACTICAL_INSIGHT",
                    standalone_clarity=p.cps,
                    hook_strength=p.cps,
                    story_payoff=p.cps,
                    value_originality=p.cps,
                    audio_dynamics=p.cps,
                    visual_composition=None,
                    boundary_precision=p.cps,
                ),
                hook_remix=HookRemixVariant(enabled=False),
                draft_curiosity_titles=[p.title] if p.title else [],
                evidence_log=p.rationale or [],
            )
            manifest_candidates.append(mc)
        manifest.candidates = manifest_candidates
        if "s04_candidates" not in manifest.completed_stages:
            manifest.completed_stages.append("s04_candidates")
        if "s05_ranking" not in manifest.completed_stages:
            manifest.completed_stages.append("s05_ranking")

        if orch:
            orch.manifest = manifest
            orch.save_manifest()
        else:
            manifest_file.write_text(manifest.model_dump_json(), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not sync candidates to manifest: {e}")

    warnings = list(result.warnings) + rank_warnings

    # Thumbnail preview frames are extracted by a background job so the
    # request handler performs zero FFmpeg media processing.
    try:
        from app.jobs.manager import job_manager
        from app.schemas.jobs import JobType

        await job_manager.submit_job(
            project_id=media.project_id,
            job_type=JobType.CANDIDATE_THUMBNAILS.value,
            media_id=media.id,
        )
    except Exception as e:
        # Thumbnails are decorative previews; failure to enqueue only logs.
        logger.warning(f"Could not enqueue candidate thumbnails job: {e}")

    return CandidateGenerationResponse(
        media_id=media.id,
        transcript_id=transcript.id,
        candidates=persisted,
        warnings=warnings,
        scoring_notice=SCORING_NOTICE,
        ranking_method="llm_reranked" if ranked_set.reranked else "baseline",
        ranking_provider=ranked_set.provider_name,
    )


@router.get(
    "/media/{media_id}/candidates",
    response_model=list[CandidateResponse],
    summary="List persisted candidates for a media asset (ranked by CPS)",
)
async def list_media_candidates(media_id: str) -> list[CandidateResponse]:
    media = repo.get_media_asset(media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{media_id}' not found.",
        )
    records = candidates_repo.list_media_candidates(media_id)
    return [_parse_record(r) for r in records]


@router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateResponse,
    summary="Get one persisted candidate by ID",
)
async def get_candidate(candidate_id: str) -> CandidateResponse:
    record = candidates_repo.get_candidate(candidate_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    return _parse_record(record)


def _rescore_edited_span(
    segments: list[TranscriptSegment],
    media_duration_ms: int,
    start_ms: int,
    end_ms: int,
) -> ScoredCandidate:
    """Deterministically re-derive scores for a manually edited span.

    Reuses the exact same transcript-anchored machinery as generation
    (FR-04): boundaries map to existing transcript units, text/silence/cut
    risks come from those units, and CPS comes from the deterministic baseline
    scorer (FR-05). No LLM and no invented values are involved.
    """
    warnings: list[str] = []
    words_available = any(seg.words for seg in segments)
    units = build_boundary_units(segments, words_available, media_duration_ms, warnings)
    fitting = [u for u in units if u.end_ms > start_ms and u.start_ms < end_ms]
    if not fitting:
        raise CandidateGenerationError(
            "Edited range contains no transcript content; boundaries must "
            "overlap transcript evidence."
        )
    draft = _make_draft(start_ms, end_ms, fitting, media_duration_ms)
    if draft.end_ms - draft.start_ms <= 0:
        raise CandidateGenerationError(
            "Edited range is empty after clamping to the media duration."
        )

    word_probs: list[float] = []
    avg_lps: list[float] = []
    probs_by_segment: dict[str, list[float]] = {}
    lps_by_segment: dict[str, list[float]] = {}
    for seg in segments:
        if seg.words and all(w.probability is not None for w in seg.words):
            probs_by_segment[seg.id] = [w.probability for w in seg.words]
        if seg.avg_logprob is not None:
            lps_by_segment[seg.id] = [seg.avg_logprob]
    for u in draft.units:
        p = probs_by_segment.get(u.seg_id) or []
        if p and all(q is not None for q in p):
            word_probs.extend(p)
        lp = lps_by_segment.get(u.seg_id) or []
        if lp and lp[0] is not None:
            avg_lps.extend(lp)

    config = ScoringConfig()  # default bounds/weights for user edits
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
        word_probabilities=word_probs or None,
        avg_logprobs=avg_lps or None,
        low_boundary_precision=draft.low_boundary_precision,
        config=config,
    )
    return ScoredCandidate(
        candidate=draft,
        cps=result.cps,
        unavailable_keys=result.unavailable_keys,
        components=result.components,
        rationale=result.rationale,
    )


@router.patch(
    "/candidates/{candidate_id}",
    response_model=CandidateResponse,
    summary="Update reviewed clip boundaries and optional title/hook (user edit)",
)
async def update_candidate(
    candidate_id: str,
    payload: CandidateUpdateRequest,
) -> CandidateResponse:
    """Apply a user-reviewed boundary edit with Python-side validation.

    Validation (FR-04/FR-05 honesty contract):
    - ``start_ms``/``end_ms`` must lie within the source media duration.
    - Duration must respect the configured minimum/maximum (defaults 30-55 s).
    - The span is re-scored deterministically from transcript evidence; an LLM
      can never set a cut boundary, and edited ranges without transcript
      coverage are rejected with a clear error.
    """
    record = candidates_repo.get_candidate(candidate_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    media = repo.get_media_asset(record.media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media asset '{record.media_id}' not found.",
        )

    cfg = ScoringConfig()
    min_ms = int(cfg.min_duration_s * 1000)
    max_ms = int(cfg.max_duration_s * 1000)
    duration_ms = payload.end_ms - payload.start_ms
    if payload.end_ms > media.duration_ms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"end_ms ({payload.end_ms}) exceeds the source media duration "
                f"({media.duration_ms} ms)."
            ),
        )
    if duration_ms < min_ms or duration_ms > max_ms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Edited duration {duration_ms} ms is outside the configured "
                f"bounds ({min_ms}-{max_ms} ms; FR-04 default 30-55 s)."
            ),
        )

    transcript = repo.get_transcript(record.transcript_id)
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Transcript '{record.transcript_id}' for this candidate no "
                "longer exists; regenerate candidates before editing."
            ),
        )
    try:
        segments = [TranscriptSegment(**s) for s in json.loads(transcript.segments_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stored transcript segments are not parseable: {e}",
        ) from e

    try:
        scored = _rescore_edited_span(
            segments=segments,
            media_duration_ms=media.duration_ms,
            start_ms=payload.start_ms,
            end_ms=payload.end_ms,
        )
    except CandidateGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    draft = scored.candidate
    new_status = (
        CandidateStatus.SUGGESTED
        if scored.cps >= cfg.suggested_threshold
        else CandidateStatus.PENALIZED
    )
    components_json = json.dumps(
        [
            {
                "key": c.key,
                "label": COMPONENT_LABELS.get(c.key, c.key),
                "score": c.score,
                "nominal_weight": c.weight,
                "effective_weight": c.effective_weight,
                "available": c.available,
                "rationale": c.rationale,
            }
            for c in scored.components.values()
        ]
    )
    rationale_lines = list(scored.rationale)
    rationale_lines.append(
        f"Boundaries manually edited by the user to "
        f"{draft.start_ms}-{draft.end_ms} ms; scores were re-derived "
        "deterministically from transcript evidence for the edited span."
    )
    title = payload.title.strip()[:120] if payload.title and payload.title.strip() else record.title
    hook = payload.hook.strip()[:200] if payload.hook and payload.hook.strip() else record.hook

    updated = candidates_repo.update_candidate(
        candidate_id=candidate_id,
        start_ms=draft.start_ms,
        end_ms=draft.end_ms,
        title=title,
        hook=hook,
        rationale_json=json.dumps(rationale_lines),
        feature_scores_json=components_json,
        transcript_span_ids_json=json.dumps(draft.span_ids),
        cps=scored.cps,
        status=new_status.value,
    )
    if updated is None:  # pragma: no cover - row vanished mid-request
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate '{candidate_id}' not found.",
        )
    response = _parse_record(updated)
    response.boundary_edited = True
    return response
