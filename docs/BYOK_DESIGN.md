# Bring Your Own Keys (BYOK) & Advanced Settings Studio

* **Author:** Mohamed Aboelela
* **Date:** 2026-11-14

## Overview

Laqta v0.2.0 introduces Bring Your Own Keys (BYOK) credential management and an Advanced Settings Studio. It converts Laqta from an environment-variable-configured application into a local-first studio application where users manage AI credentials (OpenRouter, OpenAI-compatible / Ollama / LM Studio, Groq Whisper, AssemblyAI, Hugging Face) and runtime configuration directly in the interface.

The design enforces the following constraints:
- Credentials persist locally under POSIX file mode 0600 in SQLite (`user_settings` table in `qatta.db`) and a local settings file mirror.
- Cleartext secrets are never returned to the UI or logged; only cryptographically masked previews (e.g. `sk-or-v1-••••••••ef31`) and boolean presence flags are exposed.
- Remote inference remains gated behind fail-closed flags (`ALLOW_CLOUD_APIS` and `LLM_HOSTED_OPT_IN`), preventing silent external transmission of media or transcript text.
- The implementation introduces no AGPL dependencies, avoids background model pre-downloads, and remains within the 8 GB RAM / CPU-only Fedora Linux baseline.

---

## Analysis

### 1. Multi-Lens Brainstorm Findings

#### Lens 1: UX & Ergonomics (`egm-design`)
- **Workbench Architecture:** Replaces the static read-only 4-card audit (`CapabilitiesCard`) with a 5-tab settings workbench:
  1. **AI & BYOK (`ai`)**: Provider cards with masked credential fields, toggle visibility, connection status indicators, inline "Test Connection" actions, and model selector chips.
  2. **Speech Recognition (`asr`)**: Visual selection for transcription engine (`faster-whisper`, `groq_api`, `youtube_subs_first`), model profiles (fast/balanced/accurate), Silero VAD toggles, and Arablish technical prompt injection.
  3. **Ingestion & Media (`ingest`)**: URL ingestion toggle, YouTube language preferences (`ar.*,ar,en.*,en`), player client fallbacks, and cookie path configuration.
  4. **Storage & Cache (`storage`)**: Visual disk quota metrics, transcript cache counters, and a protected "Clear Transcript Cache" action with confirmation.
  5. **System Audit (`system`)**: Preserved runtime audit (FFmpeg with libass check, FFprobe, GPU/CPU) with an on-demand "Refresh Audit" button.
- **Feedback & State Safety:** A top action bar surfaces dirty-state tracking ("Unsaved Changes"), "Save Changes" with loading states, "Discard", and "Reset to Defaults". Toast notifications provide immediate feedback on connection tests, cache clearance, and persistence operations.
- **Privacy Disclosures:** Prominent bilingual banners clarify data boundaries between hosted gateways (OpenRouter, Groq) and loopback local servers (Ollama on `127.0.0.1:11434`).

#### Lens 2: Codebase Details & Precision Engineering (`egm-codebase-details`)
- **Database Schema:** Non-destructive schema addition to `backend/app/db/connection.py`:
  ```sql
  CREATE TABLE IF NOT EXISTS user_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
  );
  ```
- **Lifecycle & Synchronization:**
  - `SettingsService.init_and_sync()` executes during FastAPI application startup (`lifespan`), populating runtime `settings` attributes and synchronizing to `os.environ[f"QATTA_{k}"]` so child processes and core pipeline modules inherit updated values.
  - Updates update both SQLite and the in-memory singleton atomically.
  - An initial snapshot (`_initial_snapshot` and `_initial_env`) is cached at boot, allowing deterministic rollback during `reset_to_defaults()`.
- **Secret Safety Pipeline:**
  - `SECRET_FIELDS = {"LLM_API_KEY", "LLM_OPENROUTER_API_KEY", "GROQ_API_KEY", "ASSEMBLYAI_API_KEY", "HF_TOKEN"}`.
  - `SettingsResponse` uses `redact_secret()` to ensure raw tokens never leave the backend process.
  - Inbound candidate keys during "Test Connection" are evaluated in memory and discarded without persistence unless the user explicitly saves changes.

