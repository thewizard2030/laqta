"""Unit tests for qatta.core.schema, qatta.core.config, qatta.core.pipeline.

Verifies (task 5):
- Serialization / deserialization round trips through Pydantic v2 and the
  atomic manifest file (including all nested models with defaults).
- Strict validation: bad u_id formats, reversed timing, unknown literal
  values, extra fields, inconsistent duration_sec, failed gates without
  rejection reason, disabled hook remix payload.
- Stage caching: registered stages execute once; second invocation is
  skipped via completed_stages; force=True re-executes; unregistered stages
  raise clear errors; manifests persist across orchestrator instances.
- Config: env-prefixed overrides, clip-duration bounds (28/58, cap 180),
  fail-closed cloud backend gating.
"""

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineError, PipelineOrchestrator
from qatta.core.schema import (
    AtomicUtterance,
    BrollCue,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    MonetizationMeta,
    QattaManifest,
    VetoGates,
)


def _make_utterance(u_id: str, start_ms: int, end_ms: int) -> AtomicUtterance:
    return AtomicUtterance(
        u_id=u_id,
        start_ms=start_ms,
        end_ms=end_ms,
        text="مثال نصي mixed history 2024",
        words=[
            {
                "word": "مثال",
                "start_ms": start_ms,
                "end_ms": start_ms + 200,
                "confidence": 0.9,
                "is_latin": False,
            },
            {
                "word": "history",
                "start_ms": start_ms + 200,
                "end_ms": start_ms + 400,
                "confidence": 0.8,
                "is_latin": True,
            },
        ],
    )


def _make_candidate(
    clip_id: str = "clip_0001",
    *,
    passed: bool = True,
    archetype: str = "STORY",
    with_monetization: bool = True,
    start_ms: int = 1000,
    end_ms: int = 31_000,
) -> ClipCandidate:
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=start_ms,
        end_ms=end_ms,
        duration_sec=(end_ms - start_ms) / 1000.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.1,
            passed_all=passed,
            rejection_reason=None if passed else "starts mid-sentence",
        ),
        cps=CPSBreakdown(
            total_score=72.5,
            archetype=archetype,  # type: ignore[arg-type]
            standalone_clarity=8.0,
            hook_strength=9.0,
            story_payoff=7.0,
            value_originality=6.5,
            audio_dynamics=7.5,
            visual_composition=None,
            boundary_precision=8.5,
        ),
        hook_remix=HookRemixVariant(enabled=False),
        broll_cues=[
            BrollCue(
                trigger_ms=5000,
                duration_ms=3000,
                search_query="dollar bill macro",
                overlay_type="STOCK_VIDEO",
            )
        ],
        monetization=MonetizationMeta(
            visual_transformation_ratio=0.35,
            seamless_loop_score=0.82,
            pinned_comment_cta="اشترك وقناة كاملة على الرابط",
            curiosity_titles=["ما لم يخبرك به أحد"],
            ypp_safe=True,
        )
        if with_monetization
        else None,
        evidence_log=["hook strength from first-utterance pause 1200ms"],
        rendered_paths={},
    )


def _make_manifest(tmp_path: Path) -> QattaManifest:
    return QattaManifest(
        project_id="proj_test",
        source_path=str(tmp_path / "source.mp4"),
        duration_sec=120.5,
        language_profile="ar-EG-mixed",
        completed_stages=["import"],
        atomic_utterances=[
            _make_utterance("U_0001", 0, 4500),
            _make_utterance("U_0002", 5000, 9000),
        ],
        candidates=[_make_candidate()],
    )


