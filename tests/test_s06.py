"""Tests for Stage s06_reframe_subs: Permissive CV Reframing & Arabic BiDi ASS Subtitles."""

from pathlib import Path

from qatta.core.config import QattaSettings
from qatta.core.schema import (
    AtomicUtterance,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
    WordToken,
)
from qatta.stages.s06_reframe_subs import run_reframe_subs_stage
from qatta.stages.s06_reframe_subs.arabic_ass import (
    FSI,
    PDI,
    RLM,
    ArabicBiDiShaper,
    ASSCaptionConfig,
    CaptionLine,
    generate_dynamic_ass,
    group_words_into_lines,
    hex_to_ass_color,
    ms_to_ass_time,
)
from qatta.stages.s06_reframe_subs.camera_solver import (
    BoundingBox,
    FaceDetection,
    FrameObservation,
    LayoutMode,
    LayoutStateMachine,
    SceneAwareHysteresisSolver,
    partition_clip_into_shots,
)

# ---------------------------------------------------------------------------
# ArabicBiDiShaper & ASS Subtitle Tests
# ---------------------------------------------------------------------------


def test_arabic_bidi_shaper_wraps_mixed_arabish_sample():
    """Verify ArabicBiDiShaper properly wraps mixed strings with RLM and FSI/PDI isolates."""
    sample = "عملنا deploy للـ API في 3 أيام"
    shaped = ArabicBiDiShaper.shape_line(sample)

    expected = f"{RLM}عملنا {FSI}deploy{PDI} للـ {FSI}API{PDI} في {FSI}3{PDI} أيام"
    assert shaped == expected

    # Verify individual Unicode markers
    assert shaped.startswith(RLM)
    assert f"{FSI}deploy{PDI}" in shaped
    assert f"{FSI}API{PDI}" in shaped
    assert f"{FSI}3{PDI}" in shaped


def test_arabic_bidi_shaper_pure_arabic_and_idempotency():
    """Verify pure Arabic strings receive RLM, and repeated shaping is idempotent."""
    pure_arabic = "مرحبا بكم في استوديو الذكاء الاصطناعي"
    shaped = ArabicBiDiShaper.shape_line(pure_arabic)
    assert shaped == f"{RLM}{pure_arabic}"

    # Idempotency check: shaping an already shaped string does not double-wrap
    reshaped = ArabicBiDiShaper.shape_line(shaped)
    assert reshaped == shaped


def test_arabic_bidi_shaper_technical_tokens():
    """Verify code tokens and hyphenated terms are cleanly isolated."""
    technical = "شغلنا v2.5 على Kubernetes و backend-api"
    shaped = ArabicBiDiShaper.shape_line(technical)
    assert f"{FSI}v2.5{PDI}" in shaped
    assert f"{FSI}Kubernetes{PDI}" in shaped
    assert f"{FSI}backend-api{PDI}" in shaped
    assert shaped.startswith(RLM)


def test_group_words_into_lines():
    """Verify word grouping enforces max_words and max_chars limits."""
    words = [
        WordToken(word="هذا", start_ms=0, end_ms=300, confidence=0.98, is_latin=False),
        WordToken(word="هو", start_ms=300, end_ms=500, confidence=0.97, is_latin=False),
        WordToken(word="مشروع", start_ms=500, end_ms=900, confidence=0.99, is_latin=False),
        WordToken(word="Laqta", start_ms=900, end_ms=1400, confidence=0.95, is_latin=True),
        WordToken(word="الجديد", start_ms=1400, end_ms=1800, confidence=0.99, is_latin=False),
        WordToken(word="تماماً", start_ms=1800, end_ms=2200, confidence=0.96, is_latin=False),
    ]

    # Max 3 words per line
    lines = group_words_into_lines(words, max_words=3, max_chars=30)
    assert len(lines) == 2
    assert len(lines[0].words) == 3
    assert len(lines[1].words) == 3
    assert lines[0].start_ms == 0
    assert lines[0].end_ms == 900
    assert lines[1].start_ms == 900
    assert lines[1].end_ms == 2200
    assert f"{FSI}Laqta{PDI}" in lines[1].shaped_text


