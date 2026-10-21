# Changelog

All notable changes to Laqta are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.1] — 2026-10-21

A hardening release: no known vulnerabilities, a reproducible CI, and the
fail-closed defaults the product promises.

### Security

- **The frontend toolchain is fully upgraded** — Vitest 5, Vite 8, Tailwind 4,
  React 19 and Lucide 1. `npm audit` now reports **0 vulnerabilities**, down
  from 13. The critical one was `tinypool` (a prototype-pollution RCE in the
  test worker pool), reached through Vitest 2.
- **URL ingestion is fail-closed.** It shipped enabled; it now ships
  **disabled** and needs an explicit `QATTA_ENABLE_URL_INGESTION=true`. The
  policy, the env template, the error messages and the tests agree.
- **Every GitHub Action is pinned to a full commit SHA**, and the OpenSSF
  Scorecard workflow checks it (the *Pinned-Dependencies* check).
- The CI runners are pinned to `ubuntu-24.04` before `ubuntu-latest` moves
  to Ubuntu 26.

### Fixed

- The job panel read the clock **during render**, which made the elapsed time
  non-reproducible. It now comes from a one-second state clock, so it also
  ticks on its own between polls.
- The state resets that ran inside effects (thumbnail failure, clip
  pagination, the canvas scrubber, the YouTube dialog) are adjusted during
  render instead. ESLint is at **zero warnings**, not zero errors.
- The **core test suite is hermetic**: it used to create real projects in the
  developer's own data directory.
- `laqta doctor` now reports whether the API and the studio are actually
  running, not just what is installed.

### Added

- `laqta studio` — runs the API and the studio frontend together.
- `scripts/check.sh` — every quality gate in one command, exactly like CI.
- Coverage is measured in CI and gated on non-regression
  (`config/coverage-baseline.json`).
- `docs/ARCHITECTURE.md` — the module map, the manifest lifecycle and where
  to change things.
- The GitHub and YouTube marks are now Laqta's own inline SVGs (Lucide v1
  removed its brand icons).

### Changed

- Tailwind v4 is CSS-first: the theme moved from `tailwind.config.js` into
  an `@theme` block in `index.css`, and the gradient utilities were renamed
  (`bg-gradient-to-*` → `bg-linear-to-*`). The rendered result is unchanged.
- The Node baseline is **22.12+** (the Vitest 5 requirement).

## [0.1.0] — 2026-10-20

The first public release. Laqta turns long videos into ranked vertical Shorts
on your own machine — no account, no upload, no telemetry.

### Added

- **Local studio** — React + TypeScript workbench: import a video, review the
  ranked clip candidates, trim and stabilise a clip, style the captions and
  export a 1080×1920 MP4.
- **Manifest pipeline** (`qatta/`) — a Pydantic-validated manifest drives the
  stages: ingest → transcribe → rank → render, with an atomic, resumable
  state file per project.
- **Local speech recognition** — faster-whisper on CPU with a two-pass
  strategy: a fast full pass for the transcript, then word-level re-timing
  only for the clips that are actually rendered.
- **Explainable clip ranking** — every candidate carries a Clip Potential
  Score (0–100) with the per-feature rationale that produced it. The score is
  a heuristic editorial quality signal, **not** a prediction of views.
- **Arabic-first captions** — right-to-left subtitle layout, FSI/PDI isolates
  and mirrored line handling, with a burned-in `.ass` export.
- **Honest capability reporting** — the UI and the `laqta doctor` command
  report exactly what is installed and what is missing; optional components
  are never presented as working features.
- **Optional URL import** — yt-dlp based, gated behind
  `QATTA_ENABLE_URL_INGESTION` and a per-import rights confirmation.
- **Optional hosted ranker** — OpenRouter, Groq, AssemblyAI and local
  OpenAI-compatible endpoints, all fail-closed: they need an explicit opt-in
  *and* a key, and the UI discloses that transcript text leaves the device.
- **Command line** — `laqta doctor`, `laqta serve`, `laqta models`.
- **Release tooling** — a pinned, hash-verified dependency lock, a version
  consistency check across every manifest, and a one-command setup script.

### Security

- The API binds to `127.0.0.1` by default and enforces an explicit CORS
  allow-list (never a wildcard).
- Media processing never runs on a request handler: work is queued, persisted
  and reported with real progress.
- Transcripts and media metadata are treated as untrusted data and are never
  interpolated into shell commands.

[Unreleased]: https://github.com/thewizard2030/laqta/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/thewizard2030/laqta/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/thewizard2030/laqta/releases/tag/v0.1.0
