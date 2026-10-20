"""Integration and Unification tests for Laqta Core Pipeline + FastAPI Backend.

Verifies:
1. PipelineOrchestrator loads and registers all stages (s01..s06).
2. Manifest-to-SQLite synchronization bridge accurately projects utterances,
   CPS breakdowns, and candidates into SQLite.
3. FastAPI endpoints GET /api/projects/{id}/manifest and /utterances return valid data.
4. JobManager correctly accepts and executes unified pipeline jobs.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.repository import (
    CandidateRepository,
    ProjectRepository,
    RenderRepository,
)
from app.main import app
from app.schemas.jobs import JobType
from app.services.bridge.manifest_sync import sync_manifest_to_db
from qatta.core.config import QattaSettings
from qatta.core.pipeline import PipelineOrchestrator
from qatta.core.schema import (
    AtomicUtterance,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
    WordToken,
)
from qatta.stages.s01_ingest import ingestor
from qatta.stages.s02_transcript import fast_pass, fine_pass
from qatta.stages.s03_multimodal import analyzer
from qatta.stages.s04_candidates import generator
from qatta.stages.s05_ranking import scorer
from qatta.stages.s06_render import renderer


def test_pipeline_orchestrator_registers_all_stages(tmp_path: Path):
    """Verify all 7 stages register on PipelineOrchestrator without error."""
    dummy_wav = tmp_path / "dummy.wav"
    dummy_wav.write_bytes(
        b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )

    manifest = QattaManifest(
        project_id="proj_stages_check",
        source_path=str(dummy_wav),
        duration_sec=10.0,
    )
    manifest_file = tmp_path / "qatta_manifest.json"
    manifest_file.write_text(manifest.model_dump_json(), encoding="utf-8")

    orch = PipelineOrchestrator(
        project_id="proj_stages_check",
        work_dir=tmp_path,
        settings=QattaSettings(),
    )
    ingestor.register(orch)
    fast_pass.register(orch)
    fine_pass.register(orch)
    analyzer.register(orch)
    generator.register(orch)
    scorer.register(orch)
    from qatta.stages.s05b_section_fetch import section_fetch

    section_fetch.register(orch)
    renderer.register(orch)

    stages = orch._stage_functions.keys()
    assert "s01_ingest" in stages
    assert "s02_transcript" in stages
    assert "s02b_fine_alignment" in stages
    assert "s03_multimodal" in stages
    assert "s04_candidates" in stages
    assert "s05_ranking" in stages
    assert "s05b_section_fetch" in stages
    assert "s06_render" in stages


def test_manifest_sync_bridge_to_sqlite(tmp_path: Path):
    """Verify sync_manifest_to_db updates media, transcripts, and candidates in SQLite."""
    test_db = tmp_path / "test_sync.db"
    repo = ProjectRepository(db_path=test_db)
    cand_repo = CandidateRepository(db_path=test_db)
    render_repo = RenderRepository(db_path=test_db)

    # Setup project and media in SQLite
    proj = repo.create_project("Sync Test Project")
    media = repo.create_media_asset(
        project_id=proj.id,
        safe_path=str(tmp_path / "input.mp4"),
        original_name="input.mp4",
        size_bytes=1000,
        duration_ms=20000,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
    )

    # Create mock manifest with utterances and candidates
    words = [
        WordToken(word="ذكاء", start_ms=1000, end_ms=1500, confidence=0.95, is_latin=False),
        WordToken(word="AI", start_ms=1600, end_ms=2000, confidence=0.98, is_latin=True),
    ]
    u1 = AtomicUtterance(
        u_id="U_0001",
        start_ms=1000,
        end_ms=5000,
        text="ذكاء AI ممتاز",
        words=words,
    )
    u2 = AtomicUtterance(
        u_id="U_0002",
        start_ms=6000,
        end_ms=12000,
        text="الخلاصة هنا مهمة",
    )
    cand = ClipCandidate(
        clip_id="clip_test_01",
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=1000,
        end_ms=12000,
        duration_sec=11.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
            rejection_reason=None,
        ),
        cps=CPSBreakdown(
            total_score=85.5,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=85.0,
            hook_strength=90.0,
            story_payoff=80.0,
            value_originality=85.0,
            audio_dynamics=82.0,
            visual_composition=None,
            boundary_precision=95.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
        draft_curiosity_titles=["سر الذكاء الاصطناعي"],
        evidence_log=["Clean opening pause", "High pitch variance on hook"],
    )

    manifest = QattaManifest(
        project_id=proj.id,
        source_path=str(tmp_path / "input.mp4"),
        duration_sec=20.0,
        video_width=1920,
        video_height=1080,
        atomic_utterances=[u1, u2],
        candidates=[cand],
    )

    # Execute sync bridge
    sync_manifest_to_db(
        manifest=manifest,
        project_id=proj.id,
        repo=repo,
        candidates_repo=cand_repo,
        renders_repo=render_repo,
    )

    # Verify transcripts created
    transcripts = repo.list_media_transcripts(media.id)
    assert len(transcripts) == 1
    t = transcripts[0]
    assert "ذكاء AI" in t.text
    assert t.word_timestamps_available is True
    assert t.timing_granularity == "word"

    # Verify candidates created
    candidates = cand_repo.list_media_candidates(media.id)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.id == "clip_test_01"
    assert c.cps == 85.5
    assert c.status == "suggested"
    assert c.title == "سر الذكاء الاصطناعي"
    span_ids = json.loads(c.transcript_span_ids_json)
    assert span_ids == ["U_0001", "U_0002"]


def test_api_manifest_and_utterances_endpoints(tmp_path: Path):
    """Verify GET /api/projects/{id}/manifest and /utterances return valid JSON."""
    client = TestClient(app)

    # Create project via API
    res = client.post("/api/projects", json={"name": "API Manifest Test"})
    assert res.status_code == 201
    proj_id = res.json()["id"]

    # Before manifest exists -> 404
    res_m = client.get(f"/api/projects/{proj_id}/manifest")
    assert res_m.status_code == 404

    # Utterances returns empty list before manifest exists
    res_u = client.get(f"/api/projects/{proj_id}/utterances")
    assert res_u.status_code == 200
    assert res_u.json() == []

    # Write a test manifest into the project's data directory
    from app.core.config import settings

    proj_dir = settings.get_project_dir(proj_id)
    u = AtomicUtterance(u_id="U_0001", start_ms=0, end_ms=2000, text="تجربة المنفست")
    manifest = QattaManifest(
        project_id=proj_id,
        source_path="/tmp/test.mp4",
        duration_sec=2.0,
        atomic_utterances=[u],
    )
    (proj_dir / "qatta_manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    # Now GET manifest returns 200 and valid JSON
    res_m2 = client.get(f"/api/projects/{proj_id}/manifest")
    assert res_m2.status_code == 200
    data = res_m2.json()
    assert data["project_id"] == proj_id
    assert data["duration_sec"] == 2.0

    # GET utterances returns the atomic utterances
    res_u2 = client.get(f"/api/projects/{proj_id}/utterances")
    assert res_u2.status_code == 200
    utts = res_u2.json()
    assert len(utts) == 1
    assert utts[0]["u_id"] == "U_0001"
    assert utts[0]["text"] == "تجربة المنفست"


def test_job_type_enum_supports_pipeline():
    """Verify JobType includes pipeline and multimodal job types."""
    assert JobType.PIPELINE == "pipeline"
    assert JobType.MULTIMODAL == "multimodal"
    assert JobType.CANDIDATE_GENERATION == "candidate_generation"
