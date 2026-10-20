/**
 * Mapping between the studio's user-facing caption options and the
 * backend ASS caption style (PRD §5 FR-08).
 *
 * The inspector shows a small, opinionated set of choices; the renderer
 * needs concrete ASS values. This module is the single place where the
 * two meet, so the Captions tab actually changes the rendered output
 * instead of being a decorative control.
 */

import type { CaptionStyleOptions, CaptionPreset } from "../../features/studio/types";
import type { CaptionStyleSettings } from "../../types/rendering";

/** Font size (ASS PlayRes px on a 1080x1920 canvas) for each size pill. */
const FONT_SIZE_BY_PILL: Record<CaptionStyleOptions["fontSize"], number> = {
  sm: 76,
  base: 94,
  lg: 110,
  xl: 132,
};

interface PresetLook {
  outlineWidth: number;
  shadowDepth: number;
  highlightColor: string;
}

const PRESET_LOOKS: Record<CaptionPreset, PresetLook> = {
  "neon-glow": { outlineWidth: 6, shadowDepth: 3, highlightColor: "#00F2FE" },
  minimalist: { outlineWidth: 3, shadowDepth: 0, highlightColor: "#FFFFFF" },
  "bold-outline": { outlineWidth: 9, shadowDepth: 0, highlightColor: "#00F2FE" },
  cyberpunk: { outlineWidth: 5, shadowDepth: 2, highlightColor: "#FACC15" },
};

/**
 * Build the ASS caption style for a render request.
 *
 * `karaoke` is forwarded as-is: the backend only honours it when the
 * clip can be re-timed locally with word-level timestamps, and falls
 * back to plain timed captions otherwise.
 */
export function buildCaptionStyle(options: CaptionStyleOptions): CaptionStyleSettings {
  const look = PRESET_LOOKS[options.preset] ?? PRESET_LOOKS["neon-glow"];
  return {
    font_name: options.fontFamily,
    font_size: FONT_SIZE_BY_PILL[options.fontSize] ?? 110,
    bold: true,
    foreground_color: options.textColor,
    highlight_color: options.highlightColor || look.highlightColor,
    outline_color: "#000000",
    outline_width: look.outlineWidth,
    shadow_depth: look.shadowDepth,
    position: options.position,
    margin_v: 340,
    margin_h: 60,
    max_chars_per_line: 28,
    max_lines: 2,
    karaoke: options.karaokeSync,
  };
}
