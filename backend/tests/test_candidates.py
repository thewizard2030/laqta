"""Tests for candidate generation and deterministic baseline scoring
(PRD §5 FR-04, FR-05, FR-06 partial, §8, §11 Gate C).

Validates:
- Duration bounds (default 30-55 s, configurable) are always respected.
- No empty ranges; all boundaries inside media duration; clamping disclosed.
- Word boundaries never cut when word timestamps exist; evidence IDs real.
- Segment-only transcripts fall back with disclosed lower precision.
- Unavailable modalities (visual, ASR-free clarity) are flagged, never zeroed.
- Overlap IoU / near-duplicate handling; deterministic output on rerun.
- Weight validation and renormalization.
- Extreme transcript input (empty, fully-out-of-range, too short, reversed).
- API endpoints: create/list candidates (fake transcript fixture), clear
  errors for missing media/transcript, invalid duration payloads.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.repository import CandidateRepository, ProjectRepository
from app.schemas.transcription import TranscriptSegment, WordTiming
from app.services.candidates.generator import (
    CandidateGenerationError,
    generate_candidates,
    make_candidate_id,
)
from app.services.scoring.baseline import ScoringConfig, compute_cps


def word(word_text: str, start: float, end: float, probability: float = 0.95) -> WordTiming:
    return WordTiming(word=word_text, start=start, end=end, probability=probability)


def make_sentence(
    index: int,
    sentence_len_s: float = 8.0,
    with_words: bool = True,
    open_text: str | None = None,
) -> TranscriptSegment:
    """Deterministic sentence segment: words of 1 s each, last word punctuated."""
    base = f"Fact number {index} shows {index * 3} clear steps today"
    text = open_text if open_text is not None else f"{base}."
    if not with_words:
        return TranscriptSegment(
            id=f"seg_{index:04d}",
            start=index * sentence_len_s,
            end=(index + 1) * sentence_len_s,
            text=text,
            words=None,
            avg_logprob=None,
            no_speech_prob=None,
        )
    tokens = text.split()
    start = index * sentence_len_s
    words = [word(t, start + i, start + i + 1) for i, t in enumerate(tokens[:-1])]
    words.append(word(tokens[-1], start + len(tokens) - 1, start + sentence_len_s))
    return TranscriptSegment(
        id=f"seg_{index:04d}",
        start=start,
        end=(index + 1) * sentence_len_s,
        text=text,
        words=words,
        avg_logprob=-0.3,
        no_speech_prob=0.02,
    )


@pytest.fixture
def long_transcript() -> list[TranscriptSegment]:
    """30 x 8 s sentences = 240 s of speech inside a 300 s media asset."""
    return [make_sentence(i) for i in range(30)]


# ---------------------------------------------------------------- unit tests


def test_duration_bounds_respected(long_transcript) -> None:
    result = generate_candidates(long_transcript, media_duration_ms=300_000)
    assert result.candidates, "expected at least one candidate for a 240 s transcript"
    for scored in result.candidates:
        duration_ms = scored.candidate.end_ms - scored.candidate.start_ms
        assert 30_000 <= duration_ms <= 55_000


def test_no_empty_ranges_and_positive_duration(long_transcript) -> None:
    result = generate_candidates(long_transcript, media_duration_ms=300_000)
    for scored in result.candidates:
        assert scored.candidate.end_ms > scored.candidate.start_ms


def test_boundaries_inside_media_duration(long_transcript) -> None:
    media_duration_ms = 300_000
    # Segments run to 240 s: well inside. Extend one segment past the end.
    segments = long_transcript + [
        TranscriptSegment(
            id="seg_9999",
            start=250.0,
            end=400.0,  # beyond 300 s media duration
            text="This trailing sentence goes far beyond the media end.",
        )
    ]
    result = generate_candidates(segments, media_duration_ms=media_duration_ms)
    assert result.candidates
    for scored in result.candidates:
        assert 0 <= scored.candidate.start_ms < media_duration_ms
        assert scored.candidate.end_ms <= media_duration_ms


def test_clamped_truncation_disclosed(long_transcript) -> None:
    segments = long_transcript + [
        TranscriptSegment(
            id="seg_9999",
            start=250.0,
            end=400.0,
            text="This trailing sentence goes far beyond the media end.",
        )
    ]
    result = generate_candidates(segments, media_duration_ms=300_000)
    truncated_seen = False
    for scored in result.candidates:
        if scored.candidate.truncated:
            truncated_seen = True
            assert "clamped" in " ".join(scored.rationale).lower()
    assert truncated_seen, "a window touching the truncated segment must be clamped"


def test_no_word_cuts_with_word_timestamps(long_transcript) -> None:
    """Every boundary must equal a word start/end of an existing word."""
    word_starts: set[int] = set()
    word_ends: set[int] = set()
    for seg in long_transcript:
        assert seg.words is not None
        for w in seg.words:
            word_starts.add(round(w.start * 1000))
            word_ends.add(round(w.end * 1000))

    result = generate_candidates(long_transcript, media_duration_ms=300_000)
    assert result.candidates
    for scored in result.candidates:
        draft = scored.candidate
        assert draft.start_ms in word_starts, "candidate start cuts a word"
        assert draft.end_ms in word_ends, "candidate end cuts a word"
        assert draft.span_ids, "evidence IDs required"
        for span_id in draft.span_ids:
            assert span_id.startswith("seg_") or "#w" in span_id


def test_segment_only_transcript_fallback_and_unavailable_flags() -> None:
    segments = [make_sentence(i, with_words=False) for i in range(10)]
    result = generate_candidates(segments, media_duration_ms=120_000)
    assert result.candidates
    for scored in result.candidates:
        draft = scored.candidate
        assert draft.low_boundary_precision is True
        assert all(u.word_ids == [] for u in draft.units)
        unavailable = scored.unavailable_keys
        assert "visual" in unavailable  # no CV features implemented
        assert "clarity" in unavailable  # no confidence metadata in fixture
        keys = {c.key for c in scored.components.values()}
        assert unavailable and keys.issuperset(unavailable)
        assert any(
            "segment-end" in c.rationale or "segment ends" in c.rationale
            for c in scored.components.values()
            if c.key == "boundary"
        )


def test_unavailable_components_renormalize_not_zeroed() -> None:
    components_fixture = (
        generate_candidates(
            [make_sentence(i, with_words=False) for i in range(10)],
            media_duration_ms=120_000,
        )
        .candidates[0]
        .components
    )
    effective_total = sum(c.effective_weight for c in components_fixture.values() if c.available)
    assert effective_total == pytest.approx(1.0, abs=1e-6)
    for comp in components_fixture.values():
        if not comp.available:
            assert comp.score is None
            assert comp.effective_weight is None or comp.effective_weight == 0.0
        else:
            assert 0.0 <= comp.score <= 100.0


def test_deterministic_output(long_transcript) -> None:
    first = generate_candidates(long_transcript, media_duration_ms=300_000)
    second = generate_candidates(long_transcript, media_duration_ms=300_000)
    assert first.warnings == second.warnings

    def key(scored):
        return (
            make_candidate_id("t", scored.candidate.start_ms, scored.candidate.end_ms),
            scored.cps,
        )

    seq1 = sorted(first.candidates, key=key)
    seq2 = sorted(second.candidates, key=key)
    assert [
        (c.candidate.start_ms, c.candidate.end_ms, c.cps, c.unavailable_keys) for c in seq1
    ] == [(c.candidate.start_ms, c.candidate.end_ms, c.cps, c.unavailable_keys) for c in seq2]


def test_duplicate_candidate_ids_deterministic() -> None:
    assert make_candidate_id("tr_x", 10_000, 40_000) == make_candidate_id("tr_x", 10_000, 40_000)
    assert make_candidate_id("tr_x", 10_000, 40_000) != make_candidate_id("tr_y", 10_000, 40_000)
    assert make_candidate_id("tr_x", 10_000, 40_000) != make_candidate_id("tr_x", 11_000, 40_000)


def test_overlap_and_duplicates_suppressed(long_transcript) -> None:
    result = generate_candidates(
        long_transcript, media_duration_ms=300_000, config=ScoringConfig(max_overlap_iou=0.5)
    )
    kept = result.candidates
    assert kept
    for i, a in enumerate(kept):
        for b in kept[i + 1 :]:
            inter = max(
                0,
                min(a.candidate.end_ms, b.candidate.end_ms)
                - max(a.candidate.start_ms, b.candidate.start_ms),
            )
            union = max(a.candidate.end_ms, b.candidate.end_ms) - min(
                a.candidate.start_ms, b.candidate.start_ms
            )
            assert inter / union <= 0.5, "kept candidates exceed overlap threshold"


def test_extreme_input_empty_transcript() -> None:
    with pytest.raises(CandidateGenerationError) as exc:
        generate_candidates([], media_duration_ms=300_000)
    assert "no segments" in str(exc.value).lower()


def test_extreme_input_zero_media_duration(long_transcript) -> None:
    with pytest.raises(CandidateGenerationError) as exc:
        generate_candidates(long_transcript, media_duration_ms=0)
    assert "positive" in str(exc.value).lower()


def test_extreme_input_all_segments_beyond_media() -> None:
    segments = [
        TranscriptSegment(id=f"seg_{i:04d}", start=400.0 + i, end=420.0 + i, text=f"Beyond {i} u.")
        for i in range(5)
    ]
    with pytest.raises(CandidateGenerationError) as exc:
        generate_candidates(segments, media_duration_ms=300_000)
    assert "no valid transcript segments" in str(exc.value).lower()


def test_extreme_input_transcript_shorter_than_min_duration() -> None:
    segments = [make_sentence(i) for i in range(2)]  # 16 s total < 30 s min
    result = generate_candidates(segments, media_duration_ms=300_000)
    assert result.candidates == []
    assert any("no candidate passed" in w.lower() for w in result.warnings)


def test_extreme_input_reversed_and_empty_segments() -> None:
    good = make_sentence(0)
    bad_reversed = TranscriptSegment(id="seg_bad", start=10.0, end=5.0, text="Reversed timing x.")
    bad_empty = TranscriptSegment(id="seg_empty", start=9.0, end=12.0, text="   ")
    segments = [good, bad_reversed, bad_empty]
    result = generate_candidates(segments, media_duration_ms=60_000)
    # With a single valid 8 s sentence no 30-55 s window exists.
    assert result.candidates == []
    assert any("seg_bad" in w for w in result.warnings)
    assert any("seg_empty" in w for w in result.warnings)


def test_extreme_input_long_gaps_penalized() -> None:
    seg_a = make_sentence(0)
    seg_b = make_sentence(1)
    # Push the second sentence to create a 40 s dead-air gap.
    shifted = TranscriptSegment(
        id=seg_b.id,
        start=48.0,
        end=56.0,
        text=seg_b.text,
        words=None,
        avg_logprob=-0.3,
        no_speech_prob=0.02,
    )
    result = generate_candidates([seg_a, shifted], media_duration_ms=120_000)
    if result.candidates:
        penalty_seen = any(
            "Silence fraction" in c.rationale
            for s in result.candidates
            for c in s.components.values()
            if c.key == "boundary"
        )
        low_scores = [s.cps for s in result.candidates]
        assert penalty_seen or all(v < 60 for v in low_scores)


def test_weight_validation() -> None:
    with pytest.raises(ValueError):
        ScoringConfig(weights=(("self_contained", 0.5), ("nonexistent", 0.5)))
    with pytest.raises(ValueError):
        ScoringConfig(weights=(("self_contained", -0.1),))
    with pytest.raises(ValueError):
        ScoringConfig(min_duration_s=55.0, max_duration_s=30.0)


def test_weights_renormalized_to_one() -> None:
    cfg = ScoringConfig(weights=(("self_contained", 0.4), ("boundary", 0.2)))
    weights = cfg.weight_map()
    assert sum(weights.values()) == pytest.approx(1.0)


def test_compute_cps_empty_when_all_unavailable() -> None:
    cps, effective = compute_cps({})
    assert cps == 0.0
    assert effective == {}


def test_custom_duration_bounds_unlock_shorter_candidates() -> None:
    segments = [make_sentence(i) for i in range(10)]  # 80 s total
    wide = generate_candidates(
        segments,
        media_duration_ms=120_000,
        config=ScoringConfig(min_duration_s=10.0, max_duration_s=60.0),
    )
    assert wide.candidates
    for scored in wide.candidates:
        duration_ms = scored.candidate.end_ms - scored.candidate.start_ms
        assert 10_000 <= duration_ms <= 60_000
    assert any(
        10_000 <= (s.candidate.end_ms - s.candidate.start_ms) < 30_000 for s in wide.candidates
    ), "widened bounds should unlock shorter candidates outside the default range"


# ---------------------------------------------------------------- API tests


def _make_media_and_transcript(
    client: TestClient,
    project_name: str = "Candidates E2E",
) -> tuple[str, str]:
    """Create project + media asset + completed transcript directly in DB."""
    res_proj = client.post("/api/projects", json={"name": project_name})
    assert res_proj.status_code == 201
    project_id = res_proj.json()["id"]

    repo = ProjectRepository()
    media = repo.create_media_asset(
        project_id=project_id,
        safe_path="/tmp/qatta_test_clip.mp4",
        original_name="test_clip.mp4",
        size_bytes=1024,
        duration_ms=300_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    segments = [make_sentence(i) for i in range(30)]
    transcript = repo.create_transcript(
        media_id=media.id,
        language="en",
        provider="fake",
        model="base",
        text=" ".join(s.text for s in segments),
        segments_json=json.dumps([s.model_dump() for s in segments]),
        word_timestamps_available=True,
        timing_granularity="word",
    )
    return media.id, transcript.id


def test_candidates_api_full_flow(client: TestClient) -> None:
    media_id, transcript_id = _make_media_and_transcript(client)

    res_create = client.post(f"/api/media/{media_id}/candidates", json={})
    assert res_create.status_code == 201
    body = res_create.json()
    assert body["media_id"] == media_id
    assert body["transcript_id"] == transcript_id
    assert len(body["candidates"]) >= 1
    assert "not a probability" in body["scoring_notice"]
    first = body["candidates"][0]
    assert 0 <= first["cps"] <= 100
    assert first["start_ms"] >= 0
    assert first["end_ms"] <= 300_000
    assert first["duration_ms"] == first["end_ms"] - first["start_ms"]
    assert 30_000 <= first["duration_ms"] <= 55_000
    assert first["status"] in {"suggested", "penalized"}
    assert first["transcript_span_ids"]
    assert first["feature_scores"]
    assert first["cps_interpretation"]

    # List endpoint returns persisted candidates ranked by CPS desc.
    res_list = client.get(f"/api/media/{media_id}/candidates")
    assert res_list.status_code == 200
    listed = res_list.json()
    assert len(listed) >= len(body["candidates"])
    cpss = [c["cps"] for c in listed]
    assert cpss == sorted(cpss, reverse=True)

    # Get one by ID.
    res_one = client.get(f"/api/candidates/{first['id']}")
    assert res_one.status_code == 200
    assert res_one.json()["id"] == first["id"]

    # Regeneration is idempotent: same candidates re-persisted under same IDs.
    res_again = client.post(f"/api/media/{media_id}/candidates", json={})
    assert res_again.status_code == 201
    ids_again = {c["id"] for c in res_again.json()["candidates"]}
    assert ids_again == {c["id"] for c in body["candidates"]}


def strip(payload) -> list[dict]:
    return [
        {
            "id": c["id"],
            "start_ms": c["start_ms"],
            "end_ms": c["end_ms"],
            "cps": c["cps"],
            "status": c["status"],
            "rationale": c["rationale"],
            "feature_scores": c["feature_scores"],
        }
        for c in payload.json()["candidates"]
    ]


def test_candidates_api_deterministic_scoring(client: TestClient) -> None:
    media_id, _ = _make_media_and_transcript(client, project_name="Candidates Determinism")
    a = client.post(f"/api/media/{media_id}/candidates", json={})
    b = client.post(f"/api/media/{media_id}/candidates", json={})
    assert strip(a) == strip(b)


def test_candidates_api_media_not_found(client: TestClient) -> None:
    res = client.post("/api/media/med_nonexistent/candidates", json={})
    assert res.status_code == 404
    res = client.get("/api/media/med_nonexistent/candidates")
    assert res.status_code == 404


def test_candidates_api_missing_transcript_clear_error(client: TestClient) -> None:
    res_proj = client.post("/api/projects", json={"name": "No Transcript Project"})
    project_id = res_proj.json()["id"]
    repo = ProjectRepository()
    media = repo.create_media_asset(
        project_id=project_id,
        safe_path="/tmp/qatta_no_transcript.mp4",
        original_name="clip.mp4",
        size_bytes=1024,
        duration_ms=300_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    res = client.post(f"/api/media/{media.id}/candidates", json={})
    assert res.status_code == 409
    assert "transcription" in res.json()["detail"].lower()


def test_candidates_api_invalid_duration_payload(client: TestClient) -> None:
    res = client.post(
        "/api/media/med_any/candidates",
        json={"min_duration_s": 55.0, "max_duration_s": 30.0},
    )
    assert res.status_code == 422


def test_candidates_api_custom_weights_persisted(client: TestClient) -> None:
    media_id, _ = _make_media_and_transcript(client, project_name="Candidates Weights")
    res = client.post(
        f"/api/media/{media_id}/candidates",
        json={
            "min_duration_s": 30.0,
            "max_duration_s": 55.0,
            "weights": {
                "self_contained": 0.15,
                "hook": 0.10,
                "completion": 0.10,
                "novelty_emotion": 0.05,
                "clarity": 0.05,
                "visual": 0.05,
                "boundary": 0.50,
            },
        },
    )
    assert res.status_code == 201
    candidate = res.json()["candidates"][0]
    by_key = {c["key"]: c for c in candidate["feature_scores"]}
    assert by_key["boundary"]["nominal_weight"] == pytest.approx(0.5)
    effective = sum(c["effective_weight"] for c in candidate["feature_scores"] if c["available"])
    assert effective == pytest.approx(1.0)


def test_candidates_rejected_below_threshold_not_persisted(client: TestClient) -> None:
    media_id, _ = _make_media_and_transcript(client, project_name="Candidates Threshold")
    res_strict = client.post(
        f"/api/media/{media_id}/candidates",
        json={"keep_threshold": 99.0, "suggested_threshold": 100.0},
    )
    assert res_strict.status_code == 201
    body = res_strict.json()
    assert body["candidates"] == []
    assert any(
        "no candidate passed" in w.lower() or "below the keep threshold" in w.lower()
        for w in body["warnings"]
    )


def test_candidate_repository_list_ordering(tmp_path: Path) -> None:
    """Direct repository test with an isolated DB path and real parent rows."""
    import app.db.connection as connection

    db_path = tmp_path / "cand_repo.db"
    connection.init_db(db_path)
    repo = ProjectRepository(db_path=db_path)
    project = repo.create_project("Candidates Repo Ordering")
    media = repo.create_media_asset(
        project_id=project.id,
        safe_path="/tmp/qatta_repo_test.mp4",
        original_name="clip.mp4",
        size_bytes=1024,
        duration_ms=300_000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )
    transcript = repo.create_transcript(
        media_id=media.id,
        language="en",
        provider="fake",
        model="base",
        text="Sample transcript",
        segments_json="[]",
        word_timestamps_available=True,
        timing_granularity="word",
    )
    cr = CandidateRepository(db_path=db_path)
    now = "2026-01-01T00:00:00+00:00"
    common = dict(
        media_id=media.id,
        transcript_id=transcript.id,
        transcript_span_ids_json="[]",
        hook=None,
        rationale_json="[]",
        feature_scores_json="[]",
        created_at=now,
    )

    def make(cid: str, start: int, end: int, cps: float) -> None:
        cr.put_candidate(
            candidate_id=cid,
            start_ms=start,
            end_ms=end,
            title=cid[-1].upper(),
            cps=cps,
            status="suggested" if cps >= 60 else "penalized",
            **common,
        )

    make("cand_a", 0, 40_000, 50.0)
    make("cand_b", 0, 45_000, 70.0)
    make("cand_c", 5_000, 25_000, 10.0)
    listed = cr.list_media_candidates(media.id)
    assert [c.id for c in listed] == ["cand_b", "cand_a", "cand_c"]
    assert [c.status for c in listed] == ["suggested", "penalized", "penalized"]
    assert cr.get_candidate("cand_a").cps == 50.0
    assert cr.delete_media_candidates(media.id) == 3
    assert cr.list_media_candidates(media.id) == []
