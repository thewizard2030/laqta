"""Tests for stage s03 (sanity), s04 (windows/LLM parsing) and s05.

Focus per the task: the SlidingWindowChunker, the Arabic dangling-context
auto-healer, and the CPS weight renormalization math. LLM providers are
tested through injected httpx mock clients (no network, no model).
"""

import json
from pathlib import Path

import httpx
import pytest

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
from qatta.stages.s04_candidates.generator import (
    SlidingWindowChunker,
    build_candidate_from_proposal,
    format_utterance,
    run_candidates_stage,
)
from qatta.stages.s04_candidates.llm import (
    OllamaProvider,
    WindowPayload,
    parse_llm_json,
    validate_proposal,
)
from qatta.stages.s05_ranking.scorer import (
    ARCHETYPE_WEIGHTS,
    compute_cps,
    heal_audio_boundaries,
    heal_dangling_context,
    is_dangling,
    run_ranking_stage,
)

# ---------------------------------------------------------------------------
# Fixtures: utterance tapes + candidate/manifest helpers
# ---------------------------------------------------------------------------


def make_utterance(
    u_id: str,
    start_ms: int,
    end_ms: int,
    text: str,
    rms: float = 0.5,
    pause_after_ms: int = 0,
    pitch_variance: float | None = None,
    silence_ratio: float | None = None,
) -> AtomicUtterance:
    return AtomicUtterance(
        u_id=u_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        audio_rms_norm=rms,
        pause_after_ms=pause_after_ms,
        pitch_variance=pitch_variance,
        silence_ratio=silence_ratio,
    )


def raw_index(utterances: list[AtomicUtterance]) -> dict[str, dict]:
    raw = {}
    for u in utterances:
        row = format_utterance(u)
        raw[row["u_id"]] = row
    return raw


def make_candidate(
    clip_id: str,
    start_u: str,
    end_u: str,
    start_ms: int,
    end_ms: int,
) -> ClipCandidate:
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id=start_u,
        end_u_id=end_u,
        start_ms=start_ms,
        end_ms=end_ms,
        duration_sec=(end_ms - start_ms) / 1000.0,
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
        hook_remix=HookRemixVariant(enabled=False),
    )


def make_settings(tmp_path: Path, **overrides) -> QattaSettings:
    return QattaSettings(data_dir=tmp_path / "data", _env_file=None, **overrides)


def make_manifest(utterances, candidates=(), source="/nowhere/x.mp4"):
    return QattaManifest(
        project_id="proj_s45",
        source_path=source,
        duration_sec=max((u.end_ms for u in utterances), default=1000) / 1000.0,
        audio_16k_path=str(Path("/nowhere/audio.wav")),
        language_profile="ar-EG-mixed",
        atomic_utterances=list(utterances),
        candidates=list(candidates),
    )


# ---------------------------------------------------------------------------
# SlidingWindowChunker
# ---------------------------------------------------------------------------


def test_chunker_small_input_single_window() -> None:
    chunker = SlidingWindowChunker(window_sec=900, overlap_sec=120)
    utterances = [
        make_utterance(f"U_{i:04d}", i * 1000, i * 1000 + 900, f"جملة {i}")
        for i in range(1, 51)  # 50 s total
    ]
    windows = chunker.chunk(utterances)
    assert len(windows) == 1
    covered = {u["u_id"] for u in windows[0].utterances}
    assert covered == {u.u_id for u in utterances}


def test_chunker_respects_window_size_and_overlap() -> None:
    chunker = SlidingWindowChunker(window_sec=60, overlap_sec=20)
    # Utterances every 5 s spanning 145 s -> expects ≥3 windows.
    utterances = [
        make_utterance(f"U_{i:04d}", i * 5000, i * 5000 + 3000, f"t{i}") for i in range(1, 30)
    ]
    windows = chunker.chunk(utterances)
    assert len(windows) >= 3

    covered: set[str] = set()
    for window in windows:
        ids = [u["u_id"] for u in window.utterances]
        assert len(ids) == len(set(ids))  # no duplicates inside one window
        covered.update(ids)
    assert covered == {u.u_id for u in utterances}  # nothing dropped

    # Overlap property: the last utterance of a window also starts the next.
    tail = windows[0].utterances[-1]["u_id"]
    heads = [u["u_id"] for u in windows[1].utterances]
    assert tail in heads


