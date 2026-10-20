# Changelog

All notable changes to Laqta are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

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

[Unreleased]: https://github.com/thewizard2030/laqta/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/thewizard2030/laqta/releases/tag/v0.1.0
