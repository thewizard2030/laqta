# Lib

## Overview
Shared client utilities: canonical product branding and repository URLs, display formatters for durations, bytes, relative timestamps, and text sanitization, and score rationale extraction.

## Interface
- brand.ts: BRAND, REPO_URL, ISSUES_URL, DOCS_URL - Brand constants and repository links
- format.ts: formatDurationMs, formatDurationHuman - Millisecond duration formatters
- format.ts: formatBytes - Human-readable byte size formatter (KB, MB, GB)
- format.ts: formatRelativeTime - Relative time formatter (e.g. '2 hours ago')
- format.ts: cleanDisplayText - Text sanitizer stripping HTML entities and marker tags
- rationale.ts: pickMeaningfulRationale - Heuristic ranking rationale picker
- [API](./api/README.md): Type-safe HTTP and XHR backend client
- [Captions](./captions/README.md): Caption styling translators for ASS subtitles
- [I18n](./i18n/README.md): Bidirectional text handling and RTL formatting
- [Validation](./validation/README.md): Boundary validation for clip cut points

## Invariants
- formatDurationMs renders mm:ss or h:mm:ss deterministically from millisecond values without inventing values
- cleanDisplayText strips HTML entities, YouTube platform markers (>>), and collapses redundant whitespace

## Side Effects
- None

## Verification
- Run: `npm --prefix frontend test`
