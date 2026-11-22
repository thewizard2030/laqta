# Changelog

All notable changes to Laqta are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.3.0] — 2026-11-22

Scriptable Laqta — one pipeline, two entry points, no duplicated stage list.

### Added

- **`laqta run SOURCE`** — run the full pipeline headless, with no server and no browser. Flags: `--project-id`, `--work-dir`, `--stages` (comma-separated subset), `--force`, `--json`. `--json` emits NDJSON events (`run_start`, `stage_start`, `stage_end`, `run_end`, `error`, `cancelled`) carrying the **measured** `stage_timings_ms` from the manifest. Exit codes: `0` success, `1` failure, `130` interrupted.
- **`qatta/core/runner.py`** — the single source of truth for the pipeline: `PIPELINE_STAGES`, `register_default_stages()` and `run_pipeline()`. The backend job manager and the CLI both use it, so the stage order cannot drift between them.
- `PipelineOrchestrator.registered_stages` — the stages an orchestrator can actually run.
- **Hash-pinned locks for the optional profiles**: `backend/requirements-url-lock.txt` (1 package) and `backend/requirements-analysis-lock.txt` (31 packages), generated from the new `requirements-url.txt` / `requirements-analysis.txt` profiles.
- **`scripts/generate_lock.py --verify`** — an offline structural gate: every locked profile ships a lock, every requirement is pinned with a hash, no package is pinned twice, and the composed `all` profile includes every capability. Wired into CircleCI (`backend` job) and `scripts/check.sh`. `--check` remains the maintainer's freshness tool and is deliberately **not** a CI gate: it turns red when upstream publishes a new version even though nothing in the repository changed.
- Tests: `tests/test_runner.py` (15), `tests/test_cli_run.py` (13), `tests/test_generate_lock.py` (11), and `backend/tests/test_stage_registration.py` (3).

### Changed

- The backend job manager no longer owns a stage list. It delegates registration and execution to `qatta.core.runner` and keeps only what is genuinely its own: the UI progress percentages (`_PROGRESS_BY_STAGE`, asserted to match the pipeline) and the SQLite projection after each stage.
- `backend/requirements-all.txt` now composes the `asr`, `url` and `analysis` profiles with `-r` includes instead of restating their packages.
- README refresh in English and Arabic: navigation, system requirements, a CLI reference that matches `qatta/cli.py`, a feature matrix separating `[Supported]` / `[Optional]` / `[Not shipped]`, and Docker Compose labelled an experimental preview with the reason (the Dockerfile installs the `[asr]` extra and defines `QATTA_BIND_HOST`/`QATTA_BIND_PORT`, not `QATTA_HOST`/`QATTA_PORT`).

### Removed

- **`mediapipe` from the `analysis` and `all` extras.** Nothing imported it: stage `s06_reframe_subs` has a camera solver that consumes `FaceDetection` objects, but no detector produces them. It also installed `opencv-contrib-python` alongside `scenedetect`'s hard `opencv-python`, two packages providing the same `cv2` module.

### Fixed

- The `[analysis]` profile now resolves to exactly one `cv2` provider (`opencv-python`) instead of two silently shadowing each other.
- The README no longer claims the face/speaker camera solver works when the `[analysis]` extra is installed. It does not: no detector feeds it and the stage is not registered.

### Known limitations

- **The two policy proposals remain pending, deliberately.** `docs/DEPENDENCY_POLICY_PROPOSAL.md` and `docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md` carry a dated status note stating that `docs/POLICY.md` is unchanged and that the transitive `MPL-2.0` / `PSF-2.0` / `CC-BY-4.0` / `BlueOak-1.0.0` / `MIT-0` licences they audit are shipped but not covered by a written policy. Adopting them is a maintainer licensing decision, not an agent one.
- **`s07_render_learn` and `s06_reframe_subs` are not wired.** Both are implemented and unit-tested; neither is registered, and a test asserts that only `s06_render` is. `s07` is documented as library-only in its README.
- **Cancellation is at stage boundaries.** Ctrl-C lets the running stage finish before stopping; a second Ctrl-C stops immediately, and the manifest is never advanced past the last completed stage. Cancellation is never claimed to be instant.
- **`backend/requirements-lock.txt` is stale per `--check`** because upstream published newer versions. It was not regenerated in this release to avoid a gratuitous 42-package bump; `--verify` still passes, and the default profile installs reproducibly from the committed lock.
- **`backend/requirements-lock.txt` still resolves for Python 3.11** (the minimum supported interpreter) while the development virtualenv is 3.12; this is intentional and documented in `scripts/generate_lock.py`.

