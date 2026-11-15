# Laqta — Open-Source Business & Product Architecture Model

**Document Version:** 1.4 (MIT Continuity Update)  
**Status:** Architecture & Governance Specification (Updated for Permanent MIT Continuity)  
**Governing Open-Source License:** **MIT License** (Permanently retained; proposed MPL-2.0 transition rejected)  
**Current Baseline Release:** `v0.2.0` (MIT License) -> `v0.2.5` Maintenance Release (MIT License)

---

## 1. Executive Summary & Core Philosophy

**Laqta** (لقطة) is an open-source, local-first long-video-to-vertical-Shorts studio designed to give video creators complete sovereignty over their media, their editing workflow, and their data.

The project's product and commercial model rests on three foundational principles:

1. **Uncompromised Local-First Capability:** Every core capability—audio extraction, speech recognition, candidate segmentation, heuristic ranking, and vertical video rendering—runs entirely on the creator's machine for free, offline, and without accounts.
2. **Permissive Open Source (`MIT`):** The foundational software is permanently licensed under the [**MIT License**](file:///home/thewizard/Qatta/LICENSE), providing maximum freedom for creators, developers, OS packagers, and commercial integrators while preserving trademark boundaries in [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md).
3. **Sustainable Commercialization Without Paywalls on Local Hardware:** Long-term project funding is built on optional convenience services, metered cloud compute, enterprise support, and community funding—**never by paywalling, watermarking, or artificially limiting local functionality**.

> [!IMPORTANT]
> **Roadmap & License Decision:**
>
> - **Permanent MIT Decision:** Earlier revisions of this document evaluated adopting MPL-2.0 at `v0.2.5`. The maintainer **rejected** that transition; Laqta permanently retains the **MIT License**.
> - **Product Commitments vs. License Terms:** Free local processing and free desktop applications are **maintainer product commitments**, not license restrictions. The MIT License permits unrestricted use, modification, and commercial distribution.
> - **Prospective Framing:** Optional paid cloud services and official desktop installers described herein represent prospective future offerings and are **not asserted as existing or operational in `v0.2.0` or `v0.2.5`**.

---

## 2. The Six Product & Service Pillars

```
+-----------------------------------------------------------------------------------------+
|                                    LAQTA ECOSYSTEM                                      |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  +-------------------------------------+   +-----------------------------------------+  |
|  |           1. LAQTA WEB              |   |            2. LAQTA DESKTOP             |  |
|  |           (Free Studio)             |   |        (Free Official Application)      |  |
|  |                                     |   |                                         |  |
|  |  * License: MIT                     |   |  * License: Free official distribution  |  |
|  |  * Self-hostable browser workbench  |   |  * Tauri 2 host + React/Vite workbench  |  |
|  |  * Full UI & 5-tab settings studio  |   |  * Native OS installer packages         |  |
|  |  * Runs on local localhost server   |   |  * Automated background service launch  |  |
|  +-------------------------------------+   +-----------------------------------------+  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  |                          3. FREE LOCAL-FIRST PROCESSING                           |  |
|  |                                                                                   |  |
|  |  * 100% free offline execution on user's own CPU/GPU hardware                     |  |
|  |  * faster-whisper ASR, CPS heuristic ranking, ASS/SRT captioning, FFmpeg render    |  |
|  |  * BYOK API credentials stored in local SQLite (0600 mode) with zero fee markups  |  |
|  |  * Zero export watermarks, zero resolution artificial caps, zero duration limits   |  |
|  +-----------------------------------------------------------------------------------+  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  |                     OPTIONAL PAID VALUE-ADD OFFERINGS                             |  |
|  |                                                                                   |  |
|  |  +--------------------------------+   +----------------------------------------+  |  |
|  |  |        4. LAQTA CLOUD          |   |           5. LAQTA BUSINESS            |  |  |
|  |  |  (Turnkey Hosted Compute)      |   |        (Professional Services)         |  |  |
|  |  |                                |   |                                        |  |  |
|  |  * Hosted high-speed GPU ASR      |   |  * Turnkey deployment & setup          |  |  |
|  |  * Cloud batch rendering clusters |   |  * Custom CMS/MAM pipeline adapters    |  |  |
|  |  * Metered compute seconds        |   |  * Enterprise support SLAs & warranty  |  |  |
|  |  * Multi-editor team workspaces   |   |  * Heuristic scoring calibration       |  |  |
|  |  * 100% opt-in; local never gated |   |  * Workflow consulting & team training |  |  |
|  +-----------------------------------+   +----------------------------------------+  |  |
|                                                                                      |  |
|  +--------------------------------------------------------------------------------+  |  |
|  |                       6. VOLUNTARY COMMUNITY FUNDING                           |  |  |
|  |  * GitHub Sponsors for recurring developer contributions                       |  |  |
|  |  * Direct project donations via verified public USDT / crypto address          |  |  |
|  |  * Open-source grants & cultural media technology sponsorships                 |  |  |
|  +--------------------------------------------------------------------------------+  |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Product Boundaries & Maintainer Commitments

### 3.1 Pillar 1: Free Laqta Web

- **Nature:** The browser-based workbench included in the repository (`frontend/src/` and `backend/app/`).
- **Access:** 100% free and open source under the **MIT License**.
- **Delivery:** Self-hosted by the user or run locally via one-command launch (`./scripts/dev.sh` or `laqta studio --production`).
- **Guarantee:** No feature restrictions, paywalls, or forced cloud registrations.

### 3.2 Pillar 2: Free Laqta Desktop (Planned Post-`v0.2.5`)

- **Nature:** An official packaged native application designed for creators who prefer standalone desktop installers over terminal commands.
- **Architecture Plan:** Reuses the existing React 19 / Vite frontend inside a lightweight **Tauri 2** (Rust) desktop shell, orchestrating the local Python backend as a background sidecar process.
- **Distribution Policy:** Official binaries distributed free of charge for Linux (`.deb`, `.rpm`, `.AppImage`, Flatpak), macOS (`.dmg`), and Windows (`.msi`).
- **Free Updates:** Automated in-app update checks and bug fixes provided at no charge.
- **Maintainer Guarantee:** Zero local-processing paywalls, zero export watermarks, zero resolution limits, and zero duration caps in official desktop releases.

### 3.3 Pillar 3: Free Local-First Processing

- **Guaranteed Capabilities:**
  - Audio extraction and media probing via FFmpeg/FFprobe.
  - Local CPU/GPU speech recognition via `faster-whisper` and CTranslate2.
  - Candidate span generation and deterministic Clip Potential Score (CPS) ranking.
  - Bilingual Arabic/English ASS and SRT subtitle styling with Unicode BiDi isolation.
  - 1080×1920 vertical video rendering with burned-in subtitles.
  - Bring Your Own Keys (BYOK) credential storage in local SQLite database with `0600` filesystem isolation.
- **No Paywalls Ever:** Local processing will never be artificially gated by subscriptions, export watermarks, or artificial quality limits.

### 3.4 Pillar 4: Optional Paid Laqta Cloud (Prospective Offering)

- **Nature:** An optional, future turnkey hosted infrastructure service for creators requiring accelerated performance or collaboration.
- **Capabilities:**
  - Cloud-accelerated GPU transcription for rapid processing of multi-hour videos.
  - Cloud batch rendering clusters, offloading intensive video rendering from user laptops.
  - Metered compute billing with transparent per-job cost previews.
  - Team collaboration workspaces enabling multi-seat clip review and approval.
- **Privacy Protections:** Strict fail-closed privacy. Data leaves the user's machine only upon explicit per-job consent. Automated deletion of source media after job completion or a user-defined retention period.
- **Non-Gating Rule:** Users who never subscribe to Laqta Cloud retain full, unrestricted access to all local processing capabilities.

### 3.5 Pillar 5: Paid Business Support & Integrations

- **Nature:** Direct commercial enterprise services for broadcast networks, media production companies, and content marketing agencies.
- **Offerings:**
  - Dedicated deployment assistance (private cloud, on-premises Kubernetes, air-gapped environments).
  - Custom pipeline integration with enterprise Media Asset Management (MAM) systems and Content Management Systems (CMS).
  - Production support SLAs, guaranteed bug-fix turnarounds, and custom feature development.
  - Custom heuristic calibration (fine-tuning scoring models to client-specific broadcast styles).
  - Hands-on team training and workflow consulting.

### 3.6 Pillar 6: Voluntary Community Funding

- **GitHub Sponsors:** Transparent recurring developer funding for community contributors.
- **Cryptocurrency Support (USDT / Stablecoins):** Verified public receiving address for international supporters facing traditional payment restrictions. Zero private keys, seed phrases, or custodial wallet code permitted in repository.
- **Grants & Fellowships:** Applying for non-profit open-source grants supporting open media technology.

---

## 4. Hosted Cloud & Software Distribution Under the MIT License (And Third-Party Dependencies)

> [!NOTE]
> **Historical Proposal Superseded:** Earlier drafts of this section analyzed browser-delivered Executable Form obligations under MPL-2.0. Because Laqta permanently retains the **MIT License** (proposed MPL-2.0 transition rejected), first-party Laqta server and client source code are governed by MIT.

### 4.1 First-Party Laqta Software (MIT License)

Under the **MIT License**:

- Hosted SaaS deployments, self-hosted server instances, browser-delivered frontend bundles (`frontend/dist/`), and desktop binaries of first-party Laqta code require preserving the **MIT copyright and permission notice** (`Copyright (c) 2026 Mohamed Aboelela`).
- First-party MIT code carries no copyleft source-sharing trigger; proprietary backend extensions or SaaS orchestrations may coexist freely, subject to [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) and separate non-code brand asset terms.

### 4.2 Third-Party Runtime & Binary Obligations

When distributing container images (`Dockerfile`), binary bundles, or installers (separate from source-only releases), third-party dependencies retain their own upstream licenses and distribution obligations — notably `MPL-2.0` (`certifi`, `tqdm`), `PSF-2.0`, and LGPL/GPL FFmpeg shared libraries (see [`docs/LICENSING_DECISIONS.md`](file:///home/thewizard/Qatta/docs/LICENSING_DECISIONS.md) §3).

---

## 5. Summary Matrix: Product Tiers & Legal Obligations

| Dimension              | Laqta Web            | Laqta Desktop                    | Laqta Cloud                        | Laqta Business                |
| ---------------------- | -------------------- | -------------------------------- | ---------------------------------- | ----------------------------- |
| **Audience**           | Self-Hosters, Devs   | Creators, Editors                | High-Volume Teams                  | Enterprise Broadcasters       |
| **Pricing**            | Free (Open Source)   | Free Official Binaries           | Metered / Subscription             | Contract / Retainer           |
| **Product Guarantee**  | Zero Paywalls        | Zero Local Paywalls / Watermarks | Compute Gated Only                 | Custom SLA Scope              |
| **License**            | MIT                  | MIT (Code) / Free Binary         | Commercial SaaS Terms              | Enterprise Services Agreement |
| **Compute Location**   | Local Machine        | Local Machine                    | Cloud GPU Clusters                 | On-Prem / Client Cloud        |
| **Account Required**   | No                   | No                               | Yes (for billing)                  | Corporate Contract            |
| **Offline Support**    | 100% Offline         | 100% Offline                     | Requires Internet                  | Customer Environment          |
| **Distribution Scope** | Source Distribution  | Executable Distribution          | Server & Browser Delivery          | Executable Distribution       |
| **Notice Obligations** | Standard MIT Notice  | MIT + 3P Binary/Deps Notices     | MIT Notice + Brand/Trademark Rules | MIT + Custom Agreement        |
| **Current Status**     | `v0.2.0` -> `v0.2.5` | Planned Post-`v0.2.5`            | Prospective Phase                  | On Inquiry                    |
