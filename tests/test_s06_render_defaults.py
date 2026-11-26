"""Regression tests for the render stage's default layout.

`run_render_stage` used to default to ``layout="fill_crop"``, which
``build_render_command`` has never implemented. The registered pipeline stage
passes no layout, so every headless render (`laqta run`, the backend job
pipeline) failed with ``INVALID_CONFIG`` while the Studio — which calls the
renderer directly with an explicit layout — kept working. That is why the
existing tests missed it.

These tests pin the contract: the default must be a layout the renderer can
actually build, and a full default render must produce a validated file.
"""

from __future__ import annotations

import inspect
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.rendering.render import (
    SUPPORTED_LAYOUTS,
    build_render_command,
    probe_render_environment,
)
from qatta.core.config import QattaSettings
from qatta.core.schema import (
    ClipCandidate,
    CPSBreakdown,
    HookRemixVariant,
    QattaManifest,
    VetoGates,
)
from qatta.stages.s06_render.renderer import run_render_stage

FFMPEG = shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Pure contract — no subprocess, no ffmpeg needed
# ---------------------------------------------------------------------------


def test_the_supported_layouts_are_the_implemented_ones() -> None:
    assert set(SUPPORTED_LAYOUTS) == {
        "center_crop",
        "blurred_background",
        "face_guided",
    }
    # `fill_crop` is the bug: it was a default, never an implementation.
    assert "fill_crop" not in SUPPORTED_LAYOUTS


def test_the_render_stage_default_layout_is_supported() -> None:
    default = inspect.signature(run_render_stage).parameters["layout"].default

    # None means "auto": face_guided when the candidate has a solved
    # trajectory, centre crop otherwise. Any other value must be a layout the
    # command builder can actually construct.
    assert default is None or default in SUPPORTED_LAYOUTS, (
        f"run_render_stage defaults to layout={default!r}, which "
        f"build_render_command rejects. Supported: {SUPPORTED_LAYOUTS}."
    )


def test_the_default_layout_builds_a_real_command(tmp_path: Path) -> None:
    """The registered stage passes no layout, so the default must build."""
    default = inspect.signature(run_render_stage).parameters["layout"].default
    # A manifest with no trajectory resolves auto -> center_crop.
    resolved = default if default is not None else "center_crop"

    cmd = build_render_command(
        "ffmpeg",
        Path("/media/src.mp4"),
        tmp_path / "out.mp4",
        layout=resolved,
        quality="high",
        src_width=1920,
        src_height=1080,
        has_audio=True,
    )

    assert cmd[0] == "ffmpeg"
    assert "-vf" in cmd
    assert str(tmp_path / "out.mp4") == cmd[-1]


# ---------------------------------------------------------------------------
# End-to-end default render — gated on a usable local ffmpeg
# ---------------------------------------------------------------------------


def _skip_reason() -> str | None:
    if FFMPEG is None:
        return "ffmpeg is not installed"
    report = probe_render_environment(FFMPEG)
    if not report.get("h264_encoder_available"):
        return "no software H.264 encoder in this ffmpeg build"
    if not shutil.which("ffprobe"):
        return "ffprobe is not installed"
    return None


def _candidate() -> ClipCandidate:
    return ClipCandidate(
        clip_id="clip_default",
        start_u_id="U_0001",
        end_u_id="U_0002",
        start_ms=0,
        end_ms=1000,
        duration_sec=1.0,
        veto_gates=VetoGates(
            dangling_context=False,
            clean_audio_boundaries=True,
            crosstalk_ratio=0.0,
            passed_all=True,
        ),
        cps=CPSBreakdown(
            total_score=70.0,
            archetype="TACTICAL_INSIGHT",
            standalone_clarity=15.0,
            hook_strength=15.0,
            story_payoff=14.0,
            value_originality=12.0,
            audio_dynamics=8.0,
            boundary_precision=6.0,
        ),
        hook_remix=HookRemixVariant(enabled=False),
    )


def test_a_default_render_completes_and_records_the_output(tmp_path: Path) -> None:
    """Before the fix this raised INVALID_CONFIG: the pipeline's own default."""
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(f"Default render not exercisable here: {reason}")

    source = tmp_path / "source.mp4"
    made = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert made.returncode == 0, made.stderr[-500:]
    assert source.stat().st_size > 0

    manifest = QattaManifest(
        project_id="proj_render_default",
        source_path=str(source),
        duration_sec=1.0,
        video_width=320,
        video_height=240,
        candidates=[_candidate()],
    )

    work_dir = tmp_path / "work"
    # No layout argument: this is exactly what the registered stage does.
    updated = run_render_stage(
        manifest,
        settings=QattaSettings(data_dir=tmp_path / "data"),
        work_dir=work_dir,
    )

    rendered = Path(updated.candidates[0].rendered_paths["vertical_9_16"])
    assert rendered.is_file()
    assert rendered.stat().st_size > 0
    assert rendered.parent == (work_dir / "renders").resolve()