def test_generate_dynamic_ass_content():
    """Verify generated ASS content has safe zone margin, styling, and active highlight tags."""
    words = [
        WordToken(word="عملنا", start_ms=1000, end_ms=1400, confidence=0.95, is_latin=False),
        WordToken(word="deploy", start_ms=1400, end_ms=1900, confidence=0.92, is_latin=True),
        WordToken(word="سريع", start_ms=1900, end_ms=2400, confidence=0.98, is_latin=False),
    ]
    lines = [
        CaptionLine(
            words=words,
            start_ms=1000,
            end_ms=2400,
            text="عملنا deploy سريع",
        )
    ]

    config = ASSCaptionConfig(
        play_res_x=1080,
        play_res_y=1920,
        margin_v=420,
        highlight_color="#00FFFF",
    )
    ass_text = generate_dynamic_ass(lines, config)

    # Check script info & safe zone
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
    assert ",420,1" in ass_text  # MarginV=420

    # Check dialogue events count equals number of words (dynamic word-level highlight)
    dialogues = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogues) == 3

    # Check scale pop tag and highlight color
    assert r"\fscx110\fscy110" in ass_text
    # #00FFFF -> ASS &H00FFFF00& (cyan)
    assert "&H00FFFF00&" in ass_text

    # Each dialogue line must begin with RLM
    for d in dialogues:
        text_part = d.split(",", 9)[-1]
        assert text_part.startswith(RLM)


def test_ms_to_ass_time_and_hex_color():
    """Verify ASS time formatting and hex-to-ASS color conversion."""
    assert ms_to_ass_time(0) == "0:00:00.00"
    assert ms_to_ass_time(1520) == "0:00:01.52"
    assert ms_to_ass_time(65120) == "0:01:05.12"

    # White #FFFFFF -> &H00FFFFFF&
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF&"
    # Cyan #00FFFF -> &H00FFFF00&
    assert hex_to_ass_color("#00FFFF") == "&H00FFFF00&"
    # Gold #FFD700 -> &H0000D7FF&
    assert hex_to_ass_color("#FFD700") == "&H0000D7FF&"


# ---------------------------------------------------------------------------
# Camera Solver & Deadband Hysteresis Tests
# ---------------------------------------------------------------------------


def test_scene_aware_hysteresis_solver_deadband_lock():
    """Verify camera crop center holds completely steady (0% pan) inside the 15% deadband."""
    solver = SceneAwareHysteresisSolver(
        frame_width=1920,
        frame_height=1080,
        target_aspect_ratio=9 / 16,
        deadband_ratio=0.15,
    )

    # Initial position at frame center 0.50
    c0 = solver.update(timestamp_ms=0, target_x=0.50, is_scene_cut=True)
    assert c0 == 0.50

    # Deadband half-width is (w_crop * 0.15) / 2
    # w_crop = 607.5 / 1920 = ~0.3164 -> deadband_half = ~0.0237
    # Shift by 0.015 (within deadband)
    c1 = solver.update(timestamp_ms=200, target_x=0.515, is_scene_cut=False)
    assert c1 == 0.50, "Camera must remain 100% locked (0% pan) inside deadband."

    # Shift to opposite side by 0.018 (within deadband)
    c2 = solver.update(timestamp_ms=400, target_x=0.482, is_scene_cut=False)
    assert c2 == 0.50, "Camera must remain 100% locked inside deadband."

    # Speaker moves significantly outside deadband (to 0.70)
    c3 = solver.update(timestamp_ms=600, target_x=0.70, is_scene_cut=False)
    assert c3 > 0.50, "Camera must adjust toward target when exiting deadband."
    assert c3 < 0.70, "Camera trajectory must be smooth (not teleporting inside a shot)."


