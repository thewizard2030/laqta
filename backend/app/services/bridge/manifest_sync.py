"""Manifest-to-SQLite Synchronization Bridge.

Translates and projects QattaManifest state into SQLite database records
(MediaAssetRecord, TranscriptRecord, CandidateRecord, RenderedClipRecord),
ensuring 100% backward compatibility for all web API routes and frontend UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import logger
from app.db.connection import get_connection
from app.db.repository import (
    CandidateRepository,
    ProjectRepository,
    RenderRepository,
)
from app.schemas.transcription import TranscriptSegment, WordTiming
from qatta.core.schema import QattaManifest


def sync_manifest_to_db(
    manifest: QattaManifest,
    project_id: str,
    repo: ProjectRepository | None = None,
    candidates_repo: CandidateRepository | None = None,
    renders_repo: RenderRepository | None = None,
) -> None:
    """Project the QattaManifest state into SQLite records."""
    repo = repo or ProjectRepository()
    candidates_repo = candidates_repo or CandidateRepository()
    renders_repo = renders_repo or RenderRepository()

    media_list = repo.list_project_media(project_id)
    if not media_list:
        logger.warning(
            "sync_manifest_to_db: No media asset found for project '%s'; skipping DB sync.",
            project_id,
        )
        return
    media = media_list[0]

    # 1. Update MediaAsset metadata from manifest if probe info exists
    dur_ms = int(manifest.duration_sec * 1000)
    width = manifest.video_width or media.width
    height = manifest.video_height or media.height
    with get_connection(repo.db_path) as conn:
        conn.execute(
            "UPDATE media_assets SET duration_ms = ?, width = ?, height = ? WHERE id = ?",
            (dur_ms, width, height, media.id),
        )

    # 2. Sync Transcripts
    transcript_id: str | None = None
    if manifest.atomic_utterances:
        segments: list[TranscriptSegment] = []
        for idx, u in enumerate(manifest.atomic_utterances, start=1):
            words = [
                WordTiming(
                    word=w.word,
                    start=w.start_ms / 1000.0,
                    end=w.end_ms / 1000.0,
                    probability=w.confidence,
                )
                for w in u.words
            ]
            segments.append(
                TranscriptSegment(
                    id=str(idx),
                    start=u.start_ms / 1000.0,
                    end=u.end_ms / 1000.0,
                    text=u.text,
                    words=words,
                )
            )

        full_text = " ".join(u.text for u in manifest.atomic_utterances)
        has_words = any(bool(u.words) for u in manifest.atomic_utterances)
        timing_granularity = "word" if has_words else "utterance"
        segments_json = json.dumps([s.model_dump() for s in segments])

        existing_transcripts = repo.list_media_transcripts(media.id)
        if existing_transcripts:
            latest = existing_transcripts[0]
            transcript_id = latest.id
            repo.update_transcript(
                transcript_id=latest.id,
                text=full_text,
                segments_json=segments_json,
                word_timestamps_available=has_words,
                timing_granularity=timing_granularity,
            )
        else:
            t_rec = repo.create_transcript(
                media_id=media.id,
                language=manifest.language_profile,
                provider="qatta_pipeline",
                model="local_turbo",
                text=full_text,
                segments_json=segments_json,
                word_timestamps_available=has_words,
                timing_granularity=timing_granularity,
                status="completed",
            )
            transcript_id = t_rec.id

    # 3. Sync Candidates
    if manifest.candidates and transcript_id:
        existing_candidates = {c.id: c for c in candidates_repo.list_media_candidates(media.id)}
        for candidate in manifest.candidates:
            cid = candidate.clip_id
            span_ids_json = json.dumps([candidate.start_u_id, candidate.end_u_id])
            title = (
                candidate.draft_curiosity_titles[0]
                if candidate.draft_curiosity_titles
                else f"Clip {cid}"
            )
            hook = candidate.hook_remix.ai_bridge_text or candidate.draft_pinned_comment_cta or None
            rationale_json = json.dumps(candidate.evidence_log)

            feature_scores = [
                {
                    "key": "self_contained",
                    "label": "Standalone Clarity",
                    "score": round(candidate.cps.standalone_clarity, 2),
                    "nominal_weight": 0.25,
                    "effective_weight": 0.25,
                    "available": True,
                    "rationale": "Self-contained premise and boundary completeness",
                },
                {
                    "key": "hook",
                    "label": "Hook Strength",
                    "score": round(candidate.cps.hook_strength, 2),
                    "nominal_weight": 0.20,
                    "effective_weight": 0.20,
                    "available": True,
                    "rationale": "Opening energy and attention hook",
                },
                {
                    "key": "completion",
                    "label": "Story Payoff",
                    "score": round(candidate.cps.story_payoff, 2),
                    "nominal_weight": 0.20,
                    "effective_weight": 0.20,
                    "available": True,
                    "rationale": "Clear resolution and punchline",
                },
                {
                    "key": "novelty_emotion",
                    "label": "Value & Originality",
                    "score": round(candidate.cps.value_originality, 2),
                    "nominal_weight": 0.10,
                    "effective_weight": 0.10,
                    "available": True,
                    "rationale": "Topic novelty and actionable insight",
                },
                {
                    "key": "clarity",
                    "label": "Audio Dynamics",
                    "score": round(candidate.cps.audio_dynamics, 2),
                    "nominal_weight": 0.10,
                    "effective_weight": 0.10,
                    "available": True,
                    "rationale": "Acoustic delivery and dynamics",
                },
                {
                    "key": "boundary",
                    "label": "Boundary Precision",
                    "score": round(candidate.cps.boundary_precision, 2),
                    "nominal_weight": 0.10,
                    "effective_weight": 0.10,
                    "available": True,
                    "rationale": "Clean cut inside acoustic pause",
                },
            ]
            if candidate.cps.visual_composition is not None:
                feature_scores.append(
                    {
                        "key": "visual",
                        "label": "Visual Composition",
                        "score": round(candidate.cps.visual_composition, 2),
                        "nominal_weight": 0.05,
                        "effective_weight": 0.05,
                        "available": True,
                        "rationale": "Scene cuts and visual framing",
                    }
                )

            feature_scores_json = json.dumps(feature_scores)
            cps = round(candidate.cps.total_score, 2)
            status = "suggested" if candidate.veto_gates.passed_all else "rejected"

            from app.db.repository import _utc_now_iso

            now_str = _utc_now_iso()
            if cid in existing_candidates:
                candidates_repo.update_candidate(
                    candidate_id=cid,
                    start_ms=candidate.start_ms,
                    end_ms=candidate.end_ms,
                    title=title,
                    hook=hook,
                    rationale_json=rationale_json,
                    feature_scores_json=feature_scores_json,
                    transcript_span_ids_json=span_ids_json,
                    cps=cps,
                    status=status,
                )
            else:
                candidates_repo.put_candidate(
                    candidate_id=cid,
                    media_id=media.id,
                    transcript_id=transcript_id,
                    start_ms=candidate.start_ms,
                    end_ms=candidate.end_ms,
                    transcript_span_ids_json=span_ids_json,
                    title=title,
                    hook=hook,
                    rationale_json=rationale_json,
                    feature_scores_json=feature_scores_json,
                    cps=cps,
                    status=status,
                    created_at=now_str,
                )

    # 4. Sync Render Records
    for candidate in manifest.candidates:
        if candidate.rendered_paths:
            for preset_name, path_str in candidate.rendered_paths.items():
                p = Path(path_str)
                if p.is_file():
                    existing_renders = renders_repo.list_candidate_renders(candidate.clip_id)
                    already_stored = any(r.output_path == str(p) for r in existing_renders)
                    if not already_stored:
                        size_bytes = p.stat().st_size
                        dur_ms = candidate.end_ms - candidate.start_ms
                        renders_repo.create_rendered_clip(
                            candidate_id=candidate.clip_id,
                            media_id=media.id,
                            output_path=str(p),
                            width=1080,
                            height=1920,
                            duration_ms=dur_ms,
                            size_bytes=size_bytes,
                            video_probe_json=json.dumps(
                                {"width": 1080, "height": 1920, "codec": "h264"}
                            ),
                            render_config_json=json.dumps(
                                {"preset": preset_name, "quality": "high"}
                            ),
                        )
