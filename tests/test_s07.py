"""Tests for Stage s07_render_learn: YPP-Safe FFmpeg Shorts Renderer & Feedback Loop."""

import json
from pathlib import Path

import pytest

from qatta.core.config import QattaSettings
from qatta.core.schema import (
    AtomicUtterance,
    BrollCue,
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)
from qatta.stages.s06_reframe_subs.camera_solver import LayoutMode, ShotSegment
from qatta.stages.s07_render_learn import (
    ChannelProfile,
    ChannelProfileUpdater,
    FFmpegFilterGraphBuilder,
    PublishedClipRecord,
    PunchZoomInterval,
    build_hook_remix_command,
    build_render_command,
    compute_visual_transformation_ratio,
    detect_punch_in_zooms,
    escape_ffmpeg_filter_path,
    register,
    run_render_learn_stage,
)

# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------


def make_test_candidate(
    clip_id: str = "clip_01",
    start_ms: int = 1000,
    end_ms: int = 31000,
    hook_remix_enabled: bool = False,
    broll_cues: list[BrollCue] | None = None,
) -> ClipCandidate:
    """Construct a valid test candidate."""
    duration_sec = (end_ms - start_ms) / 1000.0
    return ClipCandidate(
        clip_id=clip_id,
        start_u_id="U_0001",
        end_u_id="U_0003",
        start_ms=start_ms,
        end_ms=end_ms,
        duration_sec=duration_sec,
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
        hook_remix=(
            HookRemixVariant(
                enabled=True,
                hook_u_id="U_0002",
                source_start_ms=15000,
                source_end_ms=17500,
                ai_bridge_text="شوف اللقطة دي",
            )
            if hook_remix_enabled
            else HookRemixVariant(enabled=False)
        ),
        broll_cues=broll_cues or [],
    )


# ---------------------------------------------------------------------------
# 1. FFmpeg FilterGraph Builder Tests
# ---------------------------------------------------------------------------


def test_escape_ffmpeg_filter_path():
    """Verify paths are escaped safely for FFmpeg filter syntax."""
    raw_path = r"C:\data\test [clips]:subtitles,part1.ass"
    escaped = escape_ffmpeg_filter_path(raw_path)
    assert r"\:" in escaped
    assert r"\," in escaped
    assert r"\[" in escaped
    assert r"\]" in escaped
    assert escaped == r"C\:/data/test \[clips\]\:subtitles\,part1.ass"


def test_filtergraph_single_speaker_with_punch_zoom():
    """Verify single speaker reframing with 1.12x punch-in zoom expressions."""
    builder = FFmpegFilterGraphBuilder(target_width=1080, target_height=1920)
    zooms = [PunchZoomInterval(start_sec=2.0, end_sec=5.0, zoom_factor=1.12, reason="audio_rms")]
    fg = builder.build_crop_filter(LayoutMode.SINGLE_SPEAKER, zooms=zooms)

    assert "crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)'" in fg
    assert "between(t,2.00,5.00)" in fg
    assert "iw/1.12" in fg
    assert "ih/1.12" in fg
    assert "scale=1080:1920" in fg


def test_filtergraph_dual_split_vstack():
    """Verify DUAL_SPLIT compiles into two crops stacked with vstack."""
    builder = FFmpegFilterGraphBuilder(target_width=1080, target_height=1920)
    fg = builder.build_crop_filter(LayoutMode.DUAL_SPLIT)

    assert "split=2[top_in][bot_in]" in fg
    assert "scale=1080:960[top_out]" in fg
    assert "scale=1080:960[bot_out]" in fg
    assert "[top_out][bot_out]vstack=inputs=2" in fg


def test_filtergraph_screenshare_pip_vstack():
    """Verify SCREENSHARE_PIP compiles into 60% top slide and 40% bottom speaker."""
    builder = FFmpegFilterGraphBuilder(target_width=1080, target_height=1920)
    fg = builder.build_crop_filter(LayoutMode.SCREENSHARE_PIP)

    # 60% of 1920 = 1152; 40% = 768
    assert "scale=1080:1152" in fg
    assert "scale=1080:768" in fg
    assert "[scr_out][fac_out]vstack=inputs=2" in fg


def test_filtergraph_broll_and_text_card_overlays():
    """Verify B-roll text callout cards are placed in upper half of the frame."""
    builder = FFmpegFilterGraphBuilder(target_width=1080, target_height=1920)
    cues = [
        BrollCue(
            trigger_ms=3000,
            duration_ms=4000,
            search_query="كود بايثون سريع",
            overlay_type="TEXT_CARD",
        )
    ]
    overlays = builder.build_broll_overlay_filter(
        broll_cues=cues,
        clip_start_ms=1000,
        clip_duration_sec=30.0,
    )
    assert len(overlays) == 1
    card = overlays[0]
    # Positioned at y=200 in upper half of 1920 frame
    assert "drawbox=x=120:y=200:w=840:h=160" in card
    assert "drawtext=text='كود بايثون سريع'" in card
    assert "between(t,2.00,6.00)" in card