# ----------------------------------------------------------------------
# Serialization round trips
# ----------------------------------------------------------------------
def test_manifest_roundtrip_full_payload(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path)
    data = json.loads(manifest.model_dump_json())
    restored = QattaManifest.model_validate(data)

    assert restored == manifest
    # Defaults were applied where absent
    assert restored.atomic_utterances[0].speaker == "SPEAKER_00"
    assert restored.atomic_utterances[0].pause_after_ms == 0
    assert restored.candidates[0].rendered_paths == {}
    assert restored.candidates[0].monetization is not None
    assert restored.atomic_utterances[0].words[1].is_latin is True
    assert restored.utterance_index()["U_0002"].start_ms == 5000


def test_manifest_tolerance_of_missing_defaults(tmp_path: Path) -> None:
    manifest = _make_manifest(tmp_path)
    raw = json.loads(manifest.model_dump_json())
    raw["atomic_utterances"][0]["words"] = []
    raw["candidates"][0]["broll_cues"] = []
    raw["candidates"][0]["evidence_log"] = []
    raw["candidates"][0]["monetization"] = None
    raw["audio_16k_path"] = None
    restored = QattaManifest.model_validate(raw)
    assert restored.atomic_utterances[0].words == []


# ----------------------------------------------------------------------
# Strict validation
# ----------------------------------------------------------------------
def test_invalid_u_id_rejected() -> None:
    with pytest.raises(ValidationError):
        AtomicUtterance(
            u_id="SEG-1",  # wrong format
            start_ms=0,
            end_ms=1000,
            text="x",
        )


def test_reversed_timing_rejected() -> None:
    with pytest.raises(ValidationError):
        AtomicUtterance(u_id="U_0001", start_ms=2000, end_ms=1000, text="x")


def test_unknown_archetype_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_candidate(archetype="VIRAL_SLAM_DUNK")


def test_inconsistent_duration_rejected(tmp_path: Path) -> None:
    base = _make_candidate()
    payload = base.model_dump()
    payload["duration_sec"] = 5.0  # inconsistent with (end_ms - start_ms)/1000
    with pytest.raises(ValidationError):
        ClipCandidate.model_validate(payload)


def test_extra_fields_rejected() -> None:
    data = json.loads(_make_manifest(Path("/tmp")).model_dump_json())
    data["total guesses"] = 42
    with pytest.raises(ValidationError):
        QattaManifest.model_validate(data)


def test_vetoed_gate_requires_reason() -> None:
    with pytest.raises(ValidationError):
        VetoGates(
            dangling_context=True,
            clean_audio_boundaries=False,
            crosstalk_ratio=0.9,
            passed_all=False,
            rejection_reason=None,
        )

    # A failed gate WITH a reason is valid; a passing gate needs none.
    VetoGates(
        dangling_context=True,
        clean_audio_boundaries=False,
        crosstalk_ratio=0.9,
        passed_all=False,
        rejection_reason="starts mid-sentence",
    )


def test_hook_remix_requires_payload_when_enabled() -> None:
    with pytest.raises(ValidationError):
        HookRemixVariant(enabled=True)


def test_enable_hook_remix_payload_valid(tmp_path: Path) -> None:
    remix = HookRemixVariant(
        enabled=True,
        hook_u_id="U_0003",
        source_start_ms=60_000,
        source_end_ms=65_000,
        ai_bridge_text="قبل ما نكمل، عندي نقطة مهمة",
        context_preserved=False,
    )
    assert remix.enabled is True
    assert remix.hook_u_id == "U_0003"


def test_manifest_duplicate_stage_rejected() -> None:
    data = json.loads(_make_manifest(Path("/tmp")).model_dump_json())
    data["completed_stages"].append("import")
    with pytest.raises(ValidationError):
        QattaManifest.model_validate(data)


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
def test_default_settings() -> None:
    s = QattaSettings(_env_file=None)
    assert s.transcription_backend == "local_turbo"
    assert s.min_clip_sec == 28
    assert s.max_clip_sec == 58
    assert (s.min_clip_sec < s.max_clip_sec) is True
    assert not s.backend_is_gated()


