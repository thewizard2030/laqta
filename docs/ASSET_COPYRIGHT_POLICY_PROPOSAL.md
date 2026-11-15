# Laqta — Asset Copyright Policy Proposal (MIT Continuity)

**Project Software License:** **MIT License** (permanently retained; proposed MPL-2.0 transition rejected)  
**Current Trademark Guideline:** [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md)  
**Document Status:** **Proposed Asset Rights Policy — Not Adopted**  
**Date:** November 15, 2026

> [!IMPORTANT]
> **Copyright vs. Trademark Distinction:** [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) regulates brand identity, naming, and false endorsement; **it is NOT an artwork copyright license**. Every non-code visual asset directory requires an independent copyright disposition alongside (and separate from) MIT software licensing and trademark rules.

---

## 1. Proposed Asset-by-Asset Matrix

Each audited asset group is mapped to one of four explicit copyright dispositions:

1. **Separate explicit copyright license** (e.g., `CC BY 4.0`, conditional on verified ownership)
2. **Covered under the repository MIT License** (software/icon copyright, subject to trademark exclusions in [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md))
3. **Excluded with copyright reserved, with a narrowly defined permission for official package redistribution**
4. **Excluded from future public distributions pending provenance verification**

| Asset Group & Repository Path                                                                                                                           | Verified File Inventory                                                                                                       | Current Policy Conflict / Gap                                                                                                                                                                                                               | Proposed Copyright Disposition                                                                                  | Rationale & Required Maintainer Condition                                                                                                                                                                                                                                                                                            |
| :------------------------------------------------------------------------------------------------------------------------------------------------------ | :---------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **[`Laqta_Brand_Kit/`](file:///home/thewizard/Qatta/Laqta_Brand_Kit)** (`svg/`, `png/`, `README.md` — excluding `guidelines/`)                          | **30 files:** `11` SVGs, `18` PNGs, `1` `README.md`                                                                           | Historical [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) excluded `Laqta_Brand_Kit/` without specifying explicit copyright permission for verbatim/OS package redistribution allowed in `TRADEMARKS.md` §3.2–§3.3.  | **3. Excluded with copyright reserved, with a narrowly defined permission for official package redistribution** | Keeps copyright control over official logos/wordmarks while granting explicit copyright permission to redistribute unchanged assets in official Laqta builds, OS packages (`Fedora`/`Debian`/`Flatpak`), and unmodified source mirrors, strictly subject to [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md). |
| **[`Laqta_Brand_Kit/guidelines/`](file:///home/thewizard/Qatta/Laqta_Brand_Kit/guidelines)** (`generated-brand-direction-reference.png`)                | **1 file:** `935,124` bytes (`file` type: `RIFF (little-endian) data, WebP image, lossless, with alpha` — misnamed `.png`)    | AI-generated concept art with unverified generation tool, account tier/terms, and human-authorship copyrightability; also carries a `.png`/WebP format mismatch.                                                                            | **4. Excluded from future public distributions pending provenance verification**                                | Do **not** assume AI-generated imagery has unrestricted copyright or redistribution rights. Exclude from future source/binary release tarballs until tool terms, plan tier, redistribution rights, and extension/format fix (or removal) are approved by the maintainer.                                                             |
| **[`packaging/icons/`](file:///home/thewizard/Qatta/packaging/icons)** (`hicolor/`)                                                                     | **9 files:** `8` PNGs (`16x16`–`512x512`), `1` SVG (`laqta.svg`)                                                              | Must stay aligned with `Laqta_Brand_Kit/` (these 9 icons are byte-identical copies of `Laqta_Brand_Kit/` icons, distinct from `packaging/install.sh` and `packaging/laqta.desktop` which carry MIT software code).                          | **3. Excluded with copyright reserved, with a narrowly defined permission for official package redistribution** | Aligns `packaging/icons/` with `Laqta_Brand_Kit/` (keeping scripts `install.sh` and `laqta.desktop` under MIT while granting Linux/XDG packagers explicit copyright permission to install unmodified Laqta app icons per `TRADEMARKS.md` §3.2).                                                                                      |
| **[`frontend/public/`](file:///home/thewizard/Qatta/frontend/public)**                                                                                  | **11 files:** `5` SVGs, `5` PNGs, `1` `README.md` (copied verbatim into `frontend/dist/` during Vite build)                   | Identical brand icons/logos from `Laqta_Brand_Kit/` are bundled into `frontend/dist/`; self-hosters and packagers need explicit copyright authority to serve them with compiled UI code.                                                    | **3. Excluded with copyright reserved, with a narrowly defined permission for official package redistribution** | Grants downstream builders and self-hosters of unmodified or attribution-compliant Laqta deployments copyright permission to bundle and serve these static icon files inside `frontend/dist/`, while requiring rebranding under `TRADEMARKS.md` §3.4 for modified commercial products.                                               |
| **[`docs/assets/`](file:///home/thewizard/Qatta/docs/assets)** (diagrams, social cards & `screenshots/`)                                                | **10 files:** `2` SVGs (`social-preview.svg`, `workflow-demo.svg`), `4` root PNGs + `4` byte-identical PNGs in `screenshots/` | Currently omitted from [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) scope; includes both workflow diagrams and UI screenshots (`laqta-dashboard.png`, `laqta-studio.png`, `social-preview.png`, `laqta-logo.png`). | **1. Separate explicit copyright license** _(recommended: `CC BY 4.0`)_                                         | General documentation diagrams and UI screenshots (excluding any unverified external imagery) fit cleanly under **CC BY 4.0** (matching `CODE_OF_CONDUCT.md` / standard docs licensing), **subject to maintainer confirmation** of authorship/rights in the UI screenshots and `TRADEMARKS.md` restrictions on embedded Laqta marks. |
| **[`frontend/src/components/ui/BrandIcons.tsx`](file:///home/thewizard/Qatta/frontend/src/components/ui/BrandIcons.tsx)** (`GitHubIcon`, `YouTubeIcon`) | **2 inline `<svg><path d="..."/></svg>` components**                                                                          | `THIRD_PARTY_NOTICES.md` justifies inclusion because links point to GitHub/YouTube, but **nominative trademark use does not clear copyright in copied SVG path geometry** without verifying the upstream SVG icon source/license.           | **4. Excluded from future public distributions pending provenance verification**                                | Verify the exact origin and license of both `<path d="...">` strings (for instance, Simple Icons under `CC0-1.0` vs. official GitHub/YouTube brand kits) and vendor compliance before `v0.2.5`, or replace with documented `CC0-1.0` / MIT icons or plain text/documented UI marks.                                                  |

---

## 2. Detailed Policy Specifications

### 2.1 `Laqta_Brand_Kit/` (Core Logos, Wordmarks, Icons & Banner)

- **Proposed Rule:** Copyright in all 30 original brand-kit files (`svg/`, `png/`, `README.md`) remains reserved by the maintainer. However, downstream users, Linux distribution packagers, and repository mirrors receive a non-exclusive copyright license solely to **copy, bundle, and distribute those files unchanged** as part of unmodified Laqta source releases, official binary/OS packages, and verbatim mirrors — provided trademark usage complies with [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md).
- **Fork Obligation:** Anyone creating a substantially modified product required to rebrand under `TRADEMARKS.md` §3.4 does **not** receive copyright or trademark permission to retain Laqta brand-kit graphics in their rebranded product.

### 2.2 `Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png`

- **Verified Technical & Provenance Issues:**
  1. Actual binary header via `file` is **`RIFF (little-endian) data, WebP image, lossless, with alpha`**, not PNG (`935,124` bytes; intentionally not renamed pending maintainer direction).
  2. Documented in [`Laqta_Brand_Kit/README.md`](file:///home/thewizard/Qatta/Laqta_Brand_Kit/README.md) as an AI-generated design direction reference board.
- **Proposed Rule:** Do **not** include under MIT, CC-BY-4.0, or official brand-kit redistribution grants. Either **remove/exclude from future public release tarballs** (for example via `.gitattributes` `export-ignore` or directory removal once maintainer approves) or retain internally only after documenting the exact AI generation tool, subscription tier, commercial/redistribution terms, and fixing the `.webp` extension.

### 2.3 `packaging/icons/`

- **Conflict Fix:** Explicitly distinguish [`packaging/icons/`](file:///home/thewizard/Qatta/packaging/icons) from MIT code files ([`packaging/install.sh`](file:///home/thewizard/Qatta/packaging/icons) — specifically keeping `install.sh` and [`packaging/laqta.desktop`](file:///home/thewizard/Qatta/packaging/laqta.desktop) under MIT while governing the 9 icon files under the same narrow package-redistribution copyright grant as Section 2.1) so OS packagers (Fedora/Debian/Flatpak) face zero ambiguity.

### 2.4 `frontend/public/`

- **Build Output Alignment:** Because Vite copies [`frontend/public/`](file:///home/thewizard/Qatta/frontend/public) verbatim into `frontend/dist/`, self-hosters and packagers shipping the built studio UI must have copyright permission to serve these 11 files unchanged alongside MIT frontend code. Section 2.1's narrow unchanged-package redistribution permission resolves this without waiving trademark boundaries (`TRADEMARKS.md`).

### 2.5 `docs/assets/` (Diagrams & Screenshots)

- **Recommended License (`CC BY 4.0`):** Once the maintainer confirms all UI screenshots (`laqta-dashboard.png`, `laqta-studio.png`, `social-preview.png`, `laqta-logo.png`, plus duplicates in `screenshots/` — confirming no third-party video frames or unowned thumbnails appear inside the captured app frames) and SVGs (`workflow-demo.svg`, `social-preview.svg`) are 100% first-party creations, place `docs/assets/` under **Creative Commons Attribution 4.0 International (CC BY 4.0)**, expressly reserving brand trademarks under `TRADEMARKS.md`.
- **Clean-Up Note:** The 4 root PNGs in `docs/assets/` are byte-identical to the 4 files in `docs/assets/screenshots/`; maintainer may optionally deduplicate paths before `v0.2.5`.

### 2.6 `frontend/src/components/ui/BrandIcons.tsx` (`GitHubIcon`, `YouTubeIcon`)

- **Proposed Action Before `v0.2.5`:**
  1. Trace the exact SVG `<path d="...">` coordinates for `GitHubIcon` and `YouTubeIcon` against their source (e.g., Simple Icons vs. official GitHub Octocat / YouTube play-button brand kits).
  2. Note that GitHub's and YouTube's official brand guidelines impose strict logo-usage conditions independent of open-source licenses; if exact path provenance cannot be documented cleanly or fails brand-kit requirements, replace the components (e.g., documented `CC0-1.0` paths with vendor-guideline check, or generic Lucide icons / text links).

---

## 3. Relationship to Future `docs/LICENSING.md` & `REUSE.toml` Implementation

Upon maintainer approval (in a future implementation phase):

1. Update [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) §4 so `packaging/icons/`, `frontend/public/`, `docs/assets/`, and `Laqta_Brand_Kit/` follow one consistent asset copyright architecture alongside Laqta's permanent MIT software license.
2. Add root `REUSE.toml` only if/when adopted by the maintainer once every directory's exact SPDX expression (`MIT`, `CC-BY-4.0`, `LicenseRef-Laqta-Brand-Asset` or `CopyrightReserved`, etc.) has been approved (historically considered MPL-2.0 is rejected).