def test_build_render_command_audio_loudnorm():
    """Verify assembled FFmpeg command contains loudnorm and proper encoding flags."""
    cmd = build_render_command(
        ffmpeg_bin="ffmpeg",
        source_path="/path/to/media.mp4",
        output_path="/path/to/out.mp4",
        start_sec=5.0,
        duration_sec=30.0,
        filtergraph="scale=1080:1920",
        audio_normalize=True,
        micro_silence_trim=True,
    )
    cmd_str = " ".join(cmd)
    assert "-ss 5.000" in cmd_str
    assert "-t 30.000" in cmd_str
    assert "-vf scale=1080:1920" in cmd_str
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in cmd_str
    assert "silenceremove=" in cmd_str
    assert "-c:v libx264" in cmd_str
    assert "-movflags +faststart" in cmd_str


def test_build_hook_remix_command():
    """Verify hook remix command builds dual-input concat with transition flash."""
    cmd = build_hook_remix_command(
        ffmpeg_bin="ffmpeg",
        source_path="/media/video.mp4",
        output_path="/out/clip_01_hook_remix.mp4",
        hook_start_sec=15.0,
        hook_duration_sec=2.5,
        body_start_sec=1.0,
        body_duration_sec=30.0,
        filtergraph_body="scale=1080:1920",
    )
    cmd_str = " ".join(cmd)
    assert "-filter_complex" in cmd_str
    assert "fade=t=out:st=2.35:d=0.15:c=white[v_hook]" in cmd_str
    assert "concat=n=2:v=1:a=1" in cmd_str
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in cmd_str


# ---------------------------------------------------------------------------
# 2. Punch Zoom & Visual Transformation Ratio Tests
# ---------------------------------------------------------------------------


def test_detect_punch_in_zooms_high_rms_and_climax():
    """Verify punch zooms are detected on audio_rms_norm > 0.80 and climax utterance."""
    candidate = make_test_candidate(start_ms=1000, end_ms=16000)
    utts = [
        AtomicUtterance(
            u_id="U_0001",
            start_ms=1000,
            end_ms=4000,
            text="مقدمة عادية",
            audio_rms_norm=0.45,
            pitch_variance=0.20,
        ),
        AtomicUtterance(
            u_id="U_0002",
            start_ms=5000,
            end_ms=9000,
            text="صوت عالي ومتحمس جداً!",
            audio_rms_norm=0.88,  # > 0.80 -> punch zoom
            pitch_variance=0.75,
        ),
        AtomicUtterance(
            u_id="U_0003",
            start_ms=10000,
            end_ms=15000,
            text="الخاتمة والذروة",
            audio_rms_norm=0.72,
            pitch_variance=0.95,  # Climax combined score
        ),
    ]

    zooms = detect_punch_in_zooms(candidate, utts, rms_threshold=0.80)
    assert len(zooms) >= 1
    # Check that high RMS utterance is included
    rms_zooms = [z for z in zooms if "rms" in z.reason]
    assert len(rms_zooms) == 1
    assert rms_zooms[0].start_sec == pytest.approx(4.0, abs=0.05)
    assert rms_zooms[0].end_sec == pytest.approx(8.0, abs=0.05)


def test_visual_transformation_ratio_and_ypp_safety():
    """Verify visual transformation ratio calculation and YPP demonetization guard."""
    candidate = make_test_candidate(start_ms=0, end_ms=30000)  # 30 seconds

    # Case 1: Low transformation (under 0.35 threshold)
    shots_simple = [
        ShotSegment(
            shot_index=0,
            start_ms=0,
            end_ms=30000,
            layout=LayoutMode.SINGLE_SPEAKER,
            crop_trajectory=[(0, 0.50), (30000, 0.50)],  # stationary center
        )
    ]
    zooms_small = [PunchZoomInterval(start_sec=2.0, end_sec=5.0)]  # 3s out of 30s = 0.10
    ratio_low = compute_visual_transformation_ratio(
        candidate=candidate,
        shots=shots_simple,
        zooms=zooms_small,
        broll_cues=[],
    )
    assert ratio_low == pytest.approx(0.10, abs=0.01)
    assert ratio_low < 0.35

    # Case 2: High transformation (split-screen + zooms + B-roll overlays >= 0.35)
    shots_split = [
        ShotSegment(
            shot_index=0,
            start_ms=0,
            end_ms=10000,  # 10s split screen
            layout=LayoutMode.DUAL_SPLIT,
        ),
        ShotSegment(
            shot_index=1,
            start_ms=10000,
            end_ms=30000,
            layout=LayoutMode.SINGLE_SPEAKER,
        ),
    ]
    cues = [
        BrollCue(
            trigger_ms=12000,
            duration_ms=6000,  # 6s b-roll
            search_query="overlay test",
            overlay_type="TEXT_CARD",
        )
    ]
    zooms = [PunchZoomInterval(start_sec=20.0, end_sec=26.0)]  # 6s zoom

    ratio_high = compute_visual_transformation_ratio(
        candidate=candidate,
        shots=shots_split,
        zooms=zooms,
        broll_cues=cues,
    )
    # 10s (layout) + 6s (broll) + 6s (zoom) = 22s / 30s = ~0.73
    assert ratio_high >= 0.70
    assert ratio_high >= 0.35


