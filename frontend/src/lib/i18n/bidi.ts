/**
 * Bidirectional text handling for transcript/captions UI (PRD §5 FR-14).
 *
 * Rule (honest, deterministic):
 * - Direction is decided by the FIRST STRONG directional character of the
 *   text (similar to HTML dir="auto"), covering Arabic, Hebrew and other
 *   RTL scripts in common Arabic-transcript workflows.
 * - Mixed-direction text (Arabic narration containing embedded Latin brand
 *   names or numbers, and vice versa) still needs ONE container direction
 *   from the base text; embedded runs rely on the browser's bidi algorithm.
 *   We additionally set `unicode-bidi: plaintext` on the text node so the
 *   paragraph still renders per first-strong semantics inside the container.
 */

const RTL_RANGES = [
  /\u0591-\u07FF/, // Hebrew + Arabic + N'Ko etc.
  /\uFB1D-\uFDFD/, // Hebrew/Arabic presentation forms
  /\uFE70-\uFEFC/, // Arabic presentation forms B
];

const RTL_TEST_RE = new RegExp(`[${RTL_RANGES.map((r: RegExp) => r.source).join("")}]`);

/** Latin or any strong LTR letter, used to detect mixed-direction content. */
const LTR_TEST_RE = /[A-Za-z\u00C0-\u024F]/;

export type TextDirection = "rtl" | "ltr";

export function detectTextDirection(text: string | null | undefined): TextDirection {
  if (!text) return "ltr";
  // First strong directional character wins (dir="auto" semantics without
  // depending on the browser implementation for test determinism).
  for (const char of text) {
    if (RTL_TEST_RE.test(char)) return "rtl";
    if (LTR_TEST_RE.test(char)) return "ltr";
    // Neutral characters (punctuation, digits, spaces) are skipped.
  }
  return "ltr";
}

export function isMixedDirection(text: string | null | undefined): boolean {
  if (!text) return false;
  return RTL_TEST_RE.test(text) && LTR_TEST_RE.test(text);
}

/**
 * Inline style for bidi-correct rendering inside an explicitly-directed
 * container. `unicodeBidi: plaintext` keeps presentation of mixed runs
 * predictable and testable without claiming glyph-level shaping quality.
 */
export function bidiContainerStyle(text: string | null | undefined): {
  unicodeBidi?: "plaintext";
} {
  return isMixedDirection(text) ? { unicodeBidi: "plaintext" } : {};
}

export function formatMsAsClock(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}