#### Lens 3: Strategic Architecture & Trust Boundaries (`egm-zoom-out`)
- **Local-First Boundary Integrity:** No SaaS account registration, no remote telemetry, and no cloud synchronization.
- **Fail-Closed Policy Gating:** Even when valid API credentials are saved, cloud calls remain blocked if `ALLOW_CLOUD_APIS=false` or `LLM_HOSTED_OPT_IN=false`. The system refuses remote execution with an explicit error rather than failing silently.
- **Hardware Invariant Preservation:** BYOK settings management runs purely on lightweight HTTP/JSON and SQLite operations, consuming negligible CPU cycles and adding 0 MB to peak memory, strictly protecting the 8 GB RAM budget.

#### Lens 4: Semantic & Domain Comprehension (`egm-comprehension`)
- **Clear Demarcation Between Local and Hosted LLMs:** The UI explicitly differentiates between:
  - *Local OpenAI-Compatible*: Ollama / LM Studio / llama.cpp running on loopback (`127.0.0.1`). Zero data leaves the machine; zero API key required.
  - *Hosted Gateways*: OpenRouter / Groq / AssemblyAI. Data leaves the machine to external servers; requires API key, privacy acknowledgement, and cloud API toggle.
- **Model Preset Clarity:** OpenRouter models tagged with `:free` (e.g., `minimax/minimax-m3.1-flash:free`, `meta-llama/llama-3.3-70b-instruct:free`) are labeled as zero-cost, but explicitly not local, preventing privacy confusion.
- **Granular Cache Semantics:** Cache clearance explicitly targets derived transcript JSON files (`cache/transcripts/`), leaving source media, project metadata, and user renders completely untouched.

#### Lens 5: Implementation Readiness & Verification (`egm-implementation-readiness`)
- **Backend Test Suite (`backend/tests/test_settings_api.py`):**
  - Verification of secret masking (`test_get_settings_redacted`).
  - Verification of partial PATCH updates and SQLite persistence (`test_patch_settings`).
  - Mocked HTTP probe testing for OpenRouter, Groq, and Ollama (`test_verify_provider_mocked`).
  - Cache clearance and factory reset verification (`test_clear_cache_and_reset`).
- **Frontend Test Suite (`frontend/src/tests/SettingsView.test.tsx`):**
  - Verification of tab switching and draft state changes.
  - Password visibility toggle and masked secret rendering.
  - Key verification trigger and latency badge rendering.
  - Regression assurance: backward compatibility with legacy tests expecting "System Runtime & Media Capabilities" text.
- **Verification Commands:**
  ```bash
  backend/.venv/bin/pytest backend/tests/test_settings_api.py -v
  npm --prefix frontend run typecheck
  npm --prefix frontend run test
  ```

#### Lens 6: Structural System Integrity (`egm-structural`)
- **Dependency & License Auditing:** Utilizes existing runtime libraries (`httpx`, `pydantic-settings`, `sqlite3`, `lucide-react`, `tailwindcss`). Zero new dependencies introduced; zero AGPL-3.0 libraries.
- **Network Boundaries:** Verification probes enforce strict 8.0-second timeouts (`httpx.AsyncClient(timeout=8.0)`) and reject non-HTTP schemes or malicious redirect loops.
- **Backward Compatibility:** All existing `.env` and environment variables continue to function as base defaults if no user overrides are present in SQLite.

---

## Goals vs. Non-Goals

