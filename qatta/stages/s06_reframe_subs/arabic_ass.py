r"""Stage s06_reframe_subs — Arabic BiDi Shaper & Dynamic ASS Caption Generator.

Ensures strict BiDi correctness for mixed Arabic / Latin / English technical
terms (Arablish) and numbers:
- Detects Latin tokens and numbers using regex.
- Wraps every Latin/number token in Unicode First Strong Isolate (U+2068) and
  Pop Directional Isolate (U+2069).
- Prepends Right-to-Left Mark (U+200F) to each line so libass maintains correct
  word order and avoids reversing words during dynamic karaoke highlighting.
- Groups WordToken items into punchy display cues (max 4-5 words or 28 chars).
- Generates 1080x1920 ASS subtitles positioned in the safe zone (MarginV=420)
  with active word highlighting (\c&H00FFFF00& or \c&H0000D7FF&) and scale pop
  (\fscx110\fscy110).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qatta.core.schema import WordToken

# Unicode Directional Isolates & Marks
RLM = "\u200f"  # Right-to-Left Mark
FSI = "\u2068"  # First Strong Isolate
PDI = "\u2069"  # Pop Directional Isolate

# Regex matching Latin words and Arabic/Western numbers (including decimals, hyphens, slashes)
LATIN_NUM_PATTERN = re.compile(r"([A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*)")


class ArabicBiDiShaper:
    """Shapes Arabic text with embedded Latin terms and numbers for libass."""

    LATIN_NUM_PATTERN = LATIN_NUM_PATTERN

    @classmethod
    def shape_token(cls, token: str) -> str:
        """Wrap a token in FSI/PDI isolates if it contains Latin letters or numbers."""
        cleaned = token.replace(FSI, "").replace(PDI, "").replace(RLM, "")
        if LATIN_NUM_PATTERN.search(cleaned):
            return LATIN_NUM_PATTERN.sub(lambda m: f"{FSI}{m.group(0)}{PDI}", cleaned)
        return cleaned

    @classmethod
    def shape_line(cls, text: str) -> str:
        """Wrap Latin words & numbers in FSI/PDI isolates and prepend RLM to the line.

        Example:
            'عملنا deploy للـ API في 3 أيام' ->
            '\u200fعملنا \u2068deploy\u2069 للـ \u2068API\u2069 في \u20683\u2069 أيام'
        """
        if not text:
            return text

        # Strip any existing isolate/RLM markers to prevent duplicate nesting
        cleaned = text.replace(FSI, "").replace(PDI, "").replace(RLM, "")

        # Wrap Latin and number tokens
        shaped = LATIN_NUM_PATTERN.sub(lambda m: f"{FSI}{m.group(0)}{PDI}", cleaned)

        # Prepend Right-to-Left Mark (RLM)
        return f"{RLM}{shaped}"


@dataclass
class CaptionLine:
    """A single grouped display line of words."""

    words: list[WordToken]
    start_ms: int
    end_ms: int
    text: str
    shaped_text: str = ""

    def __post_init__(self) -> None:
        if not self.shaped_text:
            self.shaped_text = ArabicBiDiShaper.shape_line(self.text)


def group_words_into_lines(
    words: list[WordToken],
    max_words: int = 4,
    max_chars: int = 28,
) -> list[CaptionLine]:
    """Group a list of WordToken items into punchy display cues.

    Boundaries respect max_words (4-5 words) or max_chars (28 chars per cue),
    whichever limit is hit first.
    """
    if not words:
        return []

    lines: list[CaptionLine] = []
    current_tokens: list[WordToken] = []
    current_char_len = 0

    for token in words:
        token_len = len(token.word)
        # Check if adding this token exceeds limits
        projected_chars = current_char_len + (1 if current_tokens else 0) + token_len
        if current_tokens and (len(current_tokens) >= max_words or projected_chars > max_chars):
            # Flush current line
            raw_text = " ".join(t.word for t in current_tokens)
            lines.append(
                CaptionLine(
                    words=list(current_tokens),
                    start_ms=current_tokens[0].start_ms,
                    end_ms=current_tokens[-1].end_ms,
                    text=raw_text,
                )
            )
            current_tokens = [token]
            current_char_len = token_len
        else:
            current_tokens.append(token)
            current_char_len = projected_chars

    if current_tokens:
        raw_text = " ".join(t.word for t in current_tokens)
        lines.append(
            CaptionLine(
                words=list(current_tokens),
                start_ms=current_tokens[0].start_ms,
                end_ms=current_tokens[-1].end_ms,
                text=raw_text,
            )
        )

    return lines


def ms_to_ass_time(ms: int) -> str:
    """Format millisecond timestamp as ASS time: h:mm:ss.cc."""
    ms = max(0, ms)
    total_sec = ms / 1000.0
    hours = int(total_sec // 3600)
    minutes = int((total_sec % 3600) // 60)
    seconds = int(total_sec % 60)
    centis = int(round((total_sec - int(total_sec)) * 100))
    if centis >= 100:
        seconds += 1
        centis = 0
    if seconds >= 60:
        minutes += 1
        seconds = 0
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """Convert hex color (#RRGGBB) to ASS color format (&H<alpha><B><G><R>&)."""
    clean = hex_color.strip().lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    r = clean[0:2].upper()
    g = clean[2:4].upper()
    b = clean[4:6].upper()
    a = f"{alpha:02X}"
    return f"&H{a}{b}{g}{r}&"


@dataclass
class ASSCaptionConfig:
    """Visual style configuration for vertical 9:16 ASS subtitles."""

    play_res_x: int = 1080
    play_res_y: int = 1920
    font_name: str = "Noto Sans Arabic"
    font_size: int = 68
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#00FFFF"  # Electric cyan active highlight
    secondary_highlight_color: str = "#FFD700"  # Gold alternate
    outline_color: str = "#000000"
    back_color: str = "#80000000"
    outline_width: float = 3.5
    shadow_depth: float = 0.0
    margin_v: int = 420  # Safe zone above YouTube Shorts UI overlays
    margin_lr: int = 60
    scale_pop: int = 110  # Scale active word by 110%


def generate_dynamic_ass(
    lines: list[CaptionLine],
    config: ASSCaptionConfig | None = None,
) -> str:
    """Generate complete ASS script with active word-level highlight & BiDi isolates.

    For each line, sub-events are emitted for each word duration so that the
    currently active spoken word highlights dynamically with pop scaling
    (\\fscx110\\fscy110) while preserving BiDi isolate ordering.
    """
    cfg = config or ASSCaptionConfig()

    primary_ass = hex_to_ass_color(cfg.primary_color)
    highlight_ass = hex_to_ass_color(cfg.highlight_color)
    outline_ass = hex_to_ass_color(cfg.outline_color)

    format_hdr = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    style_def = (
        f"Style: Default,{cfg.font_name},{cfg.font_size},{primary_ass},"
        f"&H000000FF,{outline_ass},{cfg.back_color},-1,0,0,0,100,100,0,0,1,"
        f"{cfg.outline_width},{cfg.shadow_depth},2,{cfg.margin_lr},"
        f"{cfg.margin_lr},{cfg.margin_v},1"
    )
    header = (
        f"[Script Info]\n"
        f"Title: Laqta BiDi Dynamic Captions\n"
        f"ScriptType: v4.00+\n"
        f"PlayResX: {cfg.play_res_x}\n"
        f"PlayResY: {cfg.play_res_y}\n"
        f"ScaledBorderAndShadow: yes\n"
        f"YCbCr Matrix: TV.709\n\n"
        f"[V4+ Styles]\n"
        f"{format_hdr}\n"
        f"{style_def}\n\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    dialogue_events: list[str] = []

    for line in lines:
        if not line.words:
            # Fallback for line with no word breakdown
            t_start = ms_to_ass_time(line.start_ms)
            t_end = ms_to_ass_time(line.end_ms)
            dialogue_events.append(
                f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{line.shaped_text}"
            )
            continue

        num_words = len(line.words)
        for idx, active_word in enumerate(line.words):
            # Start of this word's highlight
            w_start_ms = active_word.start_ms

            # End of this word's highlight: extend to next word's start to avoid flicker
            if idx + 1 < num_words:
                w_end_ms = line.words[idx + 1].start_ms
            else:
                w_end_ms = active_word.end_ms

            if w_end_ms <= w_start_ms:
                w_end_ms = w_start_ms + 100

            t_start = ms_to_ass_time(w_start_ms)
            t_end = ms_to_ass_time(w_end_ms)

            # Build shaped line with active word pop
            shaped_tokens = []
            for j, token in enumerate(line.words):
                isolated = ArabicBiDiShaper.shape_token(token.word)
                if j == idx:
                    # Active spoken word highlight with scale pop
                    highlighted = (
                        f"{{\\c{highlight_ass}\\fscx{cfg.scale_pop}\\fscy{cfg.scale_pop}}}"
                        f"{isolated}"
                        f"{{\\r\\c{primary_ass}\\fscx100\\fscy100}}"
                    )
                    shaped_tokens.append(highlighted)
                else:
                    shaped_tokens.append(isolated)

            line_text = f"{RLM}{' '.join(shaped_tokens)}"
            dialogue_events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{line_text}")

    return header + "\n".join(dialogue_events) + "\n"
