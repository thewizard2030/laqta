"""Stage s06_render — ASS Subtitle Generation & 9:16 Vertical Video Rendering.

Takes winning ClipCandidates from Stage s05 (with fine word alignment from
Stage s02b if available), produces styled ASS captions with proper Arabic BiDi
isolates (\u2068, \u2069, \u200f), renders vertical 9:16 video via FFmpeg
subprocess argument arrays, validates the output via ffprobe, and persists
rendered file locations in ``candidate.rendered_paths["vertical_9_16"]``.
"""

from qatta.stages.s06_render.renderer import (
    register,
    run_render_stage,
)

__all__ = ["register", "run_render_stage"]