### In-Scope Goals
- Provide a graphical Settings Studio for configuring application options (BYOK keys, ASR profiles, URL ingestion, storage, and capabilities audit).
- Persist credentials locally in SQLite (`user_settings`) and `settings.json` with restricted `0600` file permissions.
- Provide live, non-destructive connection and model verification probes with latency reporting.
- Enforce strict fail-closed cloud policies (`ALLOW_CLOUD_APIS` and `LLM_HOSTED_OPT_IN`) with explicit in-app privacy disclosures.
- Offer configuration presets for popular local engines (Ollama, LM Studio) and zero-cost hosted models (OpenRouter `:free`).
- Maintain full backward compatibility with `.env` workflows and existing test suites.

### Out-of-Scope Non-Goals
- Cloud account synchronization, user profiles, or multi-tenant secret management.
- Modifying the core media processing pipeline (no changes to VAD segmentation, atomic utterances, or candidate scoring algorithms).
- Introducing face-guided reframing, active-speaker detection, or audio-energy ranking.
- Auto-purchasing or managing external API subscriptions or billing.
- Introducing AGPL-licensed machine learning libraries or mandatory GPU dependencies.

---

## Alternatives Weighed

| Option Considered | Architectural Pros | Architectural Cons | Final Verdict |
| :--- | :--- | :--- | :--- |
| **A. Plain `.env` File Editing via UI** | Direct alignment with existing `pydantic-settings` loader. | Concurrency race conditions, comments/formatting destroyed on rewrite, difficult atomic updates, insecure file handling. | **Rejected by author:** Fragile file manipulation and loss of user formatting. |
| **B. Encrypted Keyring via OS (SecretService / Keyring)** | OS-level encryption for API keys. | Unreliable in headless/container environments, introduces heavy C-extensions/dependencies, fails on minimal Linux servers without D-Bus. | **Rejected by author:** High failure rate across headless Linux and containerized environments. |
| **C. SQLite `user_settings` + In-Memory Layer + 0600 Mode** | Native ACID transactions, zero new dependencies, works seamlessly across all Linux/Fedora installations, clean rollback/reset. | Requires explicit masking in API serialization layers. | **Adopted:** Preserves portable, local-first zero-dependency contract. |
| **D. Modal-Only Settings Dialog** | Low UI surface footprint. | Cramped interface; unable to properly present 5 distinct configuration domains (ASR, Ingestion, Storage, BYOK, Audit) cleanly. | **Rejected by author:** Fails usability requirements for multi-category configuration. |

---

## Key Decisions & Staging for Next Steps

### Key Decisions
1. **Local-First SQLite Storage with `0600` Mirror:** Settings and credentials reside in the `user_settings` table of `qatta.db`. File permissions for the data directory and any config mirrors are locked to `0600`.
2. **Never Echo Secrets:** The backend API strictly returns `redacted_*` previews. A key's presence is indicated by a boolean status flag, preventing XSS or inspection vectors from exfiltrating raw credentials.
3. **Synchronized Environment Propagation:** `SettingsService.init_and_sync()` propagates overrides to both `settings` properties and `os.environ["QATTA_*"]`, guaranteeing that pipeline subprocesses inherit updated configuration immediately.
4. **Honest, Bounded Probe Diagnostics:** Verification requests use an isolated 8-second timeout, returning exact latency numbers and specific error classifications (e.g., HTTP 401 Invalid Key, HTTP 429 Rate Limited, Connection Refused).

### Staging for Implementation
1. **Stage 1 (Schema & Backend Routes):** Verify and activate `user_settings` table in `backend/app/db/connection.py`, finalize `SettingsService`, and mount `/api/settings` routes.
2. **Stage 2 (API Test Verification):** Execute `test_settings_api.py` and `test_capabilities.py` across all CRUD, masking, verification, and reset scenarios.
3. **Stage 3 (Frontend Studio Workbench):** Mount `SettingsView` in `frontend/src/App.tsx`, verifying dark-mode styling, responsive tab navigation, and live test affordances.
4. **Stage 4 (Frontend Automated Checks):** Run `npm --prefix frontend run typecheck` and `npm --prefix frontend run test` to confirm full regression safety.
5. **Stage 5 (Documentation & Release):** Document BYOK configuration in `docs/PRD.md` and release notes for Laqta v0.2.0.