def test_scene_aware_hysteresis_solver_scene_cut_instant_snap():
    """Verify camera snaps instantly across a scene cut boundary with zero whip-pan."""
    solver = SceneAwareHysteresisSolver(
        frame_width=1920,
        frame_height=1080,
        target_aspect_ratio=9 / 16,
    )

    # Shot 1: speaker on the left side (0.25)
    solver.update(timestamp_ms=0, target_x=0.25, is_scene_cut=True)
    solver.update(timestamp_ms=200, target_x=0.25, is_scene_cut=False)
    solver.update(timestamp_ms=400, target_x=0.25, is_scene_cut=False)
    assert solver.current_center == 0.25

    # Shot 2 begins with a scene cut at t=1000ms: speaker is on the right side (0.80)
    snap_center = solver.update(timestamp_ms=1000, target_x=0.80, is_scene_cut=True)

    # Instant snap: camera center must immediately jump to target (clamped to max_center)
    expected_center = min(0.80, solver.max_center)
    assert snap_center == expected_center
    assert solver.current_center == expected_center

    # History is reset on cut
    assert len(solver.history) == 1
    assert solver.history[0] == (1000, expected_center)


def test_partition_clip_into_shots():
    """Verify scene cuts properly partition a clip into continuous shots."""
    cuts = [2000, 5000, 9000, 15000]
    # Clip from 3000 to 12000 ms
    shots = partition_clip_into_shots(
        clip_start_ms=3000,
        clip_end_ms=12000,
        scene_cuts_ms=cuts,
    )

    # Expected shots: [3000..5000], [5000..9000], [9000..12000]
    assert len(shots) == 3
    assert shots[0] == (3000, 5000)
    assert shots[1] == (5000, 9000)
    assert shots[2] == (9000, 12000)


# ---------------------------------------------------------------------------
# Layout State Machine Tests
# ---------------------------------------------------------------------------


def test_layout_state_machine_screenshare_pip():
    """Verify SCREENSHARE_PIP layout when >75% of frame is static content with corner face."""
    observations = [
        FrameObservation(
            timestamp_ms=0,
            faces=[
                FaceDetection(
                    bbox=BoundingBox(
                        x_min=0.85, y_min=0.80, x_max=0.98, y_max=0.95
                    ),  # area = 0.0195
                    is_speaking=True,
                )
            ],
            is_screen_share=True,
            static_content_ratio=0.85,
        ),
        FrameObservation(
            timestamp_ms=200,
            faces=[
                FaceDetection(
                    bbox=BoundingBox(x_min=0.85, y_min=0.80, x_max=0.98, y_max=0.95),
                    is_speaking=True,
                )
            ],
            is_screen_share=True,
            static_content_ratio=0.88,
        ),
    ]

    layout = LayoutStateMachine.classify_shot(observations)
    assert layout == LayoutMode.SCREENSHARE_PIP


def test_layout_state_machine_dual_split():
    """Verify DUAL_SPLIT layout when two active faces alternate speaking within 4 seconds."""
    observations = [
        FrameObservation(
            timestamp_ms=0,
            faces=[
                FaceDetection(
                    bbox=BoundingBox(x_min=0.1, y_min=0.2, x_max=0.4, y_max=0.6),
                    is_speaking=True,
                    face_id=0,
                ),
                FaceDetection(
                    bbox=BoundingBox(x_min=0.6, y_min=0.2, x_max=0.9, y_max=0.6),
                    is_speaking=False,
                    face_id=1,
                ),
            ],
        ),
        FrameObservation(
            timestamp_ms=2000,  # 2 seconds later (<= 4000ms)
            faces=[
                FaceDetection(
                    bbox=BoundingBox(x_min=0.1, y_min=0.2, x_max=0.4, y_max=0.6),
                    is_speaking=False,
                    face_id=0,
                ),
                FaceDetection(
                    bbox=BoundingBox(x_min=0.6, y_min=0.2, x_max=0.9, y_max=0.6),
                    is_speaking=True,
                    face_id=1,
                ),
            ],
        ),
    ]

    layout = LayoutStateMachine.classify_shot(observations, alternate_speaking_window_ms=4000)
    assert layout == LayoutMode.DUAL_SPLIT