def test_chunker_rejects_overlap_ge_window() -> None:
    with pytest.raises(PipelineError):
        SlidingWindowChunker(window_sec=60, overlap_sec=60)


def test_prompt_line_format() -> None:
    utterance = make_utterance(
        "U_0104",
        412_300,
        416_800,
        "أكبر غلطة عملناها",
        rms=0.78,
        pause_after_ms=620,
    )
    row = format_utterance(utterance)
    assert row["line"].startswith("[U_0104 | 06:52.3 - 06:56.8 | RMS:0.78 | PauseAfter:620ms]")
    assert row["text"] == "أكبر غلطة عملناها"


# ---------------------------------------------------------------------------
# LLM proposal parsing/validation (LLM never outputs milliseconds)
# ---------------------------------------------------------------------------

_HONEST_PROPOSAL = {
    "start_u_id": "U_0002",
    "end_u_id": "U_0004",
    "archetype": "STORY",
    "hook_remix": {
        "enabled": True,
        "hook_u_id": "U_0003",
        "ai_bridge_text": "قبل الحدث، دي أهم نقطة",
    },
    "broll": [
        {
            "offset_sec": 1.5,
            "duration_sec": 2.0,
            "search_query": "startup office",
            "overlay_type": "STOCK_VIDEO",
        }
    ],
    "pinned_comment_cta": "لازم تعرف الرأي ده… قلنا في التعليق المثبت",
    "curiosity_titles": ["اللحظة اللي غيّرت كل شيء", "الحقيقة مخبية", "؟"],
}


def test_parse_llm_json_with_fences() -> None:
    text = "```json\n" + json.dumps({"candidates": []}) + "\n```"
    assert parse_llm_json(text) == {"candidates": []}


def test_validate_proposal_ignores_llm_milliseconds() -> None:
    utterances = [
        make_utterance("U_0001", 0, 2000, "واحد"),
        make_utterance("U_0002", 2500, 4500, "اتنين"),
        make_utterance("U_0003", 5000, 6500, "تلاتة", pause_after_ms=400),
        make_utterance("U_0004", 7000, 9000, "أربعة", pause_after_ms=400),
    ]
    raw = raw_index(utterances)
    proposal = dict(_HONEST_PROPOSAL)
    # Malicious/hallucinated ms fields MUST be ignored by construction.
    proposal["start_ms"] = 999_999_999
    proposal["end_ms"] = 1
    normalized = validate_proposal(proposal, raw)
    candidate = build_candidate_from_proposal(1, normalized, raw)
    # Real ms come from utterances, NEVER from the LLM payload.
    assert candidate.start_ms == 2500 and candidate.end_ms == 9000
    assert candidate.duration_sec == pytest.approx(6.5)
    assert candidate.broll_cues == [
        BrollCue(
            trigger_ms=2500 + 1500,  # clip start + RELATIVE offset
            duration_ms=2000,
            search_query="startup office",
            overlay_type="STOCK_VIDEO",
        )
    ]
    assert candidate.draft_pinned_comment_cta is not None
    assert len(candidate.draft_curiosity_titles) == 3
    assert candidate.hook_remix.enabled is True
    assert candidate.hook_remix.hook_u_id == "U_0003"


def test_validate_proposal_rejects_unknown_u_ids() -> None:
    raw = raw_index([make_utterance("U_0001", 0, 1000, "جملة واحدة")])
    with pytest.raises(PipelineError):
        validate_proposal({**_HONEST_PROPOSAL, "end_u_id": "U_0099"}, raw)