# ---------------------------------------------------------------------------
# 3. Channel Profile & Z-Score Feedback Loop Tests
# ---------------------------------------------------------------------------


def test_channel_profile_updater_csv_and_z_scores(tmp_path: Path):
    """Verify CSV analytics parsing and channel-normalized Z-score calculation."""
    csv_content = (
        "clip_id,archetype,hook_remix_used,stayed_to_watch_pct,avg_percentage_viewed\n"
        "clip_01,STORY,True,75.0,110.0\n"
        "clip_02,STORY,False,60.0,85.0\n"
        "clip_03,TACTICAL_INSIGHT,True,85.0,130.0\n"
        "clip_04,TACTICAL_INSIGHT,False,70.0,95.0\n"
        "clip_05,HOT_TAKE,False,50.0,70.0\n"
    )
    csv_path = tmp_path / "analytics.csv"
    csv_path.write_text(csv_content, encoding="utf-8")

    updater = ChannelProfileUpdater(learning_rate=0.15)
    records = updater.load_analytics_csv(csv_path)
    assert len(records) == 5

    z_scores = updater.compute_normalized_z_scores(records)
    assert len(z_scores) == 5

    # Sum of Z-scores across all samples must be approx 0.0
    total_z = sum(z for _, z in z_scores)
    assert total_z == pytest.approx(0.0, abs=1e-5)

    # Highest performing clip (clip_03: 85% stayed, 130% APV) has highest Z-score
    clip_03_z = [z for r, z in z_scores if r.clip_id == "clip_03"][0]
    clip_05_z = [z for r, z in z_scores if r.clip_id == "clip_05"][0]
    assert clip_03_z > 1.0
    assert clip_05_z < -1.0


def test_channel_profile_updater_json_loading(tmp_path: Path):
    """Verify JSON analytics loading handles percentage scales cleanly."""
    json_data = [
        {
            "clip_id": "clip_j1",
            "archetype": "HOT_TAKE",
            "hook_remix_used": False,
            "stayed_to_watch_pct": "72%",
            "avg_percentage_viewed": 105.5,
        },
        {
            "clip_id": "clip_j2",
            "archetype": "STORY",
            "hook_remix_used": True,
            "stayed_to_watch_pct": 0.85,  # fraction in 0..1 scale
            "avg_percentage_viewed": 1.25,
        },
    ]
    json_path = tmp_path / "analytics.json"
    json_path.write_text(json.dumps(json_data), encoding="utf-8")

    updater = ChannelProfileUpdater()
    records = updater.load_analytics_json(json_path)
    assert len(records) == 2
    assert records[0].stayed_to_watch_pct == 72.0
    assert records[1].stayed_to_watch_pct == 85.0
    assert records[1].avg_percentage_viewed == 125.0


def test_update_profile_adjusts_archetype_weights_and_remix_pref():
    """Verify learning update boosts outperforming archetype and remix preference."""
    updater = ChannelProfileUpdater(learning_rate=0.20)
    base_profile = ChannelProfile(
        archetype_weights={"STORY": 0.333, "TACTICAL_INSIGHT": 0.333, "HOT_TAKE": 0.334},
        hook_remix_preference=0.50,
    )

    # TACTICAL_INSIGHT outperforms; Hook remix outperforms
    records = [
        PublishedClipRecord("c1", "TACTICAL_INSIGHT", True, 90.0, 140.0),
        PublishedClipRecord("c2", "TACTICAL_INSIGHT", True, 88.0, 135.0),
        PublishedClipRecord("c3", "STORY", False, 65.0, 90.0),
        PublishedClipRecord("c4", "HOT_TAKE", False, 50.0, 70.0),
    ]

    new_profile = updater.update_profile(records, base_profile)

    # Archetype weights renormalize to 1.0
    assert sum(new_profile.archetype_weights.values()) == pytest.approx(1.0, abs=0.01)

    # TACTICAL_INSIGHT weight increased
    tac_new = new_profile.archetype_weights["TACTICAL_INSIGHT"]
    tac_base = base_profile.archetype_weights["TACTICAL_INSIGHT"]
    assert tac_new > tac_base

    # HOT_TAKE weight decreased
    assert new_profile.archetype_weights["HOT_TAKE"] < base_profile.archetype_weights["HOT_TAKE"]

    # Hook remix preference increased because remix clips performed better
    assert new_profile.hook_remix_preference > base_profile.hook_remix_preference