## [0.2.5] — 2026-11-15

Maintenance, licensing continuity, fixture remediation, and release-hardening update — permanently retaining the MIT License.

### Added

- Original synthetic Arabic technical WebVTT caption fixture ([`tests/fixtures/sample_captions_synthetic.ar.vtt`](tests/fixtures/sample_captions_synthetic.ar.vtt)) with `align:start position:100%` cue settings, mixed Arabic/English technical terminology, digits, and rolling-caption overlap.
- CircleCI 2.1 tag-triggered `release` workflow (`.circleci/config.yml`) with isolated release context `laqta-release-publishing` and stdlib HTTPS GitHub Release publisher ([`scripts/publish_github_release.py`](scripts/publish_github_release.py)) featuring SHA-256 digest / redirect-safe download verification, concurrency handling, archive hygiene validation, and unit tests ([`tests/test_publish_github_release.py`](tests/test_publish_github_release.py)).
- Copyright provenance, licensing continuity, dependency policy, and visual-asset governance documentation (`docs/PROVENANCE_AUDIT.md`, `docs/LICENSING.md`, `docs/LICENSING_DECISIONS.md`, `docs/DEPENDENCY_POLICY_PROPOSAL.md`, `docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md`, `docs/TRADEMARKS.md`, and historical audit record `docs/LICENSING_TRANSITION_AUDIT.md`).

### Changed

- Confirmed **MIT License** continuity across root `LICENSE`, `pyproject.toml`, `backend/pyproject.toml`, `frontend/package.json`, and documentation; explicitly rejected and superseded the previously evaluated MPL-2.0 transition proposal.
- Synchronized package and application manifests (`qatta`, `laqta-backend`, `laqta-frontend`) cleanly from `0.2.0` to `0.2.5`.
- Promoted CircleCI 2.1 as the authoritative CI and GitHub Release publishing pipeline; disabled automatic push/tag triggers in `.github/workflows/ci.yml` and `.github/workflows/release.yml` (retaining explicit `workflow_dispatch` fallback only) and updated `docs/CIRCLECI_MIGRATION.md`, `docs/RELEASING.md`, and dynamic CircleCI badges in `README.md` / `README.ar.md`.
- Updated `THIRD_PARTY_NOTICES.md` to correct PyAV lockfile licensing metadata (`av==18.1.0`, `BSD-3-Clause`), document transitive runtime dependencies (`typing-extensions`, `certifi`, `tqdm`), and distinguish dev/build-only frontend packages (`lightningcss`, `minimatch`, `caniuse-lite`, `@csstools/color-helpers`).

### Fixed

- Removed the unverified Arabic broadcast caption fixture (`tests/fixtures/sample_captions.ar.vtt`) from the active working tree and updated `tests/test_fixtures.py` and `tests/fixtures/README.md` to validate the synthetic caption track exclusively.
- Updated `docs/OPEN_SOURCE_BUSINESS_MODEL.md` and licensing documentation to remove stale MPL-2.0 transition assertions and separate third-party package licenses from Laqta first-party MIT code.

### Security

- Verified zero known high/critical production npm vulnerabilities (`npm audit --omit=dev --audit-level=high`) and zero known Python dependency vulnerabilities in the isolated Python 3.11 verification environment (`pip-audit --local`).
- Confirmed BYOK settings storage (`0700`/`0600` permissions), secret redaction, URL ingestion fail-closed gating, and cloud opt-in guards pass test verification.

### Known limitations

