# Laqta — Licensing Guide & Continuity Framework

**Document Status:** Active Licensing Policy (MIT Continuity)  
**Applicability:** Laqta Core, Services, Workbench, and Ecosystem  
**Governing Project License:** **MIT License** (Permanently Retained across `v0.1.0`–`v0.2.5+`)  
**Historical Note:** Previously proposed `MPL-2.0` transition for `v0.2.5` was **rejected by the maintainer**

---

## 1. Overview & Purpose

This document defines the licensing framework for the **Laqta** (لقطة) open-source project. It establishes Laqta's permanent **MIT License** across all historical and active releases (`v0.1.0` through `v0.2.5+`), records the maintainer's rejection of the previously proposed MPL-2.0 transition, separates first-party software licensing from third-party dependencies, and separates software copyright from trademark rules and visual asset rights.

---

## 2. Permanent MIT License Continuity

Laqta remains permanently licensed under the standard **MIT License**:

```
+-----------------------------------------------------------------------------------------+
|                                    LAQTA RELEASES                                       |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  ALL RELEASES (v0.1.0 - v0.2.0 - v0.2.5+)                                               |
|  * Governed continuously by the official MIT License (Copyright (c) 2026 Mohamed Aboelela)|
|  * First-party source manifests (LICENSE, pyproject.toml, package.json) declare MIT     |
|  * Proposed v0.2.5 MPL-2.0 relicensing was explicitly REJECTED by the maintainer         |
|  * Third-party dependencies retain their own separate upstream licenses and notices     |
|                                                                                         |
+-----------------------------------------------------------------------------------------+
```

### 2.1 Immutable Baseline & Continuity (`v0.1.0` through `v0.2.5+`)