def test_profile_persistence_roundtrip(tmp_path: Path):
    """Verify atomic saving and loading of channel_profile.json."""
    updater = ChannelProfileUpdater()
    profile = ChannelProfile(
        archetype_weights={"STORY": 0.40, "TACTICAL_INSIGHT": 0.45, "HOT_TAKE": 0.15},
        hook_remix_preference=0.72,
        total_samples=42,
    )
    save_path = tmp_path / "profiles" / "channel_profile.json"
    updater.save_profile(profile, save_path)
    assert save_path.is_file()

    loaded = updater.load_profile(save_path)
    assert loaded.archetype_weights == profile.archetype_weights
    assert loaded.hook_remix_preference == pytest.approx(0.72)
    assert loaded.total_samples == 42


# ---------------------------------------------------------------------------
# 4. Stage 07 End-to-End & Orchestrator Integration Tests
# ---------------------------------------------------------------------------


def test_run_render_learn_stage_metadata_and_dual_render(tmp_path: Path):
    """Verify run_render_learn_stage builds paths, Hook Remix, and MonetizationMeta."""
    candidate = make_test_candidate(
        clip_id="clip_win",
        start_ms=1000,
        end_ms=31000,
        hook_remix_enabled=True,
        broll_cues=[
            BrollCue(
                trigger_ms=5000,
                duration_ms=5000,
                search_query="تجربة الأداء",
                overlay_type="TEXT_CARD",
            )
        ],
    )
    candidate.draft_pinned_comment_cta = "جرّب الأداة مجاناً!"
    candidate.draft_curiosity_titles = ["كيف تبني تطبيق ذكي؟"]

    manifest = QattaManifest(
        project_id="proj_render_test",
        source_path="/fake/media.mp4",
        duration_sec=60.0,
        atomic_utterances=[
            AtomicUtterance(
                u_id="U_0001",
                start_ms=1000,
                end_ms=10000,
                text="مقدمة الفيديو",
                audio_rms_norm=0.85,
            ),
            AtomicUtterance(
                u_id="U_0002",
                start_ms=15000,
                end_ms=17500,
                text="اللقطة القوية للريمكس",
                audio_rms_norm=0.92,
            ),
            AtomicUtterance(
                u_id="U_0003",
                start_ms=20000,
                end_ms=31000,
                text="الخاتمة",
                audio_rms_norm=0.60,
            ),
        ],
        candidates=[candidate],
    )

    renders_dir = tmp_path / "renders"
    updated = run_render_learn_stage(
        manifest=manifest,
        renders_dir=renders_dir,
        execute_ffmpeg=False,  # Test without real external video files
    )

    cand = updated.candidates[0]
    # Check rendered paths recorded
    assert "vertical_9_16" in cand.rendered_paths
    assert "vertical_9_16_hook_remix" in cand.rendered_paths
    assert cand.rendered_paths["vertical_9_16"].endswith("clip_win_original.mp4")
    assert cand.rendered_paths["vertical_9_16_hook_remix"].endswith("clip_win_hook_remix.mp4")

    # Check MonetizationMeta populated
    assert cand.monetization is not None
    assert cand.monetization.pinned_comment_cta == "جرّب الأداة مجاناً!"
    assert cand.monetization.curiosity_titles == ["كيف تبني تطبيق ذكي؟"]
    assert cand.monetization.visual_transformation_ratio > 0.0


def test_register_s07_orchestrator(tmp_path: Path):
    """Verify s07_render_learn registers cleanly on PipelineOrchestrator."""
    from qatta.core.pipeline import PipelineOrchestrator

    media_file = tmp_path / "video.mp4"
    media_file.write_bytes(b"dummy_video")

    settings = QattaSettings(data_dir=tmp_path / "data")
    manifest = QattaManifest(
        project_id="proj_orch_s07",
        source_path=str(media_file),
        duration_sec=30.0,
    )
    manifest_path = settings.manifest_path("proj_orch_s07")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    orchestrator = PipelineOrchestrator(
        project_id="proj_orch_s07",
        settings=settings,
    )

    register(orchestrator)
    assert "s07_render_learn" in orchestrator._stage_functions

    # Execute stage
    res = orchestrator.run_stage("s07_render_learn")
    assert res["stage"] == "s07_render_learn"
    assert res["executed"] is True
    assert "s07_render_learn" in orchestrator.manifest.completed_stages

    # Second execution is cached
    res2 = orchestrator.run_stage("s07_render_learn")
    assert res2["executed"] is False
    assert res2["skipped_cached"] is True