def test_env_overrides_clip_bounds(monkeypatch) -> None:
    monkeypatch.setenv("QATTA_MIN_CLIP_SEC", "35")
    monkeypatch.setenv("QATTA_MAX_CLIP_SEC", "180")
    s = QattaSettings()
    assert s.min_clip_sec == 35
    assert s.max_clip_sec == 180  # configurable up to 180
    assert s.video_max_clip_sec == 180


def test_max_clip_upper_cap_enforced() -> None:
    with pytest.raises(ValidationError):
        QattaSettings(max_clip_sec=300, video_max_clip_sec=180)


def test_min_clip_must_be_lt_max() -> None:
    with pytest.raises(ValidationError):
        QattaSettings(min_clip_sec=60, max_clip_sec=58)


def test_cloud_backend_gated_by_default() -> None:
    s = QattaSettings(
        transcription_backend="groq_api",
        allow_cloud_apis=False,
        _env_file=None,
    )
    assert s.backend_is_gated() is True
    assert not s.cloud_backend_permitted("groq_api")


def test_opt_in_cloud_backend_permitted(monkeypatch) -> None:
    monkeypatch.setenv("QATTA_ALLOW_CLOUD_APIS", "true")
    monkeypatch.setenv("QATTA_GROQ_API_KEY", "test-key-not-real")
    s = QattaSettings(
        transcription_backend="groq_api",
        groq_api_key="test-key-not-real",
        allow_cloud_apis=True,
    )
    assert s.backend_is_gated() is False


def test_youtube_ingestion_disabled_by_default() -> None:
    s = QattaSettings(
        transcription_backend="youtube_subs_first",
        enable_url_ingestion=False,
        _env_file=None,
    )
    assert s.enable_url_ingestion is False  # PRD FR-12: disabled by default
    assert s.backend_is_gated() is True


def test_arabish_prompt_default_present() -> None:
    s = QattaSettings(_env_file=None)
    assert s.arabish_initial_prompt is True
    assert len(s.arabish_prompt_text) > 10


def test_pass2_padding_constant() -> None:
    from qatta.core.config import PASS2_PADDING_MS

    assert PASS2_PADDING_MS == 3000


# ----------------------------------------------------------------------
# Pipeline orchestrator: atomic manifest + stage caching
# ----------------------------------------------------------------------
@pytest.fixture
def settings(tmp_path: Path) -> QattaSettings:
    return QattaSettings(data_dir=tmp_path / "data", _env_file=None)


@pytest.fixture
def sample_media(tmp_path: Path) -> Path:
    """Generate a tiny 2-second media file so ffprobe can measure it."""
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg unavailable for fixture generation")
    path = tmp_path / "sample_media.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=160x120:rate=5",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-t",
            "2",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _noop_stage(manifest: QattaManifest) -> QattaManifest:
    manifest.audio_16k_path = manifest.source_path  # an honest no-op marker
    return manifest