- **Status:** Permanent and unchanged.
- **Governing Terms:** Official [MIT License](file:///home/thewizard/Qatta/LICENSE).
- **Non-Revocation Guarantee:** Every Laqta release from `v0.1.0` through `v0.2.0` and `v0.2.5+` grants recipients full, perpetual permissive rights under the MIT License to use, copy, modify, merge, publish, distribute, sublicense, and sell copies of first-party Laqta software, subject to preserving the copyright and MIT permission notice.
- **Rejected MPL-2.0 Proposal (Superseded):** Earlier audit drafts (`docs/LICENSING_TRANSITION_AUDIT.md`) evaluated a prospective MPL-2.0 transition at `v0.2.5`. That proposal was **rejected** by the maintainer; no MPL-2.0 relicensing or Exhibit A headers are implemented for Laqta first-party code.

---

## 3. Repository License Identification & Metadata

Under the **MIT License**, Laqta applies notice consistently at the repository and package-manifest level:

1. **Root License Text:** Official MIT text in [`LICENSE`](file:///home/thewizard/Qatta/LICENSE) (`Copyright (c) 2026 Mohamed Aboelela`).
2. **Package Manifests:**
   - Root Python package [`pyproject.toml`](file:///home/thewizard/Qatta/pyproject.toml): `license = "MIT"`, `license-files = ["LICENSE"]`.
   - Backend Python package [`backend/pyproject.toml`](file:///home/thewizard/Qatta/backend/pyproject.toml): `license = "MIT"`, `license-files = ["LICENSE"]`.
   - Frontend workbench [`frontend/package.json`](file:///home/thewizard/Qatta/frontend/package.json): `"license": "MIT"`.
3. **Contributor Terms (`CONTRIBUTING.md` §9):** Contributions to Laqta are licensed under the [MIT License](file:///home/thewizard/Qatta/LICENSE).
4. **Historical Note on Superseded MPL-2.0 Strategy:** Earlier planning sections describing `SPDX-License-Identifier: MPL-2.0`, Exhibit A notices, and Exhibit B evaluations apply solely to the **rejected** MPL-2.0 proposal preserved for audit traceability in [`docs/LICENSING_TRANSITION_AUDIT.md`](file:///home/thewizard/Qatta/docs/LICENSING_TRANSITION_AUDIT.md).

---

## 4. Comprehensive Repository Inventory: MIT Software vs. Excluded Assets

### 4.1 First-Party MIT Software Directories

| Directory / File Path             | Description & Contents                                                                                                                      | Governing License |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| `qatta/`                          | Manifest-based video processing engine, pipeline schema (`schema.py`), configuration (`config.py`), CLI (`cli.py`), and stages `s01`–`s07`. | MIT               |
| `backend/app/`                    | FastAPI backend application, database models, schemas, background job worker, and API routes.                                               | MIT               |
| `backend/tests/`                  | Automated test suites, API test fixtures, and mock service harnesses for the backend.                                                       | MIT               |
| `frontend/src/`                   | React 19 / Vite workbench UI components, feature modules (transcription, clips, settings), timeline, and canvas.                            | MIT               |
| `frontend/` (configs)             | Studio configuration files (`vite.config.ts`, `tsconfig.json`, `eslint.config.js`).                                                         | MIT               |
| `tests/`                          | Core pipeline integration tests, scoring benchmarks, and property verification suites.                                                      | MIT               |
| `scripts/`                        | Clean-room verification harnesses (`verify_release.py`), doctor tools, and evaluation benchmarks.                                           | MIT               |
| `packaging/` _(scripts/desktop)_  | Linux desktop integration scripts (`install.sh`) and desktop entry specification (`laqta.desktop`); brand icons handled separately below.   | MIT               |
| `benchmarks/` (scripts & schemas) | Benchmark evaluation scripts (`evaluate_ranking.py`) and dataset schemas.                                                                   | MIT               |

### 4.2 Excluded Materials, Third-Party Dependencies & Separately Governed Assets

| Component / Path                                  | Description                                                                                                                                                                               | Governing Terms / Licensing Status                                                                                                                                                                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `THIRD_PARTY_NOTICES.md` & Lockfiles              | Upstream runtime and build dependencies (FastAPI, faster-whisper, PyAV, certifi, tqdm, React, Lucide, Tailwind, lightningcss, etc.).                                                      | Governed exclusively by their respective upstream licenses (`MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Unlicense`, plus audited `MPL-2.0`, `PSF-2.0`, etc.). Third-party licenses apply only to their own packages, not Laqta code.                         |
| `tests/fixtures/sample_captions_synthetic.ar.vtt` | Original synthetic Arabic technical WebVTT caption track (14 cues) replacing the removed broadcast fixture in the working tree (historical tags `v0.1.0`–`v0.2.0` retain the prior file). | First-party test data fixture under `tests/` (MIT).                                                                                                                                                                                                                           |
| `CODE_OF_CONDUCT.md`                              | Contributor Covenant version 2.1 community guidelines.                                                                                                                                    | Creative Commons Attribution 4.0 International (CC BY 4.0).                                                                                                                                                                                                                   |
| `Laqta_Brand_Kit/`, `packaging/icons/`            | Master vector and raster logos, app icons, wordmarks, promotional banners, and bundled app icons.                                                                                         | Separate asset copyright governance proposed in [`docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md); trademark/brand usage governed by [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md). |

---

## 5. Rights & Obligations Under the MIT License & Dependency Separation

### 5.1 Permitted Uses (First-Party MIT Code)

- **Universal Commercial & Personal Use:** You may use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of first-party Laqta software for personal, educational, commercial, or governmental purposes without fee or royalty.
- **Notice Preservation Condition:** The MIT copyright notice (`Copyright (c) 2026 Mohamed Aboelela`) and permission notice must be included in all copies or substantial portions of the Software.

### 5.2 Third-Party Dependency Separation

- Distributing, packaging, or shipping binaries or containers that include third-party packages (`certifi` / `tqdm` under `MPL-2.0`, `typing-extensions` under `PSF-2.0`, or FFmpeg / PyAV wheels with LGPL/GPL shared libraries) triggers the respective **upstream third-party notices and source obligations** for those third-party components, without altering the MIT license of Laqta's first-party code. See [`docs/DEPENDENCY_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/DEPENDENCY_POLICY_PROPOSAL.md) and [`docs/LICENSING_DECISIONS.md`](file:///home/thewizard/Qatta/docs/LICENSING_DECISIONS.md) §3.

---

## 6. Trademarks & Brand Protection

The **MIT License** governs copyright rights in the source code; **it does not grant trademark rights**.

Use of the project name "Laqta", the Arabic mark "لقطة", and the official logos and graphics is governed by [docs/TRADEMARKS.md](file:///home/thewizard/Qatta/docs/TRADEMARKS.md). Downstream distributors and fork maintainers must respect brand boundaries to prevent consumer confusion.

---

## 7. Inquiries & Community Contact

For questions regarding Laqta licensing or commercial integrations:

- **Repository Issues:** [https://github.com/thewizard2030/laqta/issues](https://github.com/thewizard2030/laqta/issues)
- **Security & Private Contact:** See [SECURITY.md](file:///home/thewizard/Qatta/SECURITY.md)