def test_stage_four_mock_provider_and_fallback(
    tmp_path: Path,
) -> None:
    utterances = [
        make_utterance("U_0001", 0, 5000, "عشان كده البداية", rms=0.6),
        make_utterance(
            "U_0002",
            5500,
            12000,
            "النقطة الأساسية",
            rms=0.9,
            pause_after_ms=600,
            pitch_variance=0.4,
        ),
        make_utterance("U_0003", 13000, 28000, "التفاصيل الكاملة", rms=0.8, pause_after_ms=700),
        make_utterance("U_0004", 29000, 44000, "الخاتمة القوية", rms=0.7, pause_after_ms=500),
        make_utterance("U_0005", 45000, 52000, "غير مدفوع", rms=0.4),
    ]
    manifest = make_manifest(utterances)

    class FakeProvider:
        name = "mock"

        def propose_candidates(self, window):
            from qatta.stages.s04_candidates.llm import ProviderResult

            proposal = dict(_HONEST_PROPOSAL)
            proposal["broll"] = [
                {
                    "offset_sec": 0.5,
                    "duration_sec": 2.0,
                    "search_query": "x",
                    "overlay_type": "TEXT_CARD",
                }
            ]
            assert any(line["line"].startswith("[U_") for line in window.utterances)
            return ProviderResult(
                proposals=[
                    proposal,
                    {
                        "start_u_id": "U_0099",
                        "end_u_id": "U_0010",
                        "archetype": "HOT_TAKE",
                    },  # invalid
                    proposal,  # duplicate -> dedupe
                ],
                provider_name="mock",
            )

    result = run_candidates_stage(manifest, make_settings(tmp_path), provider=FakeProvider())
    assert len(result.candidates) == 1  # 1 valid, 1 invalid, 1 dup
    candidate = result.candidates[0]
    assert candidate.start_ms == 5500  # derived from U_0002, not the LLM
    assert candidate.broll_cues[0].trigger_ms == 5500 + 500
    # Scaffold gates: NOT yet vetted (pending s05).
    assert candidate.veto_gates.rejection_reason == "pending_s05_ranking"
    assert candidate.veto_gates.passed_all is False


def test_stage_four_fallback_provider_actionable(
    tmp_path: Path,
) -> None:
    utterances = [
        make_utterance(f"U_{i:04d}", i * 6000, i * 6000 + 5000, f"نص {i}") for i in range(1, 13)
    ]
    # 12 utterances × ~6 s ≈ 72 s → fallback should emit 28–58 s spans.
    manifest = make_manifest(utterances)

    class BrokenProvider:
        name = "broken"

        def propose_candidates(self, window):
            raise PipelineError("model offline")

    result = run_candidates_stage(
        manifest,
        make_settings(tmp_path),
        provider=BrokenProvider(),
    )
    assert result.candidates  # heuristic fallback produced real spans
    for candidate in result.candidates:
        assert 28.0 <= candidate.duration_sec <= 58.0 + 5  # span bounds
        assert candidate.evidence_log  # honest provenance recorded


def test_fallback_deterministic(tmp_path: Path) -> None:
    utterances = [
        make_utterance(f"U_{i:04d}", i * 6000, i * 6000 + 5000, f"نص {i}") for i in range(1, 13)
    ]

    class BrokenProvider:
        name = "broken"

        def propose_candidates(self, window):
            raise PipelineError("model offline")

    result1 = run_candidates_stage(
        make_manifest(utterances),
        make_settings(tmp_path),
        provider=BrokenProvider(),
    )
    result2 = run_candidates_stage(
        make_manifest(utterances),
        make_settings(tmp_path),
        provider=BrokenProvider(),
    )
    spans1 = [(c.start_u_id, c.end_u_id) for c in result1.candidates]
    spans2 = [(c.start_u_id, c.end_u_id) for c in result2.candidates]
    assert spans1 == spans2


