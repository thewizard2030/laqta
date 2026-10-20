"""Stage s07_render_learn — YPP-Safe FFmpeg 9:16 Shorts Renderer & Channel Feedback.

Combines:
- Single-pass FFmpegFilterGraphBuilder for vertical reframing, layout vstack,
  pattern interrupt zoom, B-roll overlays, and Arabic BiDi .ass subtitle burn-in.
- MonetizationMeta.visual_transformation_ratio validation (warning if < 0.35).
- Hook remix dual cut rendering (original + hook-first remix).
- ChannelProfileUpdater learning loop with channel-normalized Z-scores.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from qatta.core.config import QattaSettings
from qatta.core.schema import QattaManifest
from qatta.stages.s07_render_learn.feedback_loop import (
    DEFAULT_ARCHETYPE_WEIGHTS,
    ChannelProfile,
    ChannelProfileUpdater,
    PublishedClipRecord,
)
from qatta.stages.s07_render_learn.renderer import (
    FFmpegFilterGraphBuilder,
    PunchZoomInterval,
    build_hook_remix_command,
    build_render_command,
    compute_visual_transformation_ratio,
    detect_punch_in_zooms,
    escape_ffmpeg_filter_path,
    execute_ffmpeg_render,
    run_render_stage,
)

if TYPE_CHECKING:
    from qatta.core.pipeline import PipelineOrchestrator

logger = logging.getLogger("qatta.s07_render_learn")

__all__ = [
    "DEFAULT_ARCHETYPE_WEIGHTS",
    "ChannelProfile",
    "ChannelProfileUpdater",
    "FFmpegFilterGraphBuilder",
    "PublishedClipRecord",
    "PunchZoomInterval",
    "build_hook_remix_command",
    "build_render_command",
    "compute_visual_transformation_ratio",
    "detect_punch_in_zooms",
    "escape_ffmpeg_filter_path",
    "execute_ffmpeg_render",
    "register",
    "run_render_learn_stage",
    "run_render_stage",
]


def run_render_learn_stage(
    manifest: QattaManifest,
    settings: QattaSettings | None = None,
    renders_dir: Path | None = None,
    analytics_file: Path | None = None,
    execute_ffmpeg: bool = True,
) -> QattaManifest:
    """Execute Stage s07 rendering and update channel performance profile."""
    settings = settings or QattaSettings()

    # 1. Execute rendering and monetization transformation calculation
    manifest = run_render_stage(
        manifest=manifest,
        settings=settings,
        renders_dir=renders_dir,
        execute_ffmpeg=execute_ffmpeg,
    )

    # 2. Check for optional analytics feedback update
    analytics_path = analytics_file or (
        settings.data_dir / "analytics" / "latest_shorts_analytics.csv"
    )
    if analytics_path.is_file():
        updater = ChannelProfileUpdater()
        profile_path = settings.data_dir / "channel_profile.json"
        base_profile = updater.load_profile(profile_path)

        if analytics_path.suffix.lower() == ".json":
            records = updater.load_analytics_json(analytics_path)
        else:
            records = updater.load_analytics_csv(analytics_path)

        updated_profile = updater.update_profile(records, base_profile)
        updater.save_profile(updated_profile, profile_path)
        logger.info(
            "Updated channel profile with %d samples from %s "
            "(STORY=%.2f, TACTICAL=%.2f, HOT_TAKE=%.2f)",
            len(records),
            analytics_path.name,
            updated_profile.archetype_weights.get("STORY", 0.0),
            updated_profile.archetype_weights.get("TACTICAL_INSIGHT", 0.0),
            updated_profile.archetype_weights.get("HOT_TAKE", 0.0),
        )

    return manifest


def register(orchestrator: PipelineOrchestrator) -> None:
    """Attach s07_render_learn stage to a PipelineOrchestrator."""

    @orchestrator.stage("s07_render_learn")
    def _stage(manifest: QattaManifest) -> QattaManifest:
        return run_render_learn_stage(
            manifest=manifest,
            settings=orchestrator.settings,
            # Core orchestrator pipeline avoids heavy external encoding in tests
            execute_ffmpeg=False,
        )
