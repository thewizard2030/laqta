# Laqta — Licensing Transition & Open-Source Business Architecture Audit (Historical / Superseded Proposal)

> [!IMPORTANT]
> **Superseded / Rejected by Maintainer Decision:** The prospective `v0.2.5` transition to **MPL-2.0** analyzed in this document was **explicitly rejected by the maintainer**. **Laqta remains permanently licensed under the [MIT License](file:///home/thewizard/Qatta/LICENSE)** across `v0.2.0`, `v0.2.5`, and future releases. This audit record is retained intact strictly for historical traceability; see [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) and [`docs/LICENSING_DECISIONS.md`](file:///home/thewizard/Qatta/docs/LICENSING_DECISIONS.md) for the governing MIT continuity policy.

**Document Status:** Historical / Superseded Audit Record (Proposed MPL-2.0 Transition Rejected)  
**Evaluated Target Release (Rejected):** `v0.2.5` (Retained on **MIT License**)  
**Current Baseline Release:** `v0.2.0` (Published under MIT License)  
**Superseded Proposal License:** Mozilla Public License 2.0 (MPL-2.0) — **Not Adopted**  
**Audit Date:** 2026-11-14 (Maintainer Decision Recorded: 2026-11-15)  
**Audit Scope:** Historical Authorship Evidence, Provenance Findings, and Rejected Transition Analysis

---

## Executive Summary

This audit evaluates the prospective transition of the **Laqta** (لقطة) open-source repository from the **MIT License** to the **Mozilla Public License 2.0 (MPL-2.0)**, targeted for a future release at **`v0.2.5`**.

The project's chosen business and distribution model comprises six distinct pillars:

1. **Free Laqta Web:** The browser-based workbench included in the repository, freely accessible and self-hostable.
2. **Free Laqta Desktop:** Official packaged desktop application (planned for post-`v0.2.5`), providing free native installation and updates.
3. **Free Local-First Processing:** 100% free offline execution on the user's hardware with zero feature paywalls or export limits.
4. **Optional Paid Laqta Cloud:** Optional turnkey hosted compute (GPU ASR, cluster batch rendering, multi-editor team workspaces).
5. **Paid Business Support & Integrations:** Enterprise deployments, custom MAM/CMS adapters, training, and support SLAs.
6. **Voluntary Community Funding:** GitHub Sponsors, verified non-custodial crypto donations, and ecosystem grants.

### Summary of Audit Findings: Facts vs. Legal Conclusions

- **Verified Fact (Authorship):** Forensic audit of all **28 git commits** on `main` confirms that **100% of the code on `main` was authored and committed by Mohamed Aboelela** (`thewizard2019@gmail.com` and `81768997+thewizard2030@users.noreply.github.com`).
- **Verified Fact (External Commits):** Zero third-party commits exist on `main`. Six Dependabot PR branches exist on remote forks but were never merged into `main`.
- **Verified Fact (Historical Releases):** Releases `v0.1.0` through `v0.2.0` were published under MIT. Permissions granted under those releases are permanent and irrevocable.
- **Distinction Between Authorship and Ownership:** Git authorship is factual evidence of author identity, but does **not** constitute legal proof of unencumbered copyright title. The maintainer must verify the absence of employer invention-assignment or contractor claims.
- **MPL-2.0 Notice Strategy:** To comply with MPL-2.0 Sections 1.4, 3.1, and Exhibit A, the project will implement a hybrid notice strategy: SPDX headers where file formats support comments, root license metadata and explicit covered directory identification where comments are unsupported.
- **Distribution vs. Network Use:** Under MPL-2.0, running software as a server-side SaaS service does not constitute software distribution. However, distributing an on-premises package, desktop binary, or browser-delivered client executable containing Covered Software (whether modified or unmodified) **carries mandatory source availability (Section 3.1) and notice obligations (Section 3.2)** for the Covered Software and any applicable Modifications.

---

## 1. Current MIT Baseline

### 1.1 Repository State at v0.2.0

The repository currently operates under the MIT License at release `v0.2.0` (commit `5148e7f` / merge `b0ede9e`).

| File                     | Declared License        | Attribution / Header Details                 | Factual Verification                    |
| ------------------------ | ----------------------- | -------------------------------------------- | --------------------------------------- |
| `LICENSE`                | MIT License             | `Copyright (c) 2026 Mohamed Aboelela`        | Standard 1988 MIT text.                 |
| `pyproject.toml`         | `license = "MIT"`       | `authors = [{ name = "thewizard2030" }]`     | Declares `license-files = ["LICENSE"]`. |
| `backend/pyproject.toml` | `license = "MIT"`       | `authors = [{ name = "thewizard2030" }]`     | Backend service packaging manifest.     |
| `frontend/package.json`  | `"license": "MIT"`      | Repository: `github.com/thewizard2030/laqta` | Frontend package manifest.              |
| `CONTRIBUTING.md`        | MIT License (§9)        | Submissions licensed under MIT               | Inbound submission policy.              |
| `README.md`              | MIT License             | Badge, comparison table, and §License        | Links directly to `LICENSE`.            |
| `README.ar.md`           | ترخيص MIT               | Badge and Arabic §License                    | Arabic translation of license terms.    |
| `THIRD_PARTY_NOTICES.md` | Multi-license inventory | Full inventory of runtime dependencies       | MIT, Apache-2.0, BSD, ISC, Unlicense.   |
| `docs/POLICY.md`         | Dependency Policy (§5)  | Whitelist: MIT/Apache/BSD/ISC/Unlicense      | AGPL-3.0 strictly forbidden.            |

### 1.2 First-Party vs. Third-Party Scope

- **First-Party Code:** All files in `qatta/` (manifest pipeline engine), `backend/app/` (FastAPI services), `frontend/src/` (React/Vite studio), `scripts/` (build and verification harnesses), and `packaging/` (Linux packaging). All currently licensed under MIT.
- **Third-Party Dependencies:** Direct dependencies are documented in `THIRD_PARTY_NOTICES.md`. No third-party code is vendored into application source trees.
- **External Binaries:** FFmpeg / FFprobe (LGPL 2.1+ / GPL 2.0+) and libass (ISC) are executed strictly via external process execution (`subprocess.Popen` with `shell=False`) and are never linked into application binaries.

---

## 2. v0.2.0 Historical Rights Statement

### 2.1 Irrevocability of Historical MIT Releases

The MIT License grants licensees an unrestricted, perpetual, royalty-free, and irrevocable right to deal in copies of the Software obtained under that license:

> _"Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the 'Software'), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software..."_

Under established international copyright jurisprudence, an open-source license grant with no reservation of revocation rights cannot be unilaterally cancelled for versions already distributed.

- **`v0.1.0`** (tagged 2026-10-20, commit `1726837`)
- **`v0.1.1`** (tagged 2026-10-21, commit `e5faca2`)
- **`v0.1.2`** (tagged 2026-10-21, commit `308cd0c`)
- **`v0.1.3`** (tagged 2026-10-22, commit `6b6b7b0`)
- **`v0.2.0`** (tagged 2026-11-14, commit `5148e7f`)

All individuals and entities who received copies of Laqta under releases `v0.1.0` through `v0.2.0` maintain full, irrevocable rights under the MIT License to use, modify, sublicense, and distribute those versions.

### 2.2 Non-Retroactivity Guarantee

1. **Prospective Application:** The prospective transition to MPL-2.0 applies strictly from the designated transition commit and release tag (`v0.2.5` onward).
2. **No History Rewrites:** Historical Git tags and release archives will permanently point to their respective MIT commits and will never be rewritten.
3. **Downstream Freedom:** Downstream users retain the legal right to continue maintaining or forking historical versions (`v0.2.0` or earlier) under MIT.

---

## 3. Contributor & Authorship Inventory

An exhaustive inspection of the Git object database was conducted across all refs, branches, and tags (`git log --all`, `git shortlog -sne --all`, `git rev-list --count HEAD`).

### 3.1 Authorship Distribution on `main`

There are exactly **28 commits** on the `main` branch:

```
    24  Mohamed Aboelela <thewizard2019@gmail.com>
     4  Mohamed Aboelela <81768997+thewizard2030@users.noreply.github.com>
```

#### Detailed Commit Audit Table

| Commit Hash | Date       | Author Identity            | Committer   | Type / Scope | Subject Summary                                                            |
| ----------- | ---------- | -------------------------- | ----------- | ------------ | -------------------------------------------------------------------------- |
| `51980b8`   | 2026-10-20 | Mohamed Aboelela (noreply) | GitHub      | Initial      | Initial commit (added MIT LICENSE)                                         |
| `1726837`   | 2026-10-20 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: Laqta v0.1.0 — local-first long-video-to-Shorts studio               |
| `0e56203`   | 2026-10-20 | Mohamed Aboelela (gmail)   | M. Aboelela | CI Fix       | fix(ci): use a valid matrix key in the backend job                         |
| `414d9b6`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Bugfix       | fix: close the v0.1.1 correctness and CI gaps                              |
| `25b7764`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Toolchain    | chore: upgrade the frontend toolchain and clear every advisory             |
| `e5faca2`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: v0.1.1 — zero known vulnerabilities, reproducible CI                 |
| `3d4c07e`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Tests        | test: cover the new CLI paths and re-baseline coverage                     |
| `a1714bb`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Bugfix       | fix: the health endpoint must not lie about the job worker                 |
| `d78f08b`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: error boundary, machine-readable doctor, Windows setup               |
| `b09b8b2`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Tests        | test: prove the release works end to end, from clean clone                 |
| `fd5868f`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: run whole studio from one command (release mode)                     |
| `308cd0c`   | 2026-10-21 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: v0.1.2 — studio runs from one command, release proves itself         |
| `caf8d13`   | 2026-10-22 | Mohamed Aboelela (gmail)   | M. Aboelela | Tests        | test: cover the scoring gates and fix coverage measurement                 |
| `926b207`   | 2026-10-22 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: measure the ranking — the clip-selection benchmark                   |
| `6b6b7b0`   | 2026-10-22 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat: v0.1.3 — the ranking is measured, not asserted                       |
| `35a562e`   | 2026-10-29 | Mohamed Aboelela (gmail)   | M. Aboelela | Docs/Assets  | docs: presentation overhaul, Arabic README, Docker support                 |
| `56b91b8`   | 2026-11-11 | Mohamed Aboelela (gmail)   | M. Aboelela | Feature      | feat(settings): add Bring Your Own Keys (BYOK) studio                      |
| `570921c`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | CI/Release   | feat(ci): CircleCI 2.1 with Smarter Testing & prepare v0.2.0               |
| `728ff20`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | CI Fix       | fix(ci): separate backend and core test suites                             |
| `11a98d1`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | CI Fix       | fix(ci): use cd backend with python -m pytest                              |
| `62aa0ec`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | CI Fix       | fix(ci): preserve cimg pyenv PATH in python-executor                       |
| `b5710e8`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | CI Fix       | fix(ci): add missing test dependencies and harden unit tests               |
| `e592f74`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | Bugfix       | fix(transcription): isolate settings state between tests                   |
| `5148e7f`   | 2026-11-14 | Mohamed Aboelela (noreply) | GitHub      | Merge PR #16 | Merge pull request #16 from thewizard2030/circleci-project-setup (v0.2.0)  |
| `028be5f`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | Docs         | docs: upgrade Laqta GitHub repository showcase                             |
| `20219c6`   | 2026-11-14 | Mohamed Aboelela (noreply) | GitHub      | Merge PR #17 | Merge pull request #17 from thewizard2030/docs/repository-showcase-refresh |
| `a4391cc`   | 2026-11-14 | Mohamed Aboelela (gmail)   | M. Aboelela | Docs         | docs: quote edge labels with parentheses in Mermaid diagrams               |
| `b0ede9e`   | 2026-11-14 | Mohamed Aboelela (noreply) | GitHub      | Merge PR #18 | Merge pull request #18 from thewizard2030/fix/mermaid-architecture-syntax  |

### 3.2 Unmerged Remote Branches

Six commits exist on remote Dependabot branches (`origin/dependabot/...`):

- `e87e12a`, `b6d1f4c`, `b3ffe88`, `b017e2a`, `5388d69`, `939748b`.
  **Verified Finding:** None of these commits were ever merged into `main`. The `main` branch contains zero bot contributions and zero external pull requests.

---

## 4. Copyright & IP Provenance: Maintainer Verification Checklist

While Git authorship is 100% attributed to Mohamed Aboelela, **Git authorship alone does not legally prove unencumbered copyright title**. A developer may author code while bound by an employment invention-assignment agreement, a consulting IP transfer, or university patent policies.

### 4.1 Strict Provenance Verification Rules

1. **Personal Time and Hardware Alone Are Inconclusive:** Under the laws of many jurisdictions, employment contracts frequently contain broad IP assignment clauses claiming all inventions created during the term of employment or relating to the employer's business, regardless of whether created outside office hours or on personal devices.
2. **Third-Party Code Snippets Require Provenance Review:** Code copied from technical blogs, online tutorials, or Q&A platforms (such as Stack Overflow) cannot be presumed fair use, nor can snippets be dismissed with blanket assumptions of universal incompatibility. Instead, each potential snippet must undergo a structured provenance review:
   - **Original Source & Publication Date:** Identify the exact post, commit, or article URL and the date it was published.
   - **Applicable License Version:** Determine the governing license terms in effect at publication (e.g., CC BY-SA 2.5 for pre-April 2011 Stack Overflow posts, CC BY-SA 3.0 for April 2011–February 2018, or CC BY-SA 4.0 for post-February 2018 posts).
   - **Amount & Expressive Substance:** Evaluate whether the snippet represents protectable creative expression or standard boilerplate, trivial idioms, or de minimis algorithmic logic.
   - **Adaptation vs. Independent Implementation:** Document whether the code was directly copied, substantially adapted, or independently reimplemented from reference documentation.
   - **Attribution & Share-Alike Terms:** Determine whether the source license imposes copyleft/share-alike obligations or specific attribution requirements, and whether the project can comply with all applicable terms.
   - **Resolution Rule:** Any unresolved copied code remains a strict licensing blocker until affirmatively resolved through full compliance, explicit contributor permission, complete removal, or clean-room independent reimplementation.
3. **Unresolved Provenance is a Hard Blocker:** Any unresolved ownership question represents a blocker that prevents declaring the repository ready for an active license change.

### 4.2 Maintainer IP Provenance Checklist

The maintainer must independently review, verify, and document the following items prior to executing the `v0.2.5` transition:

- [ ] **1. Employment & Invention-Assignment Agreements:** Review all past and current employment agreements in effect during 2026 to confirm that no employer holds an IP assignment claim, shop right, or work-made-for-hire title over Laqta.
- [ ] **2. Contractor & Consulting Contracts:** Review all client contracts, consulting scopes, or freelance agreements to verify that no code or pipeline architecture was created as work-for-hire for a client.
- [ ] **3. Third-Party Code & Copied Implementations:** Inspect first-party source directories (`qatta/`, `backend/app/`, `frontend/src/`) to ensure no external code snippets, algorithms, or utility functions were copied without explicit permission and license compatibility.
- [ ] **4. Samples, Test Fixtures & Datasets:** The prior third-party broadcast fixture (`sample_captions.ar.vtt`) was replaced in the current working tree by `tests/fixtures/sample_captions_synthetic.ar.vtt`, but remains present in immutable historical tags `v0.1.0`–`v0.2.0` (pending maintainer/legal review); verify synthetic audio generation scripts and benchmark evaluation datasets.
- [ ] **5. Graphic Assets, Logos, Fonts & Icons:** Verify that vector assets in `Laqta_Brand_Kit/` were newly authored by the maintainer, and verify that embedded font stacks (Manrope, Inter, Noto Sans Arabic) comply with the SIL Open Font License (OFL).
- [ ] **6. Dependency Licensing & Transitive Trees:** Verify that all direct and transitive dependencies documented in `THIRD_PARTY_NOTICES.md` remain compliant with the dependency whitelist (MIT, Apache-2.0, BSD, ISC, Unlicense).
- [ ] **7. Third-Party Submissions:** Confirm that no external contributor code is committed to `main`, and that future contributions will be submitted under MPL-2.0 backed by DCO 1.1 sign-offs.

> [!WARNING]
> **Checklist Status:** This checklist is **PENDING MAINTAINER VERIFICATION**. It has not been completed or signed off. Completing this checklist is an absolute release-readiness prerequisite for tagging `v0.2.5`.

---

## 5. MIT-to-MPL Transition Analysis

### 5.1 Relicensing by Copyright Holder vs. Sublicensing

A common point of confusion in open-source licensing transitions is whether a transition relies on:

1. **The MIT "Sublicense" Grant:** A licensee sublicensing someone else's MIT code under another license (which requires preserving original MIT notices and can create complex dual-notice obligations).
2. **The Original Author's Direct Relicensing:** The copyright owner exercising their inherent rights under copyright law to license their own work under a different license.

#### Analysis for Laqta

Because Mohamed Aboelela is the exclusive author and creator of the first-party codebase on `main`:

- Relicensing at `v0.2.5` is **not** an exercise in sublicensing under MIT; it is a **direct license grant from the copyright owner**.
- The historical releases continue under MIT because that grant was irrevocable.
- The new release (`v0.2.5` onward) will be offered directly under MPL-2.0.

---

## 6. Proposed License Model: MPL-2.0 Obligations & Notice Strategy

### 6.1 Core Properties of Official, Unmodified MPL-2.0

The **Mozilla Public License, version 2.0** is an OSI-approved, FSF-recognized, modern weak-copyleft license designed specifically for modular software engineering.

```
+-------------------------------------------------------------------------+
|                              LARGER WORK                                |
|                                                                         |
|  +---------------------------+       +-------------------------------+  |
|  |     MPL-2.0 COVERED       |       |     INDEPENDENT / PROPRIETARY |  |
|  |       SOURCE FILE         |       |          SOURCE FILE          |  |
|  |                           |       |                               |  |
|  | * File-level copyleft     |       | * Independent license terms   |  |
|  | * Modifications must be   |       | * Commercial closed source    |  |
|  |   made available under    |       |   permitted                   |  |
|  |   MPL-2.0 if distributed  |       | * No copyleft contamination   |  |
|  +---------------------------+       +-------------------------------+  |
+-------------------------------------------------------------------------+
```

#### Key MPL-2.0 Provisions:

1. **File-Level Copyleft Scope (Sections 1.4 & 1.10):**
   - "Covered Software" means Source Code Form of initial code and Modifications.
   - A "Modification" is defined strictly as any addition to, deletion from, or alteration of the contents of a file containing Covered Software, or any new file created that contains any part of Covered Software.
   - **Crucial Distinction:** New files that do not contain any MPL-2.0 source code are NOT Modifications, even if they import or link against MPL-covered files.
2. **Availability of Source Code (Section 3.1):**
   - If Covered Software is distributed in Source Code Form, it must remain under MPL-2.0.
   - If distributed in Executable Form (Section 3.2), the distributor must make the Source Code of the Covered Software available under MPL-2.0 and provide clear instructions on how to obtain it.
3. **Larger Works (Section 3.3):**
   - An MPL-2.0 licensee may create a "Larger Work" by combining Covered Software with other files not governed by MPL-2.0.
   - The non-MPL files may be distributed under any license terms, including proprietary commercial licenses, provided the MPL obligations for the Covered Software files are met.
4. **Distribution of Executable Form (Section 3.2):**
   - Executable distributions may be licensed under a different license (e.g. an end-user license agreement), provided the executable license does not attempt to restrict the recipient's rights to the underlying MPL source code.
5. **Absence of Network / SaaS Copyleft:**
   - Unlike AGPL-3.0 (Section 13) or SSPL, MPL-2.0 triggers obligations strictly upon **distribution** ("distribute", "distributes", "distribution").
   - Running MPL-2.0 code on a server or cloud infrastructure to deliver a SaaS web service without distributing the software itself does **not** trigger source code availability obligations.
6. **No Trademark Grant (Section 2.3):**
   - MPL-2.0 explicitly excludes trademarks: _"This License does not grant any rights in the trademarks, service marks, or logos of any Contributor (except as may be necessary to comply with the notice requirements in Section 3.4)."_
7. **Patent Grant and Retaliation (Sections 5.1 & 5.2):**
   - Contributors grant a patent license covering their patent claims embodied in their contribution.
   - If a licensee initiates patent litigation against a contributor claiming that the Covered Software infringes patents, the patent licenses granted to that litigant terminate automatically.

### 6.2 Compliant MPL Notice Architecture

To avoid vague or non-compliant notice implementation, the project establishes a multi-tier notice architecture:

1. **Root License Text:** Official, unmodified text of MPL-2.0 placed in `LICENSE`.
2. **First-Party Code Files Supporting Comments (`.py`, `.ts`, `.tsx`, `.sh`, `.yml`):**
   Marked at the top of the file with standard SPDX and Exhibit A notices:
   ```python
   # SPDX-License-Identifier: MPL-2.0
   # This Source Code Form is subject to the terms of the Mozilla Public
   # License, v. 2.0. If a copy of the MPL was not distributed with this
   # file, You can obtain one at https://mozilla.org/MPL/2.0/.
   ```
3. **Configuration & Data Files Where Inline Comments Are Unsupported (`.json`, `.toml`):**
   JSON files (e.g., `package.json`, tsconfig files) do not permit standard comments. Coverage is established through:
   - Root manifest metadata (`package.json` `"license": "MPL-2.0"`, `pyproject.toml` `license = "MPL-2.0"`).
   - Authoritative directory designation in `docs/LICENSING.md`.
   - Proposed adoption of the **FSFE REUSE specification** (`REUSE.toml`) to associate SPDX licensing metadata with non-comment files.
4. **Comprehensive Covered Software Inventory:**
   - `qatta/` — Pipeline engine, schemas, CLI, and stages `s01`–`s07`.
   - `backend/app/` — FastAPI backend service, job worker, and API endpoints.
   - `backend/tests/` — Backend automated test suites and mock harnesses.
   - `frontend/src/` — React 19 / Vite workbench UI components and studio views.
   - `frontend/` (configs) — Tooling configuration files (`vite.config.ts`, `tsconfig.json`, `eslint.config.js`).
   - `tests/` — Core pipeline tests, integration suites, and ranking benchmarks.
   - `scripts/` — Build scripts, verification harnesses, and benchmarks.
   - `packaging/` — Desktop installer scripts and integration specifications.
   - `benchmarks/` — Evaluation harnesses and dataset schemas.
5. **No Exhibit B Designation (Secondary License Compatibility):** The project will **not** attach Exhibit B ("Incompatible With Secondary Licenses"). Under MPL-2.0:
   - **Section 1.5** defines when Covered Software is "Incompatible With Secondary Licenses" (e.g., if the initial Contributor attaches the notice described in Exhibit B, or for certain historical MPL 1.1 code).
   - **Section 1.12** defines "Secondary License" as the GNU General Public License (GPL) Version 2.0, GNU Lesser General Public License (LGPL) Version 2.1, GNU Affero General Public License (AGPL) Version 3.0, and any later versions of those licenses.
   - **Section 3.3** governs Larger Works and the specific conditions for additional distribution under Secondary Licenses: if a Larger Work combines Covered Software with a work governed by one or more Secondary Licenses, and the Covered Software is not Incompatible With Secondary Licenses, the distributor may _additionally_ distribute the Covered Software under the terms of such Secondary License(s), so that the recipient of the Larger Work may, at their option, further distribute the Covered Software under the terms of either MPL-2.0 or such Secondary License(s). Omitting Exhibit B does not grant general unrestricted dual-licensing rights for standalone Covered Software; it ensures that when combined into a Larger Work with secondary-licensed code, the combination can be lawfully distributed.
   - **Section 3.4** governs the preservation of existing license notices, copyright notices, and patent notices in the Source Code Form (it does not govern secondary license compatibility).
   - **Exhibit B** provides an explicit notice attached by contributors who choose to forbid secondary licensing combinations.
   - **The project will NOT attach Exhibit B.** Omitting Exhibit B means the software is not made incompatible through that notice, preserving compatibility for Larger Works combinations under Section 3.3 as outlined in the official Mozilla MPL-2.0 FAQ (Q24–Q26), maximizing interoperability with downstream copyleft ecosystems and standard Linux distribution packaging (e.g., Fedora, Debian).

---

## 7. Proposed Release Transition Roadmap (Target: v0.2.5)

```
  v0.1.0        v0.1.3        v0.2.0           v0.2.1 - v0.2.4          v0.2.5+
----+-------------+-------------+---------------------+-------------------+---> Time
    |             |             |                     |                   |
    +==== MIT ====+= MIT =======+= MIT ===============+== Transition Prep =+= MPL-2.0 ==
    (Irrevocable) (Irrevocable) (Current Stable)      (Docs & Policies)   (Target Cut)
```

### 7.1 Staged Transition Milestones

| Stage / Milestone     | Target Version      | License Status | Scope & Actions                                                                                                                                                 |
| --------------------- | ------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Baseline**          | `v0.2.0` (Current)  | **MIT**        | Immutable historical release. BYOK and Advanced Settings Studio.                                                                                                |
| **Preparation Phase** | `v0.2.1` – `v0.2.4` | **MIT**        | Maintain documentation accuracy (`docs/LICENSING.md`, `docs/OPEN_SOURCE_BUSINESS_MODEL.md`, `docs/TRADEMARKS.md`). Maintain MIT in manifests.                   |
| **Verification Gate** | Pre-`v0.2.5`        | Review         | Maintainer completes IP Provenance Checklist; outside counsel review conducted.                                                                                 |
| **Transition Cut**    | **`v0.2.5`**        | **MPL-2.0**    | Update `LICENSE` to MPL-2.0. Add SPDX headers to source files. Update `pyproject.toml`, `backend/pyproject.toml`, and `package.json`. Update `CONTRIBUTING.md`. |
| **Post-Transition**   | `v0.3.0`+           | **MPL-2.0**    | First-party contributions strictly under MPL-2.0 with DCO. Introduction of Desktop host (Tauri 2) and optional Cloud connectors.                                |

---

## 8. Trademark Strategy Review

Software licenses govern copyright in code; **they do not grant trademark rights**. See [docs/TRADEMARKS.md](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) for full policy text.

### 8.1 Key Policy Principles

1. **Unregistered Brand Claim:** "Laqta", "لقطة", and the official logos are marks claimed by Mohamed Aboelela to identify the project. No registered trademark status (`®`) is asserted.
2. **Jurisdictional Realities:** Trademark protection mechanisms vary across legal systems. While common-law jurisdictions protect marks through use in commerce, civil-law jurisdictions (such as Egypt) recognize trademarks primarily through formal registration.
3. **No Overbroad Rebranding on Development Forks:** Developers forking the repository on GitHub/GitLab to study the code or submit pull requests do **not** need to rebrand or rename their repositories.
4. **Downstream OS Packagers:** Linux distribution packagers (e.g. Fedora, Debian) building from official source with standard packaging patches may use the name "Laqta" to identify the package.
5. **Substantially Modified Derivative Products in Commerce:** Third parties distributing modified software to the public or in commerce must choose a distinct primary brand name and replace official logos to prevent user confusion and false endorsement.
6. **Nominative Fair Use:** Truthful factual statements ("Based on Laqta", "Forked from Laqta v0.2.0", "Plugin for Laqta") are explicitly permitted.

---

## 9. Free Desktop Plan

- **Application Shell:** Evaluated for **Tauri 2** (lightweight Rust host wrapping the existing React 19 / Vite workbench).
- **Codebase Reuse:** Reuses the exact TypeScript/React components from `frontend/src/` without divergent forks.
- **Maintainer Product Commitments (Non-Negotiable):**
  1. Official desktop binaries distributed **free of charge**.
  2. Local media processing (ASR, ranking, subtitle generation, FFmpeg export) remains **100% free with zero feature paywalls, duration caps, or watermarks**.
  3. Free automatic security updates and engine fixes.
- **Phase Notice:** Desktop packaging is scheduled post-`v0.2.5` and is not part of release `v0.2.0`.

---

## 10. Optional Cloud Revenue Architecture

See [docs/OPEN_SOURCE_BUSINESS_MODEL.md](file:///home/thewizard/Qatta/docs/OPEN_SOURCE_BUSINESS_MODEL.md) for full specification.

### 10.1 Cloud Service Offerings

- Hosted GPU Whisper clusters for high-speed speech recognition.
- Cloud batch rendering clusters offloading intensive video rendering from user laptops.
- Metered compute seconds with transparent cost previews.
- Multi-seat team workspaces for collaborative clip review.

### 10.2 Privacy & Local Sovereignty

- Local processing is **never gated** behind cloud accounts.
- Data leaves the user's machine strictly upon explicit, per-job consent.
- Automated deletion of source media after job completion or a user-defined retention period.

### 10.3 Distribution Obligations vs. Network Use

- **SaaS (Server-Side Execution):** Running backend code on remote cloud servers so users can access its functionality over a network (e.g., REST API endpoints, GPU worker queues) does not constitute software distribution under MPL-2.0. Operating hosted backend services does not trigger source-code release obligations for backend code that remains on the server. However, network separation or server boundaries alone do not automatically exempt a file from MPL obligations if it incorporates or modifies Covered Software.
- **Browser-Delivered Client Assets (Distribution of Executable Form):** Under Mozilla's official interpretation (MPL 2.0 FAQ Q14–Q15), transmitting compiled, bundled, or minified JavaScript, CSS, and HTML assets to a user's web browser **constitutes distribution of Executable Form** under MPL-2.0 Section 3.2. This obligation applies to both **modified and unmodified** Covered Software. When distributing such Executable Form, Section 3.2 requires the corresponding Source Code Form to be made available as described in Section 3.1, covering the distributed Covered Software and its applicable Modifications (not only files newly modified by the distributor), along with instructions informing recipients how to obtain it.
- **Larger Works & Architectural Separation (Section 3.3):** Client-side distribution obligations do not require the entire cloud backend to become open source. Independently authored files that contain no Covered Software are not automatically subject to MPL file-level copyleft merely because they form part of a Larger Work under Section 3.3. However, separate microservices and network boundaries are **architectural considerations, not automatic legal exemptions**; any file that directly copies or modifies Covered Software remains Covered Software.
- **On-Premises & Desktop Software Delivery (Distribution):** Delivering software packages, container images, or desktop binaries directly to clients or customers is an unambiguous distribution of Executable Form, triggering full Section 3.1 and 3.2 source availability and recipient notice obligations for all distributed Covered Software and Modifications.

---

## 11. Business Services Architecture

- **Commercial Offerings:** Turnkey on-premises deployment, custom MAM/CMS pipeline integration, enterprise support SLAs, custom heuristic ranking calibration, and editor training.
- **Architectural Separation:** Proprietary enterprise integrations remain isolated in separate repositories or standalone packages under MPL-2.0 Section 3.3 (Larger Works), ensuring client IP is protected without compromising the open-source core.

---

## 12. Contributor Process Recommendations (DCO & Provenance)

### 12.1 Contributor License Grant Under MPL-2.0

Under MPL-2.0 Section 2.1, contributors automatically grant copyright and patent licenses when submitting code to Covered Software.

### 12.2 Role of Developer Certificate of Origin (DCO 1.1)

Starting in `v0.2.5`, contributions will include a DCO sign-off:

```text
Signed-off-by: Full Name <contributor@example.com>
```

#### Key DCO Distinctions:

- **DCO certifies legal authority and provenance:** It affirms that the contributor created the code or has the right to submit it under MPL-2.0.
- **DCO is NOT a copyright assignment:** Contributors retain their copyright ownership.
- **DCO is NOT a license substitute:** It certifies provenance; MPL-2.0 provides the actual license grant.
- **No CLA Required:** A broad copyright-assignment CLA is unnecessary because the project is not pursuing proprietary dual-licensing of the core.
- **Workflow Staging:** The DCO contribution workflow is documented in advance, but **automated PR enforcement will remain inactive until release `v0.2.5`**.

---

## 13. Repository File Change Map (Target: `v0.2.5`)

| Repository File                            | Current Status (`v0.2.0`) | Transition Classification          | Required Action at `v0.2.5`                                                      |
| ------------------------------------------ | ------------------------- | ---------------------------------- | -------------------------------------------------------------------------------- |
| `LICENSE`                                  | Full MIT text             | **Required for Transition**        | Replace with official, unmodified text of Mozilla Public License 2.0.            |
| `pyproject.toml`                           | `license = "MIT"`         | **Required for Transition**        | Update to `license = "MPL-2.0"` and update Trove classifiers.                    |
| `backend/pyproject.toml`                   | `license = "MIT"`         | **Required for Transition**        | Update to `license = "MPL-2.0"` and matching Trove classifier.                   |
| `frontend/package.json`                    | `"license": "MIT"`        | **Required for Transition**        | Update to `"license": "MPL-2.0"`.                                                |
| `CONTRIBUTING.md`                          | Section 9 declares MIT    | **Required for Transition**        | Update Section 9 to declare MPL-2.0; add DCO sign-off instructions.              |
| `README.md`                                | MIT badge & text          | **Required for Transition**        | Update badge to MPL-2.0, update comparison table and §License text.              |
| `README.ar.md`                             | MIT badge & text          | **Required for Transition**        | Update badge and Arabic text to reflect ترخيص موزيلا العمومي 2.0.                |
| `CHANGELOG.md`                             | Version history           | **Required for Transition**        | Document release `0.2.5` as the formal license transition milestone.             |
| `docs/LICENSING.md`                        | Proposed specification    | **Required for Transition**        | Publish as the authoritative dual-era licensing guide.                           |
| `TRADEMARKS.md`                            | Proposed policy           | **Required for Clarity**           | Publish standalone trademark policy governing project marks and fork rebranding. |
| `THIRD_PARTY_NOTICES.md`                   | Dependency inventory      | **Required for Clarity**           | Re-affirm strict dependency whitelist (MIT/Apache/BSD/ISC/Unlicense).            |
| `docs/POLICY.md`                           | Section 5 policy          | **Required for Clarity**           | Clarify first-party source is MPL-2.0 while dependency policy remains strict.    |
| `.github/PULL_REQUEST_TEMPLATE.md`         | Checklist                 | **Required for Clarity**           | Add checkbox: `[ ] Commit message includes DCO Sign-off (Signed-off-by: ...)`.   |
| Source Files (`.py`, `.ts`, `.tsx`, `.sh`) | No headers                | **Required for Notice Compliance** | Add SPDX `MPL-2.0` headers and Exhibit A notices.                                |
| Non-Comment Files (`.json`, `.toml`)       | Manifest metadata         | **Required for Notice Compliance** | Covered via manifest metadata, REUSE specification, and `docs/LICENSING.md`.     |
| Historical Tags (`v0.1.0` – `v0.2.0`)      | Tagged Git commits        | **Forbidden / Not Needed**         | **Do not touch.** Preserve historical commits and tags under MIT permanently.    |
| Core Application Code                      | Application logic         | **Forbidden / Not Needed**         | Zero functional changes to media pipeline, ASR, ranking, or rendering logic.     |

---

## 14. Legal Review: Recommended Risk-Control Questions

Outside counsel review is a **recommended risk-control measure**, not a formal statutory prerequisite of MPL-2.0 itself. Counsel familiar with the relevant jurisdictions should review the following questions:

1. **Employment IP Independence:** Does the maintainer's specific employment and consulting history during 2026 present any jurisdictional shop rights or IP assignment exposure under applicable national laws?
2. **Exhibit B Evaluation:** Does counsel concur that omitting Exhibit B ("Incompatible With Secondary Licenses") is optimal for maintaining Linux packager and open-source ecosystem compatibility?
3. **App Store Terms vs. MPL-2.0:** Does distribution of official packaged desktop builds via the Microsoft Store or macOS App Store satisfy MPL-2.0 Section 3.2 (executable distribution with source availability)?
4. **Trademark Protection in Civil-Law vs. Common-Law Systems:** Does counsel recommend formal trademark registration in Egypt and other target jurisdictions to establish robust statutory protection beyond unregistered common-law claims?
5. **On-Premises Distribution Terms:** Does counsel approve the Larger Works architecture for isolating proprietary enterprise customer adapters from MPL-covered files during commercial deployments?

---

## 15. Verification & Test Reporting

In accordance with strict verification reporting principles, exact command outcomes are recorded below:

| Verification Check                       | Target / Scope                           | Exact Outcome          | Details & Diagnostics                                                                                                                                                                                                                    |
| ---------------------------------------- | ---------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `git diff --check`                       | Working tree whitespace                  | **PASSED**             | Clean exit (code 0); zero trailing whitespace or whitespace errors.                                                                                                                                                                      |
| `python scripts/check_version.py`        | Repository version synchronization       | **PASSED**             | All 5 manifests (`qatta`, `backend`, root `pyproject.toml`, `backend/pyproject.toml`, `frontend/package.json`) agree on `0.2.0`.                                                                                                         |
| `backend/.venv/bin/ruff check`           | Python linter                            | **PASSED**             | Clean exit (code 0); all Python files passed.                                                                                                                                                                                            |
| `npm --prefix frontend run check`        | Frontend typecheck, lint, format, vitest | **PASSED**             | `tsc --noEmit` clean; `eslint .` clean (0 warnings); `prettier --check` clean; **18 test files passed (18/18), 116 tests passed (116/116)**.                                                                                             |
| `backend/.venv/bin/pytest backend/tests` | Backend test runner                      | **FAILED (Env Issue)** | Exit code 126 (`bad interpreter: No such file or directory`). The venv python symlink points to `/home/thewizard/.local/share/uv/python/...`, while system Python is 3.15.2 (lacks pytest). Application code untouched per instructions. |
| `prettier --check "docs/*.md"`           | Documentation formatting                 | **FAILED (Exit 1)**    | Prettier flagged code style issues across markdown files in `docs/` because `docs/` was authored outside Prettier's frontend scope (`frontend/src/`). Target docs formatted to resolve.                                                  |
| REUSE Specification Validation           | REUSE tooling check                      | **NOT INSTALLED**      | `which reuse` exited with code 1. REUSE tooling is not installed on the system; no tools were installed automatically.                                                                                                                   |
| CircleCI Remote Pipeline                 | Remote CI execution                      | **UNVERIFIED LOCALLY** | Remote CircleCI pipeline status is not asserted without verifiable live remote API query; local tests verified directly.                                                                                                                 |

---

## 16. Final Readiness Assessment (Superseded by Maintainer Decision)

### Historical Audit Outcome: **MPL-2.0 Transition Rejected — Permanently Retained on MIT**

All factual authorship and provenance findings recorded above (all `28` commits authored by Mohamed Aboelela, zero merged external PRs, immutable historical MIT tags `v0.1.0`–`v0.2.0`) remain preserved for provenance history. However, the prospective `MPL-2.0` transition described in Sections 5–13 of this document has been **explicitly rejected by the maintainer** and is **no longer applicable**. Laqta continues release **`v0.2.5`** permanently under the **MIT License** (see [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) and [`docs/LICENSING_DECISIONS.md`](file:///home/thewizard/Qatta/docs/LICENSING_DECISIONS.md)).
