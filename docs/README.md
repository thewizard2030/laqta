# Laqta Documentation Center

Welcome to the **Laqta (لقطة)** documentation hub. Here you will find architectural specifications, privacy and security policies, performance benchmarks, and contributor guides.

---

## 🧭 Navigation Index

### 🚀 Getting Started
- **[Quick Start & Installation](../README.md#-quick-start)**: Step-by-step native Linux setup and Docker container deployment.
- **[Hardware & System Doctor](../README.md#-check-your-machine-laqta-doctor)**: Verify your local CPU, FFmpeg with `libass`, Faster-Whisper, and storage permissions with `laqta doctor`.
- **[Upgrading Guide](UPGRADING.md)**: Release upgrade paths, database migration notes, and backwards-compatibility guarantees.
- **[Transcription Integration Test Guide](TRANSCRIPTION_INTEGRATION_TEST_GUIDE.md)**: How to run integration tests against local Faster-Whisper and mock providers.

### 🏛️ Product & Architecture
- **[Product Requirements Document (PRD)](PRD.md)**: Product scope, user personas, functional specifications, and delivery milestones.
- **[System Architecture](ARCHITECTURE.md)**: Subsystem boundaries, FastAPI local backend, SQLite schema, and the manifest pipeline.
- **[Evaluation & Ranking Benchmarks](EVALUATION.md)**: Measured precision, recall, and F1 benchmarks for candidate clip selection.
- **[Performance & Memory Benchmarks](PERFORMANCE.md)**: Two-pass transcription profiles (`fast`, `balanced`, `accurate`) and 8 GB RAM memory envelope.
- **[Transcription Tradeoffs](TRANSCRIPTION_TRADEOFFS.md)**: In-depth analysis of speed, accuracy, and memory tradeoffs across local and hosted ASR.
- **[Caption Quality Assurance](CAPTION_QA.md)**: RTL text layout verification, FSI/PDI directional isolates, and subtitle burn-in testing.
- **[Brand Identity & Design System](BRANDING.md)**: Official Laqta brand kit, color palette (violet/cyan dark theme), typography, and asset specifications.

### 🔒 Privacy & Security
- **[Data & Privacy Policy](POLICY.md)**: The core contract with users — local-first defaults, fail-closed cloud gates, and telemetry policy.
- **[BYOK Design & Credential Security](BYOK_DESIGN.md)**: Bring Your Own Keys architecture, local SQLite persistence, POSIX `0600`/`0700` filesystem isolation, and SSRF prevention.
- **[Security Policy](../SECURITY.md)**: Threat model, vulnerability reporting channel, and private disclosure timeline.
- **[OpenRouter Integration](OPENROUTER.md)**: Free and hosted model integration guidelines, headers, and opt-in boundaries.
- **[Third-Party Notices](../THIRD_PARTY_NOTICES.md)**: Open-source licenses for all direct dependencies and runtime components.

### 🛠️ Development & Operations
- **[Contributing Guide](../CONTRIBUTING.md)**: Development environment setup, coding style (Ruff, ESLint, Prettier), and pull request workflow.
- **[Code of Conduct](../CODE_OF_CONDUCT.md)**: Community standards and participant expectations.
- **[CircleCI Migration](CIRCLECI_MIGRATION.md)**: CircleCI 2.1 Smarter Testing infrastructure, test discovery specs, and caching strategy.
- **[Release Process](RELEASING.md)**: Pre-release verification checklists, manifest synchronization, and tag signing.
- **[Release Notes v0.2.0](RELEASE_NOTES_v0.2.0.md)**: What's new in v0.2.0 — BYOK & Advanced Settings Studio.
- **[Drift Report](DRIFT_REPORT.md)**: Codebase and documentation audit report.

---

## 📦 Core Package vs. Application

- **`qatta/`**: The core manifest-based pipeline engine (schema, config, stages, CLI). It is deliberately free of web frameworks and licensed under MIT.
- **`backend/`**: The local FastAPI application binding exclusively to `127.0.0.1:8000`, providing the REST API, SQLite repository, and background job manager.
- **`frontend/`**: The React 19 + TypeScript + Vite studio workbench providing the interactive timeline, vertical video preview, and settings studio.