# ---------------------------------------------------------------------------
# Cloud LLM gating (fail-closed)
# ---------------------------------------------------------------------------


def test_gemini_provider_gated_without_opt_in(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        llm_provider="gemini",
        llm_api_key="key",
        allow_cloud_apis=False,
    )
    from qatta.stages.s04_candidates.llm import select_provider

    with pytest.raises(PipelineError) as exc_info:
        select_provider(settings)
    assert "ALLOW_CLOUD_APIS" in str(exc_info.value)


def test_openai_provider_roundtrip_with_mock(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        llm_provider="openai_compatible",
        llm_api_key="sk-test",
        llm_base_url="http://llm.test/v1",
        allow_cloud_apis=True,
        llm_model="gpt-x",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"candidates": [_HONEST_PROPOSAL]})}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    from qatta.stages.s04_candidates.llm import select_provider

    provider = select_provider(settings, client=client)
    assert provider.name == "openai_compatible"

    utterances = [
        make_utterance(f"U_{i:04d}", i * 5000, i * 5000 + 3000, f"نص {i}") for i in range(1, 10)
    ]
    raw = raw_index(utterances)
    window = WindowPayload(
        window_index=0,
        utterances=[raw[u.u_id] for u in utterances],
    )
    result = provider.propose_candidates(window)
    assert result.provider_name == "openai_compatible"
    normalized = validate_proposal(result.proposals[0], raw)
    assert normalized["start_u_id"] == "U_0002"
    client.close()


def test_ollama_provider_roundtrip_with_mock(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/chat")
        body = json.loads(request.content)
        assert body["format"] == "json"
        assert body["stream"] is False
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps({"candidates": [_HONEST_PROPOSAL]})}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider(
        model="qwen2.5:7b-instruct",
        base_url="http://127.0.0.1:11434/v1",
        client=client,
    )
    utterances = [
        make_utterance(f"U_{i:04d}", i * 5000, i * 5000 + 3000, f"نص {i}") for i in range(1, 10)
    ]
    raw = raw_index(utterances)
    result = provider.propose_candidates(WindowPayload(0, [raw[u.u_id] for u in utterances]))
    assert validate_proposal(result.proposals[0], raw)["start_u_id"] == ("U_0002")
    client.close()


# ---------------------------------------------------------------------------
# Gate 1: Arabic dangling-context detector + auto-healer
# ---------------------------------------------------------------------------


def test_is_dangling_arabic_connectors() -> None:
    assert is_dangling(make_utterance("U_0001", 0, 1000, "عشان كده مشكلة"))
    assert is_dangling(make_utterance("U_0002", 0, 1000, "النقطة التانية"))
    assert is_dangling(make_utterance("U_0003", 0, 1000, "زي ما قلتلك"))
    assert is_dangling(make_utterance("U_0004", 0, 1000, "هو لما يقولك"))
    assert is_dangling(make_utterance("U_0005", 0, 1000, "و ده اللي قلته"))
    assert not is_dangling(make_utterance("U_0006", 0, 1000, "في البداية"))
    assert not is_dangling(make_utterance("U_0007", 0, 1000, "Today we will begin"))


def test_heal_shifts_start_back_one_utterance(tmp_path: Path) -> None:
    from qatta.stages.s05_ranking.scorer import GateContext

    utterances = [
        make_utterance("U_0001", 0, 4000, "مقدمة كاملة عن المشروع"),
        make_utterance("U_0002", 4500, 9000, "عشان كده خلينا نبدأ بالفكرة"),
        make_utterance("U_0003", 9500, 13000, "النقطة اللي بعدها", pause_after_ms=400),
        make_utterance("U_0004", 14000, 19000, "الخاتمة العملية", pause_after_ms=500),
    ]
    settings = make_settings(tmp_path)
    gate_ctx = GateContext(make_manifest(utterances), settings)
    proposal = make_candidate("c1", "U_0002", "U_0004", 4500, 19000)
    healed, evidence, still = heal_dangling_context(
        make_manifest(utterances), proposal, gate_ctx, settings
    )
    assert still is False
    assert healed.start_u_id == "U_0001"
    assert healed.start_ms == 0  # snapped to U_0001's real start
    assert healed.duration_sec == pytest.approx(19000 / 1000)
    assert any("البوابة 1" in line for line in evidence)


