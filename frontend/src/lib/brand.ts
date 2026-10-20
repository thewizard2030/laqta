/**
 * Brand and repository constants.
 *
 * Single source of truth for the product name and every outbound project URL,
 * so a rename or a move of the repository is a one-line change.
 */

export const BRAND = {
  /** Latin wordmark. */
  name: "Laqta",
  /** Arabic wordmark — "a take / a cut". */
  nameArabic: "لقطّة",
  /** Short promise shown under the wordmark. */
  tagline: "Long Videos → Viral Shorts",
  /** One-line description used in docs and release notes. */
  description:
    "Local-first studio that turns long videos into ranked vertical Shorts — on your own machine.",
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