def test_layout_state_machine_single_speaker_default():
    """Verify SINGLE_SPEAKER layout for standard solo speaker shots."""
    observations = [
        FrameObservation(
            timestamp_ms=0,
            faces=[
                FaceDetection(
                    bbox=BoundingBox(x_min=0.35, y_min=0.2, x_max=0.65, y_max=0.7),
                    is_speaking=True,
                    face_id=0,
                )
            ],
        ),
        FrameObservation(
            timestamp_ms=200,
            faces=[
                FaceDetection(
                    bbox=BoundingBox(x_min=0.35, y_min=0.2, x_max=0.65, y_max=0.7),
                    is_speaking=True,
                    face_id=0,
                )
            ],
        ),
    ]

    layout = LayoutStateMachine.classify_shot(observations)
    assert layout == LayoutMode.SINGLE_SPEAKER


# ---------------------------------------------------------------------------
# End-to-End Stage 06 Reframe & Subs Execution Test
# ---------------------------------------------------------------------------


def test_run_reframe_subs_stage_end_to_end(tmp_path: Path):
    """Verify run_reframe_subs_stage solves camera trajectories and writes .ass files."""
    words = [
        WordToken(word="عملنا", start_ms=1000, end_ms=1400, confidence=0.95, is_latin=False),
        WordToken(word="deploy", start_ms=1400, end_ms=1900, confidence=0.92, is_latin=True),
        WordToken(word="سريع", start_ms=1900, end_ms=2400, confidence=0.98, is_latin=False),
    ]

    utterance = AtomicUtterance(
        u_id="U_0001",
        start_ms=1000,
        end_ms=2400,
        speaker="SPEAKER_00",
        text="عملنا deploy سريع",
        words=words,
    )

    candidate = ClipCandidate(
        clip_id="clip_001",
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=1000,
        end_ms=5000,
        duration_sec=4.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=85.0,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=18.0,
            hook_strength=19.0,
            story_payoff=17.0,
            value_originality=16.0,
            audio_dynamics=15.0,
            boundary_precision=10.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
    )

    manifest = QattaManifest(
        project_id="proj_s06_test",
        source_path="/fake/media.mp4",
        duration_sec=10.0,
        atomic_utterances=[
            utterance,
            AtomicUtterance(
                u_id="U_0002",
                start_ms=2500,
                end_ms=5000,
                speaker="SPEAKER_00",
                text="للنسخة الجديدة من المشروع",
            ),
        ],
        candidates=[candidate],
        scene_cuts_ms=[3000],  # Scene cut inside candidate span
    )

    captions_dir = tmp_path / "captions"
    updated_manifest = run_reframe_subs_stage(
        manifest=manifest,
        captions_dir=captions_dir,
    )

    # 1. Check ASS file was written
    ass_path = captions_dir / "clip_001.ass"
    assert ass_path.is_file()
    ass_content = ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in ass_content
    assert "PlayResY: 1920" in ass_content
    assert f"{FSI}deploy{PDI}" in ass_content

    # 2. Check candidate rendered paths
    cand = updated_manifest.candidates[0]
    assert "ass_captions" in cand.rendered_paths
    assert cand.rendered_paths["ass_captions"] == str(ass_path.resolve())

    # 3. Check evidence log records shot decomposition
    assert any("s06_reframe_subs: Solved 2 shots" in line for line in cand.evidence_log)


def test_register_s06_orchestrator(tmp_path: Path):
    """Verify s06_reframe_subs registers with PipelineOrchestrator and executes cleanly."""
    from qatta.core.pipeline import PipelineOrchestrator
    from qatta.stages.s06_reframe_subs import register

    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"dummy")

    settings = QattaSettings(data_dir=tmp_path / "data")
    manifest = QattaManifest(
        project_id="proj_orch_s06",
        source_path=str(media_file),
        duration_sec=30.0,
    )
    manifest_path = settings.manifest_path("proj_orch_s06")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    orchestrator = PipelineOrchestrator(
        project_id="proj_orch_s06",
        settings=settings,
    )

    register(orchestrator)
    assert "s06_reframe_subs" in orchestrator._stage_functions

    res = orchestrator.run_stage("s06_reframe_subs")
    assert res["stage"] == "s06_reframe_subs"
    assert res["executed"] is True
    assert "s06_reframe_subs" in orchestrator.manifest.completed_stages

    # Second run is cached
    res2 = orchestrator.run_stage("s06_reframe_subs")
    assert res2["executed"] is False
    assert res2["skipped_cached"] is True