def test_heal_flags_hook_remix_when_no_earlier_context(
    tmp_path: Path,
) -> None:
    from qatta.stages.s05_ranking.scorer import GateContext

    # EVERY utterance of the hypothetical clip starts with a connector,
    # and the clip begins at the video start: after two shifts there is
    # still no clean opening, so the healer must flag a HookRemix
    # instead of silently shipping a dangling opening.
    utterances = [
        make_utterance("U_0001", 0, 4000, "عشان كده المشكلة..."),
        make_utterance("U_0002", 4500, 9000, "زي ما قلتلك تاني", pause_after_ms=500),
        make_utterance("U_0003", 9500, 14000, "نقطة واضحة بدون ربط"),
    ]
    settings = make_settings(tmp_path)
    gate_ctx = GateContext(make_manifest(utterances), settings)
    proposal = make_candidate("c1", "U_0001", "U_0003", 0, 14000)
    healed, _evidence, _still = heal_dangling_context(
        make_manifest(utterances), proposal, gate_ctx, settings
    )
    assert healed.hook_remix.enabled is True
    assert healed.hook_remix.hook_u_id == "U_0003"  # deepest in-clip hook
    bridge = healed.hook_remix.ai_bridge_text or ""
    assert 0 < len(bridge) <= 60  # ≤ ~2 s of Arabic speech
    assert healed.hook_remix.context_preserved is False


# ---------------------------------------------------------------------------
# Gate 2 + Gate 3
# ---------------------------------------------------------------------------


def full_manifest():
    utterances = [
        make_utterance("U_0001", 0, 5000, "مقدمة قوية", rms=0.7, pause_after_ms=600),
        make_utterance(
            "U_0002",
            5600,
            11000,
            "النقطة الأساسية",
            rms=0.9,
            pause_after_ms=700,
            pitch_variance=0.5,
        ),
        make_utterance(
            "U_0003",
            11700,
            17000,
            "التفاصيل اللي بعدها",
            rms=0.6,
            pause_after_ms=800,
            pitch_variance=0.2,
        ),
        make_utterance("U_0004", 17800, 23000, "خاتمة قوية", rms=0.8, pause_after_ms=900),
        make_utterance("U_0005", 23900, 29000, "إضافة من القلب", rms=0.5, pause_after_ms=600),
        make_utterance("U_0006", 29600, 34000, "نقطة النهاية", rms=0.85, pause_after_ms=400),
    ]
    return make_manifest(utterances)


def test_boundaries_pass_on_real_pauses(tmp_path: Path) -> None:
    from qatta.stages.s05_ranking.scorer import GateContext

    settings = make_settings(tmp_path)
    manifest = full_manifest()
    gate_ctx = GateContext(manifest, settings)
    proposal = make_candidate("c1", "U_0002", "U_0004", 5600, 23000)
    healed, evidence, ok = heal_audio_boundaries(proposal, gate_ctx, settings)
    assert ok is True
    assert healed.start_ms == 5600 and healed.end_ms == 23000
    assert any("البوابة 2" in line for line in evidence)


def test_gate_three_rejects_short_clip(tmp_path: Path) -> None:
    from qatta.stages.s05_ranking.scorer import check_duration

    # U_0003..U_0004: boundaries clean (700/900 ms pauses) but only
    # 11.3 s — well below min_clip_sec=28.
    candidate = make_candidate("c_short", "U_0003", "U_0004", 11700, 23000)
    ok, evidence = check_duration(candidate, make_settings(tmp_path))
    assert ok is False
    assert any("البوابة 3" in line for line in evidence)


