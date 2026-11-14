# Laqta v0.2.0 — BYOK & Advanced Settings Studio

**Release Title:** Laqta v0.2.0 — BYOK & Advanced Settings Studio  
**Tag:** `v0.2.0`  
**Author:** Mohamed Aboelela  
**Date:** 2026-11-14  

---

## 🌟 Overview

Laqta **v0.2.0** marks a major leap in developer ergonomics, provider choice, and local security. Users can now configure supported AI providers, speech-recognition models, ingestion policies, and storage quotas directly through a polished, dark-mode **5-tab Advanced Settings Studio** in the frontend, without editing `.env` or configuration files.

Every credential and preference is stored **locally on your machine** under strict POSIX file permissions (`0600`/`0700`), with zero cloud leakage, full SSRF protection, and fail-closed privacy guardrails.

---

## 🚀 Key Highlights & New Capabilities

### 1. Bring Your Own Keys (BYOK) Studio
- **Supported Providers:** OpenRouter, Groq, Mistral, Cerebras, DeepSeek, Anthropic, and Hugging Face.
- **Live Connection Probes:** Test API keys in real time via `POST /api/settings/verify` with instant status feedback and latency tracking.
- **Fail-Closed Privacy:** Cloud API requests are blocked unless `ALLOW_CLOUD_APIS=true` and `LLM_HOSTED_OPT_IN=true` are explicitly enabled by the user.
- **Safe Editing:** Submitting masked previews (e.g., `sk-or-...a1b2`) preserves the existing key without overwriting it.

### 2. Five-Tab Advanced Settings Experience
1. **AI Providers:** Manage API keys, model selections, base URLs for OpenAI-compatible endpoints (Ollama, LM Studio), and run live health probes.
2. **Speech Recognition:** Switch Whisper model profiles (`tiny`, `base`, `small`, `turbo`), configure beam search sizes, and customize bilingual Arablish code-switching prompts.
3. **Ingestion & Policy:** Explicitly manage URL ingestion toggles (`yt-dlp`), per-import rights confirmation, and cookie configurations.
4. **Storage & Cache:** Live disk space inspection with safe transcript cache clearing that preserves original footage and rendered shorts.
5. **System Audit:** Real-time host hardware audit (CPU cores, RAM capacity, GPU acceleration) and media engine inspection (`ffmpeg`, `libass`).

### 3. Local-First Credential Security Model
- **SQLite Persistence:** Settings persist in the `user_settings` table within `~/.local/share/qatta/qatta.db` alongside an atomic `settings.json` mirror.
- **Filesystem Permissions:** The database directory enforces `0700` and files enforce `0600` (`-rw-------`).
- **Secret Redaction:** Keys are never transmitted in plaintext over API responses or printed in logs; only masked previews are returned.
- **SSRF Defense:** Probes reject link-local and cloud metadata addresses (`169.254.169.254`, `metadata.google.internal`) and disable automatic HTTP redirects.
- **Transparency Notice:** Secrets are stored unencrypted at rest within the local filesystem-restricted SQLite database. Security relies on host OS permission isolation.

### 4. CircleCI Smarter Testing Migration
- Continuous integration migrated to **CircleCI 2.1** with Linux Docker convenience images (`cimg/python:3.12` and `cimg/node:22.14`).
- Smarter Testing enabled via `.circleci/test-suites.yml`, auto-discovering 42 Python test files and 18 Vitest test suites.
- Checksum-based caching for instant dependency resolution.

---

## 🧪 Verification & Quality Report

| Quality Gate | Metric / Total | Status |
| :--- | :--- | :--- |
| **Backend API Tests** | 295 passed, 2 skipped | ✅ 100% Pass |
| **Core Pipeline Tests** | 219 passed, 1 skipped | ✅ 100% Pass |
| **Frontend Tests** | 116 passed across 18 test files | ✅ 100% Pass |
| **Code Coverage** | **79.31%** (Baseline: 78.78%) | ✅ No Regression |
| **Clip Ranking Benchmark** | Precision 0.92, Recall 1.00, F1 0.96 | ✅ 0 Regressions |
| **Linters & Formatters** | `ruff check`, `ruff format`, `eslint`, `prettier` | ✅ Clean |
| **Version Consistency** | Synchronized across 5 manifest files | ✅ 0.2.0 |
| **Fedora Desktop Entry** | `desktop-file-validate packaging/laqta.desktop` | ✅ Valid |

---

## 📦 Getting Started with v0.2.0

### Run via Docker
```bash
git clone https://github.com/thewizard2030/laqta.git
cd laqta
docker compose up
```

### Local Dev Setup
```bash
./scripts/setup.sh
./scripts/dev.sh
```

Navigate to **http://localhost:5173** to launch the studio.