def test_orchestrator_initializes_manifest_from_media(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    orch = PipelineOrchestrator(
        project_id="proj_probe", source_path=sample_media, settings=settings
    )
    assert orch.manifest.duration_sec == pytest.approx(2.0, abs=0.2)
    assert orch.manifest.completed_stages == []
    assert orch.manifest.project_id == "proj_probe"
    assert (settings.manifest_path("proj_probe")).is_file()


def test_orchestrator_requires_existing_source(tmp_path: Path, settings: QattaSettings) -> None:
    with pytest.raises(PipelineError):
        PipelineOrchestrator(
            project_id="proj_missing",
            source_path=tmp_path / "no-such.mp4",
            settings=settings,
        )


def test_orchestrator_missing_binary_clear_error(
    tmp_path: Path, settings: QattaSettings, monkeypatch
) -> None:
    settings.ffprobe_timeout_seconds = 5.0
    missing_source = tmp_path / "x.mp4"
    missing_source.write_bytes(b"")  # exists, but ffprobe is unavailable
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    with pytest.raises(PipelineError) as exc_info:
        PipelineOrchestrator(
            project_id="proj_no_ff",
            source_path=missing_source,
            settings=settings,
        )
    assert "ffprobe" in str(exc_info.value)


def test_stage_runs_once_then_cached(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    orch = PipelineOrchestrator(
        project_id="proj_cache", source_path=sample_media, settings=settings
    )
    calls = []

    @orch.stage("audio_16k")
    def audio_stage(manifest: QattaManifest) -> QattaManifest:
        calls.append(1)
        manifest.audio_16k_path = str(Path(manifest.source_path).with_suffix(".wav"))
        return manifest

    r1 = orch.run_stage("audio_16k")
    assert r1 == {"stage": "audio_16k", "executed": True}
    assert len(calls) == 1
    assert "audio_16k" in orch.manifest.completed_stages

    # Second invocation without force: skipped (cached artifact reuse)
    r2 = orch.run_stage("audio_16k")
    assert r2["executed"] is False
    assert len(calls) == 1

    # force=True explicitly re-runs
    r3 = orch.run_stage("audio_16k", force=True)
    assert r3["executed"] is True
    assert len(calls) == 2


def test_stage_cached_state_persists_across_instances(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    """Cache must survive process restart: a NEW orchestrator instance sees
    the completed stage in the persisted manifest; unregistered stage names
    raise honest errors."""
    orch1 = PipelineOrchestrator(
        project_id="proj_persist", source_path=sample_media, settings=settings
    )
    orch1.stage("audio_16k")(_noop_stage)
    orch1.run_stage("audio_16k")

    orch2 = PipelineOrchestrator(
        project_id="proj_persist", source_path=sample_media, settings=settings
    )
    assert "audio_16k" in orch2.manifest.completed_stages
    orch2.stage("audio_16k")(_noop_stage)
    report = orch2.run_stage("audio_16k")
    assert report["executed"] is False

    with pytest.raises(PipelineError) as exc_info:
        orch2.run_stage("never_registered")
    assert "never_registered" in str(exc_info.value)


def test_atomic_save_leaves_no_temp_files(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    orch = PipelineOrchestrator(
        project_id="proj_atomic", source_path=sample_media, settings=settings
    )
    orch.stage("audio_16k")(_noop_stage)
    orch.run_stage("audio_16k")
    siblings = list(orch.manifest_path.parent.iterdir())
    assert all(not p.name.startswith(".qatta_manifest.json.tmp") for p in siblings)


def test_corrupt_manifest_fails_loudly(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    orch = PipelineOrchestrator(
        project_id="proj_corrupt", source_path=sample_media, settings=settings
    )
    orch.manifest_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(PipelineError) as exc_info:
        PipelineOrchestrator(project_id="proj_corrupt", source_path=sample_media, settings=settings)
    assert "not valid JSON" in str(exc_info.value)


def test_stage_must_return_manifest(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    orch = PipelineOrchestrator(project_id="proj_type", source_path=sample_media, settings=settings)
    orch.stage("bad_stage")(lambda manifest: {"nope": True})
    with pytest.raises(PipelineError) as exc_info:
        orch.run_stage("bad_stage")
    assert "QattaManifest" in str(exc_info.value)


def test_transcription_stage_gated_for_cloud(
    tmp_path: Path, settings: QattaSettings, sample_media: Path
) -> None:
    """Fail-closed: cloud backends must not run without explicit opt-in."""
    settings.transcription_backend = "groq_api"
    orch = PipelineOrchestrator(project_id="proj_gate", source_path=sample_media, settings=settings)
    orch.stage("transcribe_pass1")(lambda m: m)
    with pytest.raises(PipelineError) as exc_info:
        orch.run_stage("transcribe_pass1")
    assert "opt-in" in str(exc_info.value)
    # And the stage was NOT marked complete (nothing pretended to run).
    assert "transcribe_pass1" not in orch.manifest.completed_stages
