"""Pydantic schemas for rendering/export (PRD §5 FR-09, PRD §11 Gate D)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.captions import CaptionStyleSettings


class LayoutMode(StrEnum):
    """Vertical layout modes. Active-speaker and split-screen are intentionally
    NOT implemented (FR-07 defers them); honest enum keeps the UI truthful."""

    CENTER_CROP = "center_crop"
    BLURRED_BACKGROUND = "blurred_background"


class QualityPreset(StrEnum):
    """Video presets. 'high' targets 8 GB CPUs conservatively; 'cpu_friendly'
    lowers resolution/detail and encode speed cost for slower machines."""

    HIGH = "high"
    CPU_FRIENDLY = "cpu_friendly"


class CaptionFormatForRender(StrEnum):
    """Which caption file the renderer burns in, if any."""

    ASS = "ass"
    SRT = "srt"
    NONE = "none"


class RenderRequest(BaseModel):
    """Request payload for enqueueing a render job for a candidate."""

    layout: LayoutMode = Field(
        default=LayoutMode.CENTER_CROP,
        description="Vertical composition mode (FR-07 initial set).",
    )
    quality: QualityPreset = Field(
        default=QualityPreset.HIGH,
        description="1080x1920 by default; 'cpu_friendly' lowers resolution and CRF.",
    )
    caption_format: CaptionFormatForRender = Field(
        default=CaptionFormatForRender.ASS,
        description="Caption file to burn in ('none' exports no captions).",
    )
    style: CaptionStyleSettings | None = Field(
        default=None,
        description="Caption style overrides (defaults apply when omitted).",
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "Allow replacing an existing same-name render output. Without this "
            "flag the render fails safely instead of clobbering user work."
        ),
    )


class RenderCommandInfo(BaseModel):
    """Exact command and artifact metadata stored per render for debugging."""

    argv: list[str] = Field(default_factory=list)
    layout: str
    quality: str
    width: int
    height: int
    crf: int
    video_preset: str
    caption_format: str
    caption_path: str | None = None
    input_path: str
    output_path: str
    overwrite: bool


class RenderedClipResponse(BaseModel):
    """A successfully validated rendered clip record."""

    id: str
    candidate_id: str
    media_id: str
    output_path: str
    width: int
    height: int
    duration_ms: int
    size_bytes: int
    render_config_json: str | None = None
    created_at: str
    extra: dict[str, Any] | None = None
