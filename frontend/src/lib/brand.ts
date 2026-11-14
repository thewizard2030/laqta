/**
 * Brand and repository constants.
 *
 * Official brand identity for Laqta (لقطة).
 * Single source of truth for brand tokens, typography, and repository URLs.
 */

export const BRAND = {
  /** Latin wordmark. */
  name: "Laqta",
  /** Arabic wordmark — "a take / a cut" (لقطة). */
  nameArabic: "لقطة",
  /** Official tagline from brand kit. */
  tagline: "Long Videos to Viral Shorts",
  /** One-line description used in docs and release notes. */
  description:
    "Local-first studio that turns long videos into ranked vertical Shorts — on your own machine.",
} as const;

/** Official Brand Colors extracted from Laqta Brand Kit source vector definitions */
export const BRAND_COLORS = {
  /** Main dark background (Ink) */
  ink: "#070A14",
  /** Deep Navy for surfaces / light-mode text */
  deepNavy: "#10162B",
  /** Violet — gradient start */
  violet: "#A72BFF",
  /** Purple — gradient middle */
  purple: "#5637F5",
  /** Cyan — gradient end / live status */
  cyan: "#00C9E8",
  /** White — primary text on dark */
  white: "#F8FAFF",
  /** Muted slate — secondary text */
  muted: "#AAB6CC",
  /** Surface panel background */
  surface: "#0E1424",
  /** Subtle hairline border */
  border: "rgba(148, 163, 184, 0.14)",
} as const;

/** Canonical repository URL (no trailing slash). */
export const REPO_URL = "https://github.com/thewizard2030/laqta";

/** `owner/repo`, used for badges and issue links. */
export const REPO_SLUG = "thewizard2030/laqta";

/** Issue tracker. */
export const ISSUES_URL = `${REPO_URL}/issues`;

/** Releases page. */
export const RELEASES_URL = `${REPO_URL}/releases`;

/** Security advisories (private reporting). */
export const SECURITY_URL = `${REPO_URL}/security/advisories/new`;

/** Documentation entry point. */
export const DOCS_URL = `${REPO_URL}/tree/main/docs`;
