import { describe, it, expect } from "vitest";
import { buildCaptionStyle } from "../lib/captions/style";
import type { CaptionStyleOptions } from "../features/studio/types";

const base: CaptionStyleOptions = {
  preset: "neon-glow",
  fontFamily: "Noto Sans Arabic",
  fontSize: "lg",
  position: "bottom",
  textColor: "#FFFFFF",
  highlightColor: "#00F2FE",
  karaokeSync: true,
};

describe("buildCaptionStyle", () => {
  it("maps the size pills to real ASS pixel sizes", () => {
    expect(buildCaptionStyle({ ...base, fontSize: "sm" }).font_size).toBe(76);
    expect(buildCaptionStyle({ ...base, fontSize: "base" }).font_size).toBe(94);
    expect(buildCaptionStyle({ ...base, fontSize: "lg" }).font_size).toBe(110);
    expect(buildCaptionStyle({ ...base, fontSize: "xl" }).font_size).toBe(132);
  });

  it("forwards the colours, position and karaoke flag", () => {
    const style = buildCaptionStyle({
      ...base,
      position: "top",
      textColor: "#FACC15",
      highlightColor: "#A855F7",
      karaokeSync: false,
    });
    expect(style.position).toBe("top");
    expect(style.foreground_color).toBe("#FACC15");
    expect(style.highlight_color).toBe("#A855F7");
    expect(style.karaoke).toBe(false);
  });

  it("gives every preset its own outline and shadow", () => {
    const neon = buildCaptionStyle({ ...base, preset: "neon-glow" });
    const bold = buildCaptionStyle({ ...base, preset: "bold-outline" });
    const minimal = buildCaptionStyle({ ...base, preset: "minimalist" });
    expect(neon.outline_width).toBe(6);
    expect(neon.shadow_depth).toBe(3);
    expect(bold.outline_width).toBe(9);
    expect(bold.shadow_depth).toBe(0);
    expect(minimal.outline_width).toBe(3);
    expect(minimal.shadow_depth).toBe(0);
  });

  it("always renders bold captions inside the 1080x1920 safe area", () => {
    const style = buildCaptionStyle(base);
    expect(style.bold).toBe(true);
    expect(style.max_lines).toBe(2);
    expect(style.margin_v).toBeGreaterThanOrEqual(300);
    expect(style.margin_h).toBe(60);
  });
});