def test_stage_five_end_to_end_gates_and_scores(tmp_path: Path) -> None:
    manifest = full_manifest()
    manifest.candidates = [
        # 28.4 s span with clean pauses on both sides -> should pass.
        make_candidate("c_ok", "U_0002", "U_0006", 5600, 34000),
        # 11.3 s clean-boundary span -> passes gates 1-2, fails gate 3.
        make_candidate("c_short", "U_0003", "U_0004", 11700, 23000),
    ]
    result = run_ranking_stage(manifest, make_settings(tmp_path))
    ok_clip = next(c for c in result.candidates if c.clip_id == "c_ok")
    short_clip = next(c for c in result.candidates if c.clip_id == "c_short")
    assert ok_clip.veto_gates.passed_all is True
    assert 0.0 < ok_clip.cps.total_score <= 100.0
    assert any("البوابة 3" in line for line in short_clip.evidence_log)
    assert short_clip.veto_gates.passed_all is False
    assert short_clip.cps.total_score == 0.0
    assert ok_clip.cps.archetype == "STORY"
    # Winner ranking: the passing clip's positive score must precede the
    # zero-scored rejected clip.
    assert result.candidates[0].clip_id == "c_ok"


def test_stage_five_rejects_run_when_no_candidates(tmp_path) -> None:
    with pytest.raises(PipelineError):
        run_ranking_stage(full_manifest(), make_settings(tmp_path))


# ---------------------------------------------------------------------------
# CPS weight renormalization math
# ---------------------------------------------------------------------------


def test_cps_weights_sum_to_one_per_archetype() -> None:
    for archetype, weights in ARCHETYPE_WEIGHTS.items():
        assert pytest.approx(1.0) == sum(weights.values()), archetype


def test_cps_missing_visual_renormalizes_not_zeros() -> None:
    # All components at their cap-ish mean 10/10 with visual MISSING
    # must still land at 100/100 (renormalized), not 100*(1-w_visual).
    for archetype in ("STORY", "TACTICAL_INSIGHT", "HOT_TAKE"):
        without_visual, _weights = compute_cps(
            archetype,
            standalone_clarity=10.0,
            hook_strength=10.0,
            story_payoff=10.0,
            value_originality=10.0,
            audio_dynamics=10.0,
            visual_composition=None,
            boundary_precision=10.0,
        )
        assert without_visual == pytest.approx(100.0), archetype
        with_visual, weights = compute_cps(
            archetype,
            standalone_clarity=10.0,
            hook_strength=10.0,
            story_payoff=10.0,
            value_originality=10.0,
            audio_dynamics=10.0,
            visual_composition=10.0,
            boundary_precision=10.0,
        )
        assert with_visual == pytest.approx(100.0), archetype
        assert "visual_composition" in weights


def test_cps_missing_visual_never_counts_as_zero() -> None:
    # Zero-quality visual (measured) vs missing visual at 8/10 everything:
    # a measured 0/10 visual must PULL THE SCORE DOWN relative to missing.
    kwargs = dict(
        standalone_clarity=8.0,
        hook_strength=8.0,
        story_payoff=8.0,
        value_originality=8.0,
        audio_dynamics=8.0,
        boundary_precision=8.0,
    )
    missing, _ = compute_cps("STORY", visual_composition=None, **kwargs)
    zeros, _ = compute_cps("STORY", visual_composition=0.0, **kwargs)
    assert missing > zeros
    # And deltas reflect the renormalized weights, not 0-equals-missing.
    assert missing == pytest.approx(80.0)
    assert zeros < 80.0


def test_cps_unknown_archetype_rejected() -> None:
    with pytest.raises(PipelineError):
        compute_cps(
            "VIRAL_DUNK",
            standalone_clarity=5,
            hook_strength=5,
            story_payoff=5,
            value_originality=5,
            audio_dynamics=5,
            visual_composition=None,
            boundary_precision=5,
        )
