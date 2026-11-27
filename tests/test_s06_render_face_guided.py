"""Face-guided rendering: the crop trajectory must actually reach FFmpeg.

Phase 3 made ``s06_reframe_subs`` record a solved trajectory. Recording it was
useless if the renderer ignored it, so these tests cover the whole path:

- the ``face_guided`` layout exists and is accepted by the command builder;
- the trajectory becomes a real, clamped, even-offset crop expression;
- an empty or static trajectory degrades to a centred crop instead of failing;
- the core render stage picks the layout per candidate and says which it used;
- and a real FFmpeg render visibly pans from one side of the frame to the other.

The last one matters most: a command that merely *contains* an expression is
not proof the pixels moved.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.rendering.render import (
    MAX_TRAJECTORY_POINTS,
    SUPPORTED_LAYOUTS,
    build_crop_x_expression,
    build_render_command,
    probe_render_environment,
)
from qatta.core.config import QattaSettings
from qatta.core.schema import (
    ClipCandidate,
    CPSBreakdown,
    CropKeyframe,
    HookRemixVariant,
    QattaManifest,
    ShotFraming,
    VetoGates,
)
from qatta.stages.s06_render.renderer import (
    _resolve_layout,
    clip_relative_trajectory,
    run_render_stage,
)

FFMPEG = shutil.which("ffmpeg")

# 1920x1080 -> 1080x1920 crops a 606-wide vertical slice, so x ranges 0..1314.
SRC_W, SRC_H = 1920, 1080
CROP_W = 606
MAX_X = SRC_W - CROP_W


# ---------------------------------------------------------------------------
# Pure: the expression builder
# ---------------------------------------------------------------------------


def test_the_face_guided_layout_is_supported() -> None:
    assert "face_guided" in SUPPORTED_LAYOUTS


def test_no_keyframes_yields_no_expression() -> None:
    assert build_crop_x_expression([], src_width=SRC_W, crop_width=CROP_W) is None


def test_a_crop_as_wide_as_the_source_cannot_move() -> None:
    assert build_crop_x_expression([(0, 0.2), (1000, 0.8)], src_width=1000, crop_width=1000) is None


def test_a_static_trajectory_becomes_a_constant() -> None:
    expression = build_crop_x_expression(
        [(0, 0.5), (200, 0.5), (400, 0.5)], src_width=SRC_W, crop_width=CROP_W
    )

    # 0.5 * 1920 - 606/2 = 657 exactly.
    assert expression == "657.00"
    assert "if(" not in expression


def test_a_moving_trajectory_becomes_a_clamped_even_offset() -> None:
    expression = build_crop_x_expression(
        [(0, 0.2), (1000, 0.8)], src_width=SRC_W, crop_width=CROP_W
    )

    assert expression is not None
    # Even offset, clamped to the legal range: yuv420p rejects odd x.
    assert expression.startswith("2*trunc(clip(")
    assert f",0,{MAX_X}.00)" in expression
    assert "if(lt(t,1.000)" in expression


def test_held_runs_collapse_to_the_moving_points_only() -> None:
    # Ten held samples then a move to a new held value. The 12 samples must
    # collapse to four control points (start/end of each run), so only one of
    # the piecewise branches actually pans.
    keyframes = [(index * 200, 0.5) for index in range(10)]
    keyframes += [(2000, 0.7), (2200, 0.7)]

    expression = build_crop_x_expression(keyframes, src_width=SRC_W, crop_width=CROP_W)

    assert expression is not None
    assert expression.count("if(") == 3
    slopes = [float(value) for value in re.findall(r"\+\((-?\d+\.\d+)\)\*", expression)]
    assert len(slopes) == 3
    assert sum(1 for slope in slopes if abs(slope) > 0.01) == 1


def test_decimation_bounds_the_expression_size() -> None:
    # Every sample distinct: a slow pan. The rendered expression must stay
    # bounded even though the manifest holds one keyframe per frame.
    keyframes = [(index * 100, 0.1 + 0.8 * index / 199) for index in range(200)]

    expression = build_crop_x_expression(
        keyframes, src_width=SRC_W, crop_width=CROP_W, max_points=8
    )

    assert expression is not None
    assert expression.count("if(") <= 8
    assert expression.count("if(") <= MAX_TRAJECTORY_POINTS


def test_out_of_range_centres_are_clamped() -> None:
    expression = build_crop_x_expression(
        [(0, -5.0), (1000, 5.0)], src_width=SRC_W, crop_width=CROP_W
    )

    assert expression is not None
    # Both ends saturate at the legal range instead of producing a negative
    # offset that would make ffmpeg fail the whole render.
    assert "0.00" in expression
    assert f"{MAX_X}.00" in expression


# ---------------------------------------------------------------------------
# Pure: the command builder
# ---------------------------------------------------------------------------


def _cmd(tmp_path: Path, **overrides) -> list[str]:
    kwargs = {
        "layout": "face_guided",
        "quality": "cpu_friendly",
        "src_width": SRC_W,
        "src_height": SRC_H,
        "has_audio": False,
    }
    kwargs.update(overrides)
    return build_render_command("ffmpeg", Path("/media/src.mp4"), tmp_path / "out.mp4", **kwargs)


def test_face_guided_without_a_trajectory_centres_the_crop(tmp_path: Path) -> None:
    cmd = _cmd(tmp_path)
    vf = cmd[cmd.index("-vf") + 1]

    # A centred 606x1080 window: x = (1920 - 606) // 2 = 657, y = 0.
    assert f"crop=w={CROP_W}:h={SRC_H}:x=657:y=0" in vf


def test_face_guided_with_a_trajectory_uses_an_expression(tmp_path: Path) -> None:
    cmd = _cmd(tmp_path, crop_trajectory=[(0, 0.2), (1000, 0.8)])
    vf = cmd[cmd.index("-vf") + 1]

    # Single quotes keep the expression's commas out of the filtergraph split.
    assert f"crop=w={CROP_W}:h={SRC_H}:x='2*trunc(clip(" in vf
    assert "scale=720:1280" in vf


def test_center_crop_ignores_a_trajectory(tmp_path: Path) -> None:
    cmd = _cmd(tmp_path, layout="center_crop", crop_trajectory=[(0, 0.2), (1000, 0.8)])
    vf = cmd[cmd.index("-vf") + 1]

    assert "x='" not in vf
    assert f"crop=w={CROP_W}:h={SRC_H}" in vf


# ---------------------------------------------------------------------------
# The core stage's per-candidate decision
# ---------------------------------------------------------------------------


def _candidate(trajectory: list[ShotFraming] | None = None) -> ClipCandidate:
    return ClipCandidate(
        clip_id="clip_face",
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=1000,
        end_ms=3000,
        duration_sec=2.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=80.0,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=18.0,
            hook_strength=18.0,
            story_payoff=16.0,
            value_originality=14.0,
            audio_dynamics=8.0,
            boundary_precision=6.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
        crop_trajectory=trajectory or [],
    )


def _shot() -> ShotFraming:
    return ShotFraming(
        shot_index=0,
        start_ms=1000,
        end_ms=3000,
        layout="SINGLE_SPEAKER",
        keyframes=[
            CropKeyframe(timestamp_ms=1000, center_x=0.2),
            CropKeyframe(timestamp_ms=2000, center_x=0.5),
            CropKeyframe(timestamp_ms=3000, center_x=0.8),
        ],
    )


def test_auto_uses_face_guided_only_when_a_trajectory_exists() -> None:
    with_trajectory = _resolve_layout(_candidate([_shot()]), None)
    without = _resolve_layout(_candidate(), None)

    assert with_trajectory[0] == "face_guided"
    assert without[0] == "center_crop"
    assert without[1] == []


def test_an_explicit_layout_is_honoured_even_with_a_trajectory() -> None:
    layout, trajectory = _resolve_layout(_candidate([_shot()]), "center_crop")

    assert layout == "center_crop"
    assert trajectory == []


def test_an_explicit_face_guided_without_a_trajectory_reports_nothing_to_follow() -> None:
    layout, trajectory = _resolve_layout(_candidate(), "face_guided")

    assert layout == "face_guided"
    assert trajectory == []


def test_the_trajectory_is_rebased_onto_the_clip_timeline() -> None:
    # Keyframes are in SOURCE time (1000..3000); the clip starts at 1000, so
    # ffmpeg's t=0 must correspond to source 1000.
    candidate = _candidate([_shot()])
    points = clip_relative_trajectory(
        candidate.crop_trajectory,
        clip_start_ms=candidate.start_ms,
        clip_end_ms=candidate.end_ms,
    )

    assert points == [(0, 0.2), (1000, 0.5), (2000, 0.8)]


def test_keyframes_outside_the_clip_are_clamped() -> None:
    shot = ShotFraming(
        shot_index=0,
        start_ms=0,
        end_ms=5000,
        layout="SINGLE_SPEAKER",
        keyframes=[
            CropKeyframe(timestamp_ms=0, center_x=0.1),
            CropKeyframe(timestamp_ms=5000, center_x=0.9),
        ],
    )
    candidate = _candidate([shot])

    points = clip_relative_trajectory(
        candidate.crop_trajectory,
        clip_start_ms=candidate.start_ms,
        clip_end_ms=candidate.end_ms,
    )

    # Clip is 1000..3000, so source 0 and 5000 clamp to 0 and 2000.
    assert points == [(0, 0.1), (2000, 0.9)]


# ---------------------------------------------------------------------------
# The core stage wiring, without a real encode
# ---------------------------------------------------------------------------


def test_the_stage_records_the_layout_it_chose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"placeholder")

    captured: dict = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        kwargs["output_path"].write_bytes(b"fake render")
        return ["true"]

    monkeypatch.setattr(
        "app.services.rendering.render.probe_render_environment",
        lambda *_args, **_kwargs: {"h264_encoder": "libx264"},
    )
    monkeypatch.setattr("app.services.rendering.render.build_render_command", fake_build)
    monkeypatch.setattr(
        "app.services.rendering.render.probe_render_output",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )

    manifest = QattaManifest(
        project_id="proj_face_render",
        source_path=str(source),
        duration_sec=3.0,
        video_width=SRC_W,
        video_height=SRC_H,
        candidates=[_candidate([_shot()])],
    )

    updated = run_render_stage(
        manifest,
        settings=QattaSettings(data_dir=tmp_path / "data"),
        work_dir=tmp_path / "work",
        quality="cpu_friendly",
        burn_captions=False,
    )

    candidate = updated.candidates[0]
    assert captured["layout"] == "face_guided"
    assert captured["crop_trajectory"] == [(0, 0.2), (1000, 0.5), (2000, 0.8)]
    assert any("s06_render: layout=face_guided" in line for line in candidate.evidence_log)
    assert candidate.rendered_paths["vertical_9_16"]


# ---------------------------------------------------------------------------
# Real render: prove the pixels move
# ---------------------------------------------------------------------------


def _skip_reason() -> str | None:
    if FFMPEG is None:
        return "ffmpeg is not installed"
    if not shutil.which("ffprobe"):
        return "ffprobe is not installed"
    report = probe_render_environment(FFMPEG)
    if not report.get("h264_encoder_available"):
        return "no software H.264 encoder in this ffmpeg build"
    return None


def _center_pixel(frame_bytes: bytes, width: int, height: int) -> tuple[int, int, int]:
    index = ((height // 2) * width + width // 2) * 3
    return frame_bytes[index], frame_bytes[index + 1], frame_bytes[index + 2]


def test_a_real_face_guided_render_pans_across_the_frame(tmp_path: Path) -> None:
    """A red-left / blue-right source, panned from left to right.

    The first frame must sample red and the last must sample blue. If the
    expression were ignored, both frames would sit in the same place.
    """
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(f"Real render not exercisable here: {reason}")

    source = tmp_path / "split.mp4"
    made = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=960x1080:d=2:r=25",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=960x1080:d=2:r=25",
            "-filter_complex",
            "[0:v][1:v]hstack=inputs=2[v]",
            "-map",
            "[v]",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert made.returncode == 0, made.stderr[-500:]

    output = tmp_path / "out.mp4"
    report = probe_render_environment(FFMPEG)
    cmd = build_render_command(
        FFMPEG,
        source,
        output,
        layout="face_guided",
        quality="cpu_friendly",
        src_width=SRC_W,
        src_height=SRC_H,
        has_audio=False,
        start_ms=0,
        duration_ms=2000,
        crop_trajectory=[(0, 0.1), (2000, 0.9)],
        video_encoder=report["h264_encoder"],
    )
    rendered = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    assert rendered.returncode == 0, rendered.stderr[-800:]
    assert output.is_file() and output.stat().st_size > 0

    def sample(seconds: float) -> tuple[int, int, int]:
        frame = subprocess.run(
            [
                FFMPEG,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(seconds),
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        assert frame.returncode == 0
        return _center_pixel(frame.stdout, 720, 1280)

    first = sample(0.1)
    last = sample(1.8)

    # Left crop at the start sees red; right crop at the end sees blue.
    assert first[0] > first[2] + 40, first
    assert last[2] > last[0] + 40, last