- **Historical archive erratum (`v0.1.0`–`v0.2.0`):** Immutable historical Git tags `v0.1.0` through `v0.2.0` and their corresponding source archives still contain the removed prior caption fixture (`sample_captions.ar.vtt`) without a recorded upstream source URL; historical tags were not rewritten.
- **Dependency lockfile & policy alignment:** Optional `[analysis]` and `[url]` extras remain unpinned in `backend/requirements-lock.txt`, and `docs/DEPENDENCY_POLICY_PROPOSAL.md` / `docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md` (covering `MPL-2.0`/`PSF-2.0`/`CC-BY-4.0`/`BlueOak-1.0.0`/`MIT-0` dependencies, `generated-brand-direction-reference.png`, and `BrandIcons.tsx` paths) await final maintainer approval alongside `docs/POLICY.md`.
- **Manual-only GitHub Actions fallback:** Release `v0.2.5` is published via CircleCI ([workflow `1a3a76df`](https://app.circleci.com/workflow/1a3a76df-da76-472a-a5f4-8a5631483787): `backend`, `frontend`, and `publish-release` all passed using restricted CircleCI Context `laqta-release-publishing`), creating [GitHub Release `v0.2.5`](https://github.com/thewizard2030/laqta/releases/tag/v0.2.5) from tag commit `8030cf5dd1a3acaa7b5f129a69e314f7739dc650` with asset `laqta-v0.2.5.tar.gz` (`5468774` bytes, SHA-256 `a7a0117c2e4c36a7d6a3944d9100628f6af85d400378dc1f4384b5cdc038019e`). All six `.github/workflows/` files remain explicit `workflow_dispatch` fallbacks only (GitHub Actions runners remain unavailable under the account billing lock).

## [0.2.0] — 2026-11-14

Bring Your Own Keys (BYOK) and the Advanced Settings Studio — local-first credentials and studio configuration without editing config files.

### Added

- **Bring Your Own Keys (BYOK) credential management**:
  - Secure local credential storage via SQLite `user_settings` table in `qatta.db` with atomic `settings.json` mirror.
  - POSIX filesystem isolation: directory mode `0700` and file mode `0600` enforced for database and mirror files, preventing unauthorized local user access without external keyring service dependencies.
  - Secret redaction and privacy: API credentials are never logged, serialized in plaintext error responses, or exposed through API reads. Previews use fixed masked prefixes/suffixes (`sk-or-...a1b2`).
  - Safe candidate key testing: `POST /api/settings/verify` performs lightweight connection probes in-memory with strict 8-second timeouts and redirect bounds, never persisting unconfirmed keys.
  - Fail-closed cloud privacy: remote API probes and execution strictly enforce `ALLOW_CLOUD_APIS=true` and `LLM_HOSTED_OPT_IN=true`.
- **5-Tab Advanced Settings Studio in the frontend**:
  - **AI & LLM Providers**: configure OpenRouter, local OpenAI-compatible endpoints (Ollama, LM Studio), Groq, and Hugging Face with connection testing.
  - **Speech Recognition**: configure Whisper model engines, VAD silence thresholds, and bilingual Arablish code-switching prompt text.
  - **Ingestion & Subtitles**: configure yt-dlp client profiles, subtitle language preferences, and cookie paths.
  - **Storage & Cache**: live disk usage breakdown with safe cache clearance that preserves source media and exported vertical shorts.
  - **System & Capabilities Audit**: inspect CPU cores, memory footprint, hardware acceleration status, and system dependency health.
  - Unsaved change tracking, discard controls, and factory reset dialog restoring boot-time snapshot defaults.
- **Continuous Integration & Infrastructure**:
  - CircleCI 2.1 pipeline with Smarter Testing (`.circleci/config.yml` and `.circleci/test-suites.yml`).
  - Concurrent `backend` (Python 3.12) and `frontend` (Node 22.14) test runners with deterministic checksum caching.
  - Smarter Testing test discovery covering all 42 backend test files and 18 frontend test suites with JUnit report generation.
- Automated API test suite in `backend/tests/test_settings_api.py` and frontend test suite in `frontend/src/tests/SettingsView.test.tsx`.

## [0.1.3] — 2026-10-22

The release that proves the ranking instead of asserting it.

### Added

- **The clip-selection benchmark** — a labelled, reproducible measurement of
  the ranking: precision, recall, F1, coverage and bad coverage, over a
  dataset whose labels are exact. It runs weekly in CI and fails when a
  metric regresses. The method, the results and the limits are in
  [docs/EVALUATION.md](docs/EVALUATION.md).
  _Measured: precision 0.92, recall 1.00, F1 0.96, coverage 0.96, bad
  coverage 0.11 — the ranking finds every labelled highlight and
  over-selects._
- Tests for the CPS arithmetic and the three scoring gates: the score is
  bounded, the weights renormalise over the measured components, an unknown
  archetype is an error, and every gate outcome is recorded in the evidence
  log.
- The benchmark also reports the **measured** stage times, so the performance
  numbers come from a run instead of an estimate.

### Fixed

- **The Arabic prior was applied to every transcript**, including English
  audio — where it made Whisper produce Arabic text for English speech and
  the transcript degraded into repetition. The prior now follows the
  language: Arabic and auto-detected audio keep it, an explicit non-Arabic
  profile does not.
- **The coverage gate measured the wrong thing.** The two suites ran in
  separate coverage sessions, so the core suite's contribution to the `qatta`
  package was discarded: the real number was 78.78 %, not the 59.83 % the
  baseline recorded. Both suites now write into one session, and the baseline
  holds the honest number.

### Changed

- The coverage floor is now the combined measurement, and the modules that
  produce a user-visible result (the renderer, the scorer, the CLI, the audio
  extractor, the ASR provider, the URL ingest) are covered by tests.

## [0.1.2] — 2026-10-21

The release that makes Laqta an application you launch, and proves it.

### Added

- **Release mode.** The API serves the built studio: the root opens the UI,
  deep links fall back to the SPA entry point and the API keeps working.
  `laqta studio --production` builds the studio and serves everything from
  <http://127.0.0.1:8000> — one command, one address, no second terminal.
- **A release proof.** `scripts/verify_release.sh` clones the repository
  into a temporary directory, installs it from scratch and drives the whole
  pipeline with a synthetic video: import → transcribe → rank → render →
  verify the MP4. It runs weekly and on every pull request that touches the
  backend, the core or the scripts.
- **An error boundary** in the studio: a single bad render no longer blanks
  the app. The panel states what happened, keeps the error message visible
  and offers "try again" / "reload".
- `laqta doctor --json` — the same report, machine-readable.
- `scripts/setup.ps1` — a first-class Windows install path.
- `docs/UPGRADING.md` and `docs/ARCHITECTURE.md`.
- Pre-commit hooks that run the same checks as CI.

### Fixed

- **The health endpoint no longer lies.** It reported "healthy" even when the
  job worker was dead — which means queued jobs would never run. It now
  reports the worker state and answers "degraded" when the worker is
  stopped; the studio's status pill follows it.
- **A silent clip was scored as if it had speech.** The silence threshold
  was zero for a digitally silent signal, so every frame fell _above_ it
  and the silence ratio came out as 0.0 instead of 1.0. A quiet clip could
  therefore score as if it were clear, voiced audio.
- **The analyser no longer aborts the pipeline** when ffmpeg cannot decode
  the source: scene cuts degrade to "none measured" instead of failing the
  stage.
- The **core test suite** no longer creates real projects in your own data
  directory (hermetic, like the backend suite).
- The **backend tests** are no longer affected by a frontend you happen to
  have built.

### Changed

- The backend suite runs in parallel (70 s → 37 s).
- The dev extras and the requirements files no longer drift apart.

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
  Scorecard workflow checks it (the _Pinned-Dependencies_ check).
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
  _and_ a key, and the UI discloses that transcript text leaves the device.
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

[Unreleased]: https://github.com/thewizard2030/laqta/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/thewizard2030/laqta/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/thewizard2030/laqta/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/thewizard2030/laqta/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/thewizard2030/laqta/releases/tag/v0.1.0
