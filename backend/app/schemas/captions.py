"""Pydantic schemas for caption generation (PRD §5 FR-08)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CAPTION_FORMATS = ("srt", "ass")

# Warning strings surfaced to users. They must always state limitations
# honestly per PRD §5 FR-08 and AGENTS.md (no untested correctness claims).
WARNING_WORD_TIMINGS_MISSING = (
    "Word-level timestamps are missing for this transcript; captions fall "
    "back to segment-level timing (no karaoke highlight)."
)
WARNING_WORD_TIMINGS_UNRELIABLE = (
    "Word-level timestamps present but unreliable (non-monotonic or invalid "
    "out of clip range); captions fall back to segment-level timing "
    "(no karaoke highlight)."
)
WARNING_WORD_TIMINGS_LOW_CONFIDENCE = (
    "Most re-transcribed words have low confidence; karaoke is disabled and "
    "segment/word plain timing is used."
)
WARNING_WORD_TEXT_LOW_CONFIDENCE = (
    "{low} of {total} re-transcribed words were recognised with low "
    "confidence. The word highlight is still aligned to the speech, but "
    "those words may be misspelled in the caption text."
)
WARNING_TEXT_OVERFLOW = (
    "One or more caption cues exceed the configured max characters per line "
    "and max lines; text is shown longer than the safe area. Reduce the cue "
    "length or edit the transcript wording."
)
WARNING_TEXT_SPLIT = (
    "Some transcript segments were longer than one caption cue. Their text "
    "was split into several shorter cues so it stays inside the safe area; "
    "the time was distributed proportionally to the text length, so the "
    "caption is an estimate of the spoken timing."
)
WARNING_NO_ARABIC_FONT = (
    "No Arabic-capable fonts were found via fc-list (:lang=ar). Install an "
    "Arabic font (e.g. 'google-noto-sans-arabic-fonts' on Fedora) or set the "
    "caption font to a locally installed Arabic-capable family."
)


class CaptionStyleSettings(BaseModel):
    """User-editable caption appearance settings (PRD §5 FR-08)."""

    font_name: str = Field(
        default="Noto Sans Arabic",
        description="Requested font family. libass falls back via fontconfig if missing.",
    )
    font_size: int = Field(
        default=110,
        ge=10,
        le=200,
        description=(
            "Font size in ASS PlayRes pixels (1080x1920 canvas by default). "
            "110 px gives a caption cap height of roughly 6% of the frame "
            "width, which reads clearly on a phone screen."
        ),
    )
    bold: bool = Field(
        default=True,
        description="Render the caption in bold. Shorts captions need the extra weight.",
    )
    foreground_color: str = Field(
        default="#FFFFFF",
        description="Caption text color as #RRGGBB.",
    )
    highlight_color: str = Field(
        default="#00F2FE",
        description=(
            "Colour of the word-by-word highlight in karaoke mode. In ASS "
            "karaoke the PrimaryColour paints the part that has already "
            "been spoken and the SecondaryColour the part still to come, so "
            "this colour fills the caption as the speaker reaches each word."
        ),
    )
    outline_color: str = Field(
        default="#000000",
        description="Caption outline (stroke) color as #RRGGBB.",
    )
    outline_width: float = Field(
        default=6.0,
        ge=0.0,
        le=10.0,
        description="Outline width in PlayRes pixels.",
    )
    shadow_depth: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Drop-shadow depth in PlayRes pixels (separates text from the video).",
    )
    position: Literal["bottom", "middle", "top"] = Field(
        default="bottom",
        description="Caption anchor position within the safe area.",
    )
    margin_v: int = Field(
        default=340,
        ge=0,
        le=960,
        description="Vertical safe margin (pixels from bottom, top margin for 'top').",
    )
    margin_h: int = Field(
        default=60,
        ge=0,
        le=540,
        description="Horizontal safe margin (pixels from left/right edge).",
    )
    max_chars_per_line: int = Field(
        default=28,
        ge=10,
        le=80,
        description=(
            "Hard character cap per caption line. The effective limit is the "
            "smaller of this value and the width the font actually needs, so "
            "lines never spill outside the horizontal safe area."
        ),
    )
    max_lines: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Maximum stacked lines per caption cue.",
    )
    play_res_x: int = Field(
        default=1080,
        ge=320,
        le=4096,
        description="ASS script resolution width used for the layout maths.",
    )
    play_res_y: int = Field(
        default=1920,
        ge=320,
        le=4096,
        description="ASS script resolution height used for the layout maths.",
    )
    karaoke: bool = Field(
        default=False,
        description=(
            "Request ASS karaoke word highlight. Applied ONLY when valid word "
            "timings exist; otherwise the plain no-karaoke fallback is used "
            "and a warning is reported."
        ),
    )

    @field_validator("foreground_color", "outline_color", "highlight_color")
    @classmethod
    def validate_hex_color(cls, v: str) -> str:
        """Require strict #RRGGBB so color conversion stays deterministic."""
        text = v.strip()
        if len(text) != 7 or not text.startswith("#"):
            raise ValueError(f"Color '{v}' must be formatted as '#RRGGBB'.")
        try:
            int(text[1:], 16)
        except ValueError as e:
            raise ValueError(f"Color '{v}' is not valid hexadecimal #RRGGBB.") from e
        return text.upper()


class CaptionGenerationRequest(BaseModel):
    """Request payload to generate editable SRT and/or ASS files."""

    style: CaptionStyleSettings = Field(default_factory=CaptionStyleSettings)
    formats: tuple[Literal["srt", "ass"], ...] = Field(
        default=("srt", "ass"),
        description="Which caption files to generate.",
    )


class CandidateCaptionsResponse(BaseModel):
    """Result of generating caption files for a candidate."""

    candidate_id: str
    media_id: str
    transcript_id: str = Field(
        ...,
        description="Transcript the captions were derived from.",
    )
    srt_path: str | None = None
    ass_path: str | None = None
    timing_granularity: Literal["word", "segment"] = Field(
        ...,
        description=(
            "Truthful granularity used for previews: 'word' when reliable word "
            "timings exist, 'segment' when the no-karaoke fallback applied."
        ),
    )
    karaoke_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    style: CaptionStyleSettings
    created_at: str


class CaptionArtifact(BaseModel):
    """A single file artifact stored under the project data directory."""

    kind: Literal["srt", "ass", "mp4", "render_log", "render_config"]
    path: str
    size_bytes: int
    created_at: str


class CandidateArtifactsResponse(BaseModel):
    """Caption files and rendered outputs belonging to one candidate."""

    candidate_id: str
    media_id: str
    captions: list[CaptionArtifact] = Field(default_factory=list)
    rendered_clips: list[CaptionArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
