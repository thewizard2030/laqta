# Laqta — Copyright Provenance & Licensing Policy Audit (Phase 3.1)

**Audit Target:** Repository Copyright Title, Third-Party Assets, Dependencies, Distribution Packaging & Verification Closure  
**Current Release Baseline:** `v0.2.0` (MIT License) -> `v0.2.5` (MIT License — Permanently Retained)  
**Historical Proposal Status:** Proposed MPL-2.0 Transition **REJECTED by Maintainer Decision (2026-11-15)**  
**Audit Date:** November 15, 2026  
**Auditor Mode:** Phase 3.1 Verification Closure & MIT Continuity Documentation Update

---

## 1. Executive Summary

This Phase 3.1 audit closes the inventory reconciliation, FFmpeg/container packaging verification, asset licensing matrix, and verification reporting for **Laqta**, preserving all Phase 3 working-tree fixture remediation edits while making **no** changes to root `LICENSE`, package license metadata, version numbers, Git tags, Git history, `backend/.venv`, or [`docs/POLICY.md`](file:///home/thewizard/Qatta/docs/POLICY.md).

### 1.1 Blocker Classification Taxonomy

Each audit finding below is classified using five distinct statuses:

- **Resolved:** Condition eliminated or verified compliant in the current working tree with direct tool/file evidence.
- **Pending Maintainer Decision:** Policy choice, license disposition, or written ownership/IP attestation required from the maintainer.
- **Pending Counsel Review:** Potential historical distribution or third-party rights exposure requiring legal/counsel review.
- **Technically Unverified:** Runtime test execution or transitive dependency resolution could not be completed in the current environment.
- **Future Distribution Gate:** Obligation triggered only if pre-built container images, PyAV binary wheels, or desktop installers are distributed in the future (not triggered by current source-only GitHub releases).

### 1.2 Key Findings Summary

1. **[Resolved in Current Tree / Historical Counsel Review Pending] Caption Fixture (`BLK-01-CURRENT` / `BLK-01-HIST`):** The unverified Arabic broadcast caption file `tests/fixtures/sample_captions.ar.vtt` has been deleted from the current working tree and replaced by [`tests/fixtures/sample_captions_synthetic.ar.vtt`](file:///home/thewizard/Qatta/tests/fixtures/sample_captions_synthetic.ar.vtt) with zero active references remaining. However, identical blob `00778717c2ac5a1604d01c317353fc8265feab57` remains in all five historical tags (`v0.1.0`–`v0.2.0`) and their `git archive` source tarballs (Section 5.2).
2. **[Verified Authorship Baseline / Attestation Pending] Git History & First-Party Code (`BLK-02`):** All **28 commits** on `main` were authored and committed by **Mohamed Aboelela**, with zero merged external pull requests and no third-party copied source code identified in examined `qatta/`, `backend/app/`, or `frontend/src/` code (except third-party mark SVG paths in `BrandIcons.tsx`). Employer/client IP independence requires written maintainer attestation (Section 7).
3. **[Pending Maintainer Decision / Unpinned Extras Unverified] Dependencies (`BLK-03`):** Both `backend/requirements-lock.txt` (`42` packages) and `frontend/package-lock.json` (`326` installed packages) contain packages outside the 5-license list in [`docs/POLICY.md`](file:///home/thewizard/Qatta/docs/POLICY.md) (`MPL-2.0`, `PSF-2.0`/`PSFL`, `CC-BY-4.0`, `BlueOak-1.0.0`, `MIT-0`, and `numpy` permissive subcomponents), while optional `[url]` and `[analysis]` Python extras remain unpinned. Zero AGPL-3.0 or GPL packages exist in either lockfile.
4. **[Future Distribution Gate] FFmpeg & Container Images (`BLK-03` / `Dockerfile`):** No official Docker images are built or published by CI/release workflows, and GitHub Releases distribute source-only `.tar.gz` archives. Distributing a built [`Dockerfile`](file:///home/thewizard/Qatta/Dockerfile) image or PyAV wheels (which bundle `libav*` plus GPL `libx264`/`libx265`) remains a **Future Distribution Gate** (Section 4).
5. **[Pending Maintainer Decision] Visual & Brand Assets (`BLK-04`):** [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) is not a copyright license. Explicit copyright dispositions are required across `Laqta_Brand_Kit/`, `packaging/icons/`, `frontend/public/`, `docs/assets/`, `BrandIcons.tsx`, and the AI-generated WebP concept board (`generated-brand-direction-reference.png`) (Section 6).
6. **[Technically Unverified] Python Test Execution (`BLK-05`):** Both `backend/.venv` (broken symlink to missing Python 3.12) and the host system (only Python `3.15.2` installed; `python3.11`/`python3.12` unavailable; no `pytest`/`numpy`) cannot execute `pytest`. Standalone Python stdlib VTT structural checks passed separately, but runtime `pytest` verification remains **Technically Unverified** (Section 9).

### 1.3 Baseline Status

> [!NOTE]
> **Maintainer Licensing Decision:** Laqta permanently retains the **MIT License** across `v0.2.0` and `v0.2.5+`; the previously evaluated MPL-2.0 transition was explicitly **rejected by the maintainer**. Preserved audit findings below remain valid for copyright provenance, fixture remediation (`BLK-01`), dependencies (`BLK-03`), and brand/asset rules (`BLK-04`).

---

## 2. First-Party Source Inventory

Inspection confirms **329 files** across the 8 primary functional source/test/script/packaging directories (excluding `__pycache__` and gitignored `data/`, `frontend/dist/`, `laqta.egg-info/`):

| Directory                                                      | File Count | Primary Function                                                                                 | Existing Headers | Identifiable 3P Elements                                       | Classification                                   |
| :------------------------------------------------------------- | :--------: | :----------------------------------------------------------------------------------------------- | :--------------- | :------------------------------------------------------------- | :----------------------------------------------- |
| [`qatta/`](file:///home/thewizard/Qatta/qatta)                 |     43     | Core video processing engine, pipeline schema, CLI, and stages `s01`–`s07`.                      | None             | None identified                                                | **Pending Maintainer Decision** (IP attestation) |
| [`backend/app/`](file:///home/thewizard/Qatta/backend/app)     |     92     | FastAPI backend service, routes, job worker, SQLite DB models, settings.                         | None             | None identified                                                | **Pending Maintainer Decision** (IP attestation) |
| [`backend/tests/`](file:///home/thewizard/Qatta/backend/tests) |     28     | Backend automated test suites, API endpoint tests, service mocks.                                | None             | None identified                                                | **Pending Maintainer Decision** (IP attestation) |
| [`frontend/src/`](file:///home/thewizard/Qatta/frontend/src)   |    120     | React 19 / Vite UI components, timeline, studio canvas, feature tabs, test suites.               | None             | Inline GitHub & YouTube SVG paths in `BrandIcons.tsx`          | **Pending Maintainer Decision** (`BrandIcons`)   |
| [`scripts/`](file:///home/thewizard/Qatta/scripts)             |     13     | Build, test, release verification, benchmark runners, environment setup.                         | None             | None identified                                                | **Pending Maintainer Decision** (IP attestation) |
| [`packaging/`](file:///home/thewizard/Qatta/packaging)         |     11     | Linux desktop entry (`laqta.desktop`), install script (`install.sh`), 9 app icons (`hicolor/`).  | None             | Icons copied from `Laqta_Brand_Kit/`                           | **Pending Maintainer Decision** (icon license)   |
| [`tests/`](file:///home/thewizard/Qatta/tests)                 |     19     | Core pipeline integration tests, scoring tests, synthetic caption fixture & README.              | None             | Synthetic replacement `sample_captions_synthetic.ar.vtt` added | **Resolved** (current working tree)              |
| [`benchmarks/`](file:///home/thewizard/Qatta/benchmarks)       |     3      | Regression thresholds (`baseline.json`), synthetic narration scripts (`clip_selection_v1.json`). | None             | None identified                                                | **Resolved** (verified first-party scripts/data) |

- **Font Binaries:** Zero `.ttf`, `.otf`, `.woff`, or `.woff2` font files are committed in the repository (`Manrope`, `Inter`, and `Noto Sans Arabic` are CSS/ASS/SVG font-family references).
- **No Inline Copyright Headers:** Zero first-party source files contain SPDX or copyright headers (matches on `"Copyright"` are UI strings parsing FFmpeg banners plus documentation).

---

## 3. Reconciled Python & Frontend Dependency Audit

[`docs/POLICY.md`](file:///home/thewizard/Qatta/docs/POLICY.md) (§5) currently restricts third-party dependencies to **MIT, Apache-2.0, BSD variants, ISC, and Unlicense**, and forbids **AGPL-3.0**. Deterministic parsing of actual manifests and lockfiles establishes that non-whitelisted licenses exist and policy decisions are required before `v0.2.5`.

### 3.1 Python Manifests, Optional Groups & Profiles

1. **Root [`pyproject.toml`](file:///home/thewizard/Qatta/pyproject.toml)** (`requires-python = ">=3.11"`): **18 unique direct third-party packages** across all groups:
   - `dependencies` (5): `pydantic>=2.7.0`, `pydantic-settings>=2.2.0`, `numpy>=1.26`, `typer>=0.12`, `rich>=13`.
   - `[asr]` (1): `faster-whisper>=1.1`.
   - `[analysis]` (4): `librosa>=0.10`, `soundfile>=0.12`, `scenedetect[opencv]>=0.6`, `mediapipe>=0.10`.
   - `[url]` (1): `yt-dlp>=2024.04`.
   - `[all]` (6): union of `[asr]` + `[analysis]` + `[url]`.
   - `[dev]` (6): `pytest>=8.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=5.0.0`, `pytest-xdist>=3.6.0`, `ruff>=0.5.0`, `pip-audit>=2.7.0`.
   - `[test]` (7): `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-xdist`, `faster-whisper`, `ctranslate2`, `yt-dlp`.
2. **Backend [`backend/pyproject.toml`](file:///home/thewizard/Qatta/backend/pyproject.toml)** (`requires-python = ">=3.11"`): **19 unique direct third-party packages** + `1` first-party `[pipeline]` (`laqta`):
   - `dependencies` (7): `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`, `pydantic>=2.7.0`, `pydantic-settings>=2.2.0`, `python-multipart>=0.0.9`, `httpx>=0.27`, `numpy>=1.26`.
   - `[asr]` (1), `[analysis]` (4), `[url]` (1): identical to root.
   - `[dev]` (7): `httpx>=0.27.0` (shared with core) + the 6 dev tools from root `[dev]`.
3. **Backend `requirements*.txt` Profiles:**
   - [`backend/requirements.txt`](file:///home/thewizard/Qatta/backend/requirements.txt): `7` direct API runtime specs.
   - [`backend/requirements-asr.txt`](file:///home/thewizard/Qatta/backend/requirements-asr.txt): `requirements.txt` + `faster-whisper>=1.1` (`8` cumulative direct specs).
   - [`backend/requirements-all.txt`](file:///home/thewizard/Qatta/backend/requirements-all.txt): `requirements-asr.txt` + `yt-dlp>=2024.04` + `4` `[analysis]` specs (`13` cumulative direct specs).
   - [`backend/requirements-dev.txt`](file:///home/thewizard/Qatta/backend/requirements-dev.txt): `requirements.txt` + `9` direct specs (`6` dev tools + `faster-whisper>=1.1`, `ctranslate2`, `yt-dlp>=2024.04` = `16` cumulative direct specs).

#### 3.1.1 Unpinned Profiles & `.venv` vs. Lockfile Drift

- **Local `backend/.venv` Is NOT the Release Lockfile:** `backend/.venv/lib/python3.12/site-packages/` has **79** `.dist-info` entries (**42** lockfile package equivalents + **37** extra packages), and **22** of the 42 shared packages differ in version from `backend/requirements-lock.txt`. All release-level claims must cite [`backend/requirements-lock.txt`](file:///home/thewizard/Qatta/backend/requirements-lock.txt), not `.venv`.
- **Lockfile `av==18.1.0` vs. `.venv` `av==19.0.2`:** Both the lockfile version (`18.1.0`) and `.venv` version (`19.0.2`) are `BSD-3-Clause` (`av-19.0.2.dist-info/METADATA` declares `License-Expression: BSD-3-Clause`, correcting [`THIRD_PARTY_NOTICES.md`](file:///home/thewizard/Qatta/THIRD_PARTY_NOTICES.md), which misstates `BSD 2-Clause`). PyAV wheels bundle LGPL/GPL FFmpeg shared libraries (see Section 4).
- **Unpinned `[url]` (`yt-dlp`) Profile:** `yt-dlp>=2024.04` is declared in root/backend `[url]`, `requirements-all.txt`, and `requirements-dev.txt`, but is **absent from `backend/requirements-lock.txt`**. `.venv` has `yt-dlp==2026.10.26` (`License-Expression: Unlicense`). Because `[url]` is unpinned, hash-pinned lockfile builds cannot verify optional URL installs unless pinned or omitted from shipped bundles.
- **Unpinned `[analysis]` Profile (`Technically Unverified`):** `librosa>=0.10`, `soundfile>=0.12`, `scenedetect[opencv]>=0.6`, and `mediapipe>=0.10` are **not pinned in `backend/requirements-lock.txt`** and **not installed in `backend/.venv`**. Their transitive trees (`scipy`, `numba`, `llvmlite`, `opencv-python`, `protobuf`/`flatbuffers`/`absl-py`/`matplotlib`, etc.) remain **Technically Unverified** and must be lock-resolved before shipping `[analysis]` or `[all]` profiles.

### 3.2 Python Lockfile Reconciliation (`backend/requirements-lock.txt`)

[`backend/requirements-lock.txt`](file:///home/thewizard/Qatta/backend/requirements-lock.txt) resolves `backend/requirements-asr.txt` for Python 3.11 with **42 pinned packages** (**8 direct** + **34 transitive** = **42** runtime API/ASR packages; `watchfiles` is pulled via `uvicorn[standard]`):

| License Category                      | Count  | Pinned Packages (`backend/requirements-lock.txt`)                                                                                                                                                                                                                                                                                                                                   | Policy Status                                                                       |
| :------------------------------------ | :----: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------- |
| **MIT**                               |   17   | `annotated-doc==0.0.5`, `annotated-types==0.8.0`, `anyio==4.15.1`, `ctranslate2==4.8.3`, `fastapi==0.150.0`, `faster-whisper==1.2.1`, `filelock==4.2.4`, `h11==0.16.0`, `httptools==0.9.0`, `onnxruntime==1.31.0`, `pydantic==2.14.1`, `pydantic-core==2.50.1`, `pydantic-settings==2.16.0`, `pyyaml==6.0.3`, `truststore==0.10.5`, `typing-inspection==0.4.4`, `watchfiles==1.3.0` | Whitelisted                                                                         |
| **MIT / Apache-2.0 (Dual)**           |   1    | `uvloop==0.23.0` (`License: MIT License`; ships `LICENSE-MIT` and `LICENSE-APACHE`)                                                                                                                                                                                                                                                                                                 | Whitelisted                                                                         |
| **BSD-3-Clause**                      |   13   | `av==18.1.0`, `click==8.5.0`, `fsspec==2026.9.0`, `httpcore==1.0.9`, `httpcore2==2.15.1`, `httpx==0.28.1`, `httpx2==2.15.1`, `idna==3.20`, `protobuf==7.36.2`, `python-dotenv==1.2.4`, `starlette==1.9.0`, `uvicorn==0.54.0`, `websockets==17.3`                                                                                                                                    | Whitelisted                                                                         |
| **Apache-2.0**                        |   6    | `flatbuffers==25.12.19`, `hf-xet==1.7.0`, `huggingface-hub==2.2.0`, `opentelemetry-api==1.45.1`, `python-multipart==0.0.32`, `tokenizers==0.23.3`                                                                                                                                                                                                                                   | Whitelisted                                                                         |
| **Apache-2.0 OR BSD-2-Clause**        |   1    | `packaging==26.3`                                                                                                                                                                                                                                                                                                                                                                   | Whitelisted                                                                         |
| **Composite Permissive (Permissive)** |   1    | `numpy==2.4.6` (`.venv` `2.5.4` `METADATA`: `License-Expression: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`; `licenses/` also includes `numpy/random/LICENSE.md` dual `NCSA OR BSD-3-Clause` and `highway/LICENSE` dual `Apache-2.0 OR BSD-3-Clause` + `CC0-1.0`)                                                                                                          | **Pending Maintainer Decision** (`0BSD`/`Zlib`/`CC0-1.0` not listed in `POLICY.md`) |
| **PSF-2.0**                           |   1    | `typing-extensions==4.16.0` (`.venv` `METADATA`: `License-Expression: PSF-2.0`; `licenses/LICENSE`: Python Software Foundation License v2)                                                                                                                                                                                                                                          | **Pending Maintainer Decision**                                                     |
| **MPL-2.0**                           |   1    | `certifi==2026.10.19` (`.venv` `2026.10.23` `METADATA`: `License: MPL-2.0`, OSI Mozilla Public License 2.0 classifier)                                                                                                                                                                                                                                                              | **Pending Maintainer Decision**                                                     |
| **MPL-2.0 AND MIT**                   |   1    | `tqdm==4.70.1` (`.venv` `METADATA`: `License: MPL-2.0 AND MIT`; `LICENCE` states main files `MPL-2.0`, `tqdm/_tqdm.py` `MIT`)                                                                                                                                                                                                                                                       | **Pending Maintainer Decision**                                                     |
| **TOTAL (Locked ASR Runtime)**        | **42** | **8 direct + 34 transitive = 42** (`17 + 1 + 13 + 6 + 1 + 1 + 1 + 1 + 1 = 42`)                                                                                                                                                                                                                                                                                                      | **38 whitelisted / 4 require policy decision**                                      |

### 3.3 Non-Lockfile Packages Present in `backend/.venv` (37 Extra Entries)

The `37` additional `.dist-info` directories in `backend/.venv` (`42 + 37 = 79`) are:

- **First-party (1):** `laqta==0.1.3` (MIT).
- **Optional URL runtime (1):** `yt-dlp==2026.10.26` (`Unlicense`).
- **CLI / HTTP / packaging helpers (11):** `typer==0.29.1` (MIT), `rich==15.0.0` (MIT), `markdown-it-py==4.3.0` (MIT), `mdurl==0.1.2` (MIT), `shellingham==1.5.4` (ISC), `pip==26.3` (MIT), `requests==2.34.2` (Apache-2.0), `urllib3==2.8.0` (MIT), `charset-normalizer==3.5.2` (MIT), `platformdirs==4.14.5` (MIT), `tomli==2.5.0` (MIT).
- **Dev / test / security-audit tools (24):** `pytest==9.2.0` (MIT), `pytest-asyncio==1.4.1.post1` (Apache-2.0), `pytest-cov==7.1.0` (MIT), `pytest-xdist==3.8.0` (MIT), `coverage==7.17.2` (Apache-2.0), `execnet==2.1.2` (MIT), `iniconfig==2.3.1` (MIT), `pluggy==1.7.0` (MIT), `Pygments==2.21.0` (BSD-2-Clause), `ruff==0.17.4` (MIT), `pip-audit==2.10.1` (Apache-2.0), `pip-api==0.0.35` (Apache-2.0), `pip-requirements-parser==32.0.1` (MIT), `CacheControl==0.14.4` (Apache-2.0), `msgpack==1.2.4` (Apache-2.0), `cyclonedx-python-lib==11.12.0` (Apache-2.0), `py-serializable==2.2.0` (Apache-2.0), `packageurl-python==0.17.6` (MIT), `license-expression==30.4.4` (Apache-2.0), `boolean.py==5.0` (BSD-2-Clause), `pyparsing==3.3.3` (MIT), `sortedcontainers==2.4.0` (Apache-2.0), `tomli_w==1.2.0` (MIT), and **`defusedxml==0.7.1`** (`License: PSFL` / `PSF-2.0` — dev/audit-only, outside `POLICY.md` §5).

### 3.4 Frontend Dependency Inventory & Bundle Reconciliation (`frontend/`)

[`frontend/package.json`](file:///home/thewizard/Qatta/frontend/package.json) declares **25 direct dependencies** (**3** `dependencies` + **22** `devDependencies`). [`frontend/package-lock.json`](file:///home/thewizard/Qatta/frontend/package-lock.json) contains **327 `"packages"` keys**: **1** root `""` + **326 installed entries** (**25 direct** + **301 transitive**).

**Mutually Exclusive Partition of All 326 Installed Frontend Lockfile Entries:**

1. **Runtime dependencies (`dev: false, optional: false`): 6 packages**
   - **Shipped in built JS bundle (`frontend/dist/assets/*.js`): 4 packages** — `react@19.3.1` (MIT), `react-dom@19.3.1` (MIT), `lucide-react@1.60.0` (ISC), `scheduler@0.28.0` (MIT).
   - **Type-only packages marked `dev: false` via `lucide-react` optional `peerDependency`: 2 packages** — `@types/react@19.3.0` (MIT), `csstype@3.2.3` (MIT); neither emits JS into `frontend/dist/`.
2. **Build / Lint / Format / Typecheck Dev (`dev: true, optional: false`, reachable via dependencies/peers from the 16 non-test `devDependencies`): 167 packages.**
3. **Test-Only Dev (`dev: true, optional: false`, reachable exclusively from `vitest`, `@vitest/coverage-v8`, `jsdom`, `@testing-library/*`): 103 packages.**
4. **Optional Platform Binaries (`optional: true`, all `dev: true`): 50 packages** (`15` `@rolldown/binding-*` MIT, `12` `@tailwindcss/oxide-*` MIT, `1` `fsevents` MIT, `22` `lightningcss-*` MPL-2.0).

- **Reconciliation Check:** `6 + 167 + 103 + 50 = 326`.
- **Actual Release Bundle Reconciliation:** Official GitHub source archives (`laqta-v*.tar.gz`) contain **0** npm packages (`node_modules` and `frontend/dist` are gitignored). Built `frontend/dist/` contains compiled code derived only from the **4** bundled JS runtime packages above (zero `dist/` inclusion of the `167` build, `103` test, or `50` optional platform packages); note that Vite's minified output omits upstream `MIT License` header comments unless third-party notices are shipped alongside `dist/`.

**License Distribution Across All 326 Frontend Entries:**

| Declared License |  Total  | Runtime (`dev: false`) | Build / Test (`dev: true, opt: false`) | Optional Platform (`opt: true`) |  Shipped in `frontend/dist/`?   | Policy Status                   |
| :--------------- | :-----: | :--------------------: | :------------------------------------: | :-----------------------------: | :-----------------------------: | :------------------------------ |
| `MIT`            |   256   |           5            |                  223                   |               28                | 3 (`react`, `dom`, `scheduler`) | Whitelisted                     |
| `Apache-2.0`     |   18    |           0            |                   18                   |                0                |               No                | Whitelisted                     |
| `ISC`            |   14    |           1            |                   13                   |                0                |       1 (`lucide-react`)        | Whitelisted                     |
| `BSD-2-Clause`   |    8    |           0            |                   8                    |                0                |               No                | Whitelisted                     |
| `BSD-3-Clause`   |    3    |           0            |                   3                    |                0                |               No                | Whitelisted                     |
| `MPL-2.0`        |   24    |           0            |                   2                    |               22                |               No                | **Pending Maintainer Decision** |
| `CC-BY-4.0`      |    1    |           0            |                   1                    |                0                |               No                | **Pending Maintainer Decision** |
| `BlueOak-1.0.0`  |    1    |           0            |                   1                    |                0                |               No                | **Pending Maintainer Decision** |
| `MIT-0`          |    1    |           0            |                   1                    |                0                |               No                | **Pending Maintainer Decision** |
| **TOTAL**        | **326** |         **6**          |                **270**                 |             **50**              | **4 bundled JS / 0 in src tar** | **299 whitelisted / 27 review** |

_(Confirmed: **0** `PSF-2.0` packages appear in `frontend/package-lock.json`; `PSF-2.0`/`PSFL` appears exclusively in Python `typing-extensions` and dev-only `defusedxml`.)_

### 3.5 Non-Whitelisted Dependency Review & Policy Recommendations

A dependency's license (such as `MPL-2.0` on `certifi`, `tqdm`, or `lightningcss`) governs that package's Covered Software and does **not** automatically relicense Laqta's independent source files (see MPL-2.0 §3.3 Larger Works). However, distributing binaries or images containing those packages carries notice and/or source-availability obligations for the included package:

| Package & Version                                                        | License Expression                                   | Runtime vs. Build/Dev                         | Included in Official Shipped Artifacts?                             | Policy Recommendation (No `POLICY.md` Edit Yet)                                                                  |
| :----------------------------------------------------------------------- | :--------------------------------------------------- | :-------------------------------------------- | :------------------------------------------------------------------ | :--------------------------------------------------------------------------------------------------------------- |
| `certifi==2026.10.19` (lock) / `2026.10.23` (venv)                       | `MPL-2.0`                                            | Python **runtime** transitive                 | No in source `.tar.gz`; **Yes** if Docker/Python env distributed    | Grant runtime exception (Mozilla root CA bundle) & track MPL-2.0 source availability if shipping images          |
| `tqdm==4.70.1`                                                           | `MPL-2.0 AND MIT` (`_tqdm.py` MIT; rest MPL-2.0)     | Python **runtime** transitive                 | No in source `.tar.gz`; **Yes** if Docker/Python env distributed    | Grant runtime exception for `faster-whisper`/`huggingface-hub` transitive & include MPL-2.0 notices              |
| `lightningcss@1.33.0` + 11 bins; nested `@1.32.0` + 11 bins (24 entries) | `MPL-2.0`                                            | Frontend **build-time only** (`dev: true`)    | **No** (`dist/` JS/CSS and source `.tar.gz` exclude `node_modules`) | Allow non-shipped `devDependencies` under permissive/weak-copyleft build-tool exception                          |
| `typing-extensions==4.16.0`                                              | `PSF-2.0`                                            | Python **runtime** transitive                 | No in source `.tar.gz`; **Yes** if Docker/Python env distributed    | Add `PSF-2.0` to approved permissive dependency whitelist                                                        |
| `defusedxml==0.7.1`                                                      | `PSFL` (`PSF-2.0`)                                   | Python **dev/audit only** (`pip-audit`)       | **No**                                                              | Covered by adding `PSF-2.0` (and dev-only separation)                                                            |
| `numpy==2.4.6` (lock) / `2.5.4` (venv)                                   | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | Python **runtime** direct                     | No in source `.tar.gz`; **Yes** if Docker/Python env distributed    | Add `0BSD`, `Zlib`, `CC0-1.0` (and `NCSA` subcomponent notice) to approved permissive sub-licenses               |
| `caniuse-lite@1.0.30001817`                                              | `CC-BY-4.0`                                          | Frontend **build-time only** (`dev: true`)    | **No** (not bundled into `frontend/dist/`)                          | Permit `CC-BY-4.0` for non-bundled build-time data packages; retain attribution if redistributing `node_modules` |
| `minimatch@10.2.6`                                                       | `BlueOak-1.0.0`                                      | Frontend **dev/lint/test only** (`dev: true`) | **No**                                                              | Add `BlueOak-1.0.0` to approved permissive/dev dependency exceptions                                             |
| `@csstools/color-helpers@5.1.0`                                          | `MIT-0`                                              | Frontend **build-time only** (`dev: true`)    | **No**                                                              | Add `MIT-0` to approved permissive dependency whitelist                                                          |

---

## 4. FFmpeg & Container Distribution Audit

Per official FFmpeg licensing documentation ([https://ffmpeg.org/legal.html](https://ffmpeg.org/legal.html)), FFmpeg builds are **LGPL v2.1+** by default, or **GPL v2.0+** / **GPL v3.0** when built with `--enable-gpl` / `--enable-version3` and GPL codecs (such as `libx264` or `libx265`).

Inspection of all workflows, [`Dockerfile`](file:///home/thewizard/Qatta/Dockerfile), [`docker-compose.yml`](file:///home/thewizard/Qatta/docker-compose.yml), [`packaging/`](file:///home/thewizard/Qatta/packaging), [`scripts/`](file:///home/thewizard/Qatta/scripts), and `backend/.venv/lib/python3.12/site-packages/av.libs/` establishes:

1. **Are Official Docker Images Published Today? — No.**
   - [`.github/workflows/`](file:///home/thewizard/Qatta/.github/workflows) (`release.yml`, `release-check.yml`, `ci.yml`, `evaluation.yml`, `audits.yml`, `scorecard.yml`) contains **zero** Docker build or push jobs (`ghcr.io`, Docker Hub, etc.).
   - [`docker-compose.yml`](file:///home/thewizard/Qatta/docker-compose.yml) defines only a local build (`build: { context: ., dockerfile: Dockerfile }`).
   - Official GitHub Releases ([`.github/workflows/release.yml`](file:///home/thewizard/Qatta/.github/workflows/release.yml)) publish **only** `dist/laqta-<tag>.tar.gz` generated via `git archive` (source code only; **0** FFmpeg binaries, **0** PyAV wheels, **0** desktop installers).
   - **Classification:** Container / PyAV FFmpeg binary redistribution is a **Future Distribution Gate**, **NOT** a current published-binary violation.
2. **What [`Dockerfile`](file:///home/thewizard/Qatta/Dockerfile) Installs If Built & Redistributed:**
   - Debian runtime packages (`apt-get install -y --no-install-recommends ffmpeg libass9 curl`) + `pip install --no-cache-dir -e ".[asr]"` (unpinned to `requirements-lock.txt`, pulling PyPI `faster-whisper` -> `av`).
   - Direct inspection of PyAV's wheel in `backend/.venv/lib/python3.12/site-packages/av.libs/` (`av==19.0.2`; lockfile pins `av==18.1.0`) shows **30 bundled `.so` binaries**, including FFmpeg core libraries (`libavcodec-d61378e8.so.63.1.102`, `libavdevice-c9c4901c.so.63.1.102`, `libavfilter-6a4661f8.so.12.1.102`, `libavformat-7f5186bf.so.63.1.102`, `libavutil-8f0ab4ee.so.61.1.102`, `libswresample-d0a74e06.so.7.1.102`, `libswscale-cd7831fd.so.10.1.102`) alongside **GPL codecs `libx264-d6533a8d.so.165` and `libx265-eebb7db1.so.217`** (plus `libgnutls`, `libgmp`, `libdav1d`, `libSvtAv1Enc`, `libvpx`, `libopus`, `libvmaf`).
   - **Rule Reminder:** Invoking `ffmpeg`/`ffprobe` via `subprocess` (`shell=False`) avoids linking Laqta's own Python code to `libavcodec`, **but it does NOT eliminate GPL/LGPL binary redistribution obligations** if a Docker image, PyAV wheel bundle, or desktop installer containing FFmpeg/`libx264`/`libx265` binaries is distributed to third parties.

| Distribution Channel                                                                                                                                                 | FFmpeg Source                                                  | Distributed by Laqta Today? | Status & Obligation                                                                                                 |
| :------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------- | :-------------------------: | :------------------------------------------------------------------------------------------------------------------ |
| Local host ([`README.md`](file:///home/thewizard/Qatta/README.md), [`scripts/setup.ps1`](file:///home/thewizard/Qatta/scripts/setup.ps1))                            | User OS install (`dnf` / `apt` / `winget install Gyan.FFmpeg`) |           **No**            | **Resolved** — User procures FFmpeg directly from OS/upstream vendor.                                               |
| Linux desktop ([`packaging/install.sh`](file:///home/thewizard/Qatta/packaging/install.sh), [`laqta.desktop`](file:///home/thewizard/Qatta/packaging/laqta.desktop)) | None bundled                                                   |           **No**            | **Resolved** for current repo (`Future Distribution Gate` if desktop binary installers are later introduced).       |
| GitHub Releases ([`.github/workflows/release.yml`](file:///home/thewizard/Qatta/.github/workflows/release.yml))                                                      | Source-only `git archive` `.tar.gz`                            |           **No**            | **Resolved** — Zero binaries shipped; CI `apt-get install ffmpeg` runs ephemerally only.                            |
| Docker ([`Dockerfile`](file:///home/thewizard/Qatta/Dockerfile), [`docker-compose.yml`](file:///home/thewizard/Qatta/docker-compose.yml))                            | Debian `ffmpeg` + PyAV `av.libs/` (`libx264`/`libx265` GPL)    |    **No** (local build)     | **Future Distribution Gate** — Must satisfy GPL/LGPL source offer, notices & pin versions before publishing images. |

---

## 5. Caption Fixture Remediation (`BLK-01-CURRENT`) & Historical Exposure (`BLK-01-HIST`)

### 5.1 Current Working Tree (`BLK-01-CURRENT` — **Resolved**)

- Removed `tests/fixtures/sample_captions.ar.vtt` (1,175 lines of Arabic broadcast political commentary) from the working tree.
- Added original synthetic fixture [`tests/fixtures/sample_captions_synthetic.ar.vtt`](file:///home/thewizard/Qatta/tests/fixtures/sample_captions_synthetic.ar.vtt) (14 cues covering video editing, WebVTT/ASS timing, BiDi isolates, and CLI/JSON tooling, preserving `align:start position:100%`, mixed Arabic/English terms, numerals, and rolling overlap).
- Updated [`tests/test_fixtures.py`](file:///home/thewizard/Qatta/tests/test_fixtures.py), [`tests/fixtures/README.md`](file:///home/thewizard/Qatta/tests/fixtures/README.md), [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md#L117-L120), and [`docs/LICENSING_TRANSITION_AUDIT.md`](file:///home/thewizard/Qatta/docs/LICENSING_TRANSITION_AUDIT.md#L166). Zero active references remain in code, tests, scripts, or fixture documentation.

### 5.2 Factual Historical Exposure Note (`BLK-01-HIST` — **Pending Counsel Review**)

- **Origin & Affected Tags:** `tests/fixtures/sample_captions.ar.vtt` was committed in `1726837f7ed69057bd5ae60ad44a5ee539392056` (Oct 20, 2026) and is present with identical blob SHA `00778717c2ac5a1604d01c317353fc8265feab57` in all **5 published Git tags**: **`v0.1.0`**, **`v0.1.1`**, **`v0.1.2`**, **`v0.1.3`**, and **`v0.2.0`**.
- **Release Archive Exposure:** `git archive --format=tar --prefix=laqta-v0.2.0/ v0.2.0` (matching [`.github/workflows/release.yml`](file:///home/thewizard/Qatta/.github/workflows/release.yml)) includes `laqta-v0.2.0/tests/fixtures/sample_captions.ar.vtt`. No other release archive formats or package registries are configured in repo workflows.
- **Current Tree Status:** The file has been **removed from the current working tree** (uncommitted `D` pending maintainer commit).
- **Source Provenance:** **No verified original source URL** appears anywhere in commit messages, [`tests/fixtures/README.md`](file:///home/thewizard/Qatta/tests/fixtures/README.md) (which described it only as `"public broadcast captions"`), or anywhere else in the repository. Because origin and permissions are unknown, this audit **does not assert confirmed copyright infringement**.
- **Prospective Licensing Separation:** Historical presence of a removed third-party fixture inside `v0.1.0`–`v0.2.0` is legally distinct from prospective maintenance releases (`v0.2.5+`) continuing cleanly under the permanent MIT License (the previously evaluated MPL-2.0 transition proposal was rejected).
- **Recommended Options for Maintainer & Counsel Review:** (a) document the `v0.1.0`–`v0.2.0` fixture removal via release notes/erratum upon next tag without rewriting public Git history; (b) if counsel deems prior release artifacts unacceptable, re-upload clean release tarballs or yank/replace GitHub Release assets per GitHub/legal advice while documenting historical tag immutability; (c) preserve full traceability in provenance logs.

---

## 6. Asset Licensing Matrix (`BLK-04` — **Pending Maintainer Decision**)

[`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) regulates nominative and brand/trademark use of `Laqta` / `لقطة` marks; **it is NOT an artwork copyright license**. Every asset group below requires an explicit copyright disposition:

| Asset Group & Exact Path                                                                                                                                                | Inventory (Exact File Counts)                                                                                                 | Provenance & Copyright/Trademark Findings                                                                                                                                                                                                                     | Proposed Copyright Disposition (Maintainer Decision)                                                                                                                                                               |
| :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`Laqta_Brand_Kit/`](file:///home/thewizard/Qatta/Laqta_Brand_Kit) (`svg/`, `png/`, `README.md` — excluding `guidelines/`)                                              | **30 files:** `11` SVGs, `18` PNGs, `1` `README.md`                                                                           | Brand logos/icons/wordmarks. Currently excluded in [`docs/LICENSING.md`](file:///home/thewizard/Qatta/docs/LICENSING.md) §4.2 without granting copyright permission to OS/downstream redistributors.                                                          | **Excluded with copyright reserved** + explicit verbatim OS/distributor copyright grant (`TRADEMARKS.md` governs mark use) **OR Separate explicit copyright license** (e.g., CC-BY-4.0 / trademark-reserved grant) |
| [`Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png`](file:///home/thewizard/Qatta/Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png) | **1 file** (`935,124` bytes)                                                                                                  | **Format mismatch:** actual format via `file` is `RIFF (little-endian) data, WebP image, lossless, with alpha` (not renamed). **AI-generated artwork:** generation tool, tier, and terms unverified; no unrestricted copyright/redistribution rights claimed. | **Remove from future public distribution pending provenance** (recommended) **OR Excluded with copyright reserved** once AI tool/terms are verified                                                                |
| [`packaging/icons/`](file:///home/thewizard/Qatta/packaging/icons) (`hicolor/`)                                                                                         | **9 files:** `8` PNGs (`16`–`512`), `1` SVG (`laqta.svg`)                                                                     | Byte-identical copies of `Laqta_Brand_Kit/` icons; contradicts `docs/LICENSING.md` (§4.1 includes `packaging/`, §4.2 excludes Brand Kit).                                                                                                                     | **Separate explicit copyright license** (or **Excluded with copyright reserved** + explicit Linux/distro packager reproduction grant aligned with `TRADEMARKS.md` §3.2)                                            |
| [`frontend/public/`](file:///home/thewizard/Qatta/frontend/public)                                                                                                      | **11 files:** `5` SVGs, `5` PNGs, `1` `README.md` (copied into `frontend/dist/` on build)                                     | Copied from `Laqta_Brand_Kit/` app icons and logos; built into `frontend/dist/`. Self-hosters need explicit copyright right to serve these files alongside `dist/`.                                                                                           | **Separate explicit copyright license** (allowing unmodified serving in `frontend/dist/`, subject to `TRADEMARKS.md`) **OR Covered by MIT** (copyright only, with trademark exclusion)                             |
| [`docs/assets/`](file:///home/thewizard/Qatta/docs/assets) (diagrams, social cards & `screenshots/`)                                                                    | **10 files:** `2` SVGs (`social-preview.svg`, `workflow-demo.svg`), `4` root PNGs + `4` byte-identical PNGs in `screenshots/` | Architecture/workflow SVGs (`workflow-demo.svg`, `social-preview.svg`), social card PNG, logo PNG, and UI screenshots (`laqta-dashboard.png`, `laqta-studio.png`). Currently omitted from `docs/LICENSING.md`.                                                | **Covered by MIT** (or **Separate explicit copyright license** such as CC-BY-4.0 for docs/screenshots, preserving `TRADEMARKS.md` for embedded marks)                                                              |
| [`frontend/src/components/ui/BrandIcons.tsx`](file:///home/thewizard/Qatta/frontend/src/components/ui/BrandIcons.tsx) (`GitHubIcon`, `YouTubeIcon`)                     | **2 inline `<svg><path d="..."/></svg>` components**                                                                          | Third-party platform marks; nominative trademark permission does not automatically license copied SVG path geometry without checking upstream icon source (e.g., Simple Icons CC0-1.0 vs. vendor brand kit).                                                  | **Remove from future public distribution pending provenance** OR verify CC0-1.0 / upstream vendor permission under **Separate explicit copyright/notice entry**                                                    |

_(Also note: runtime `data/projects/*` media files and `frontend/dist/` build outputs on disk are gitignored and excluded from source release archives.)_

---

## 7. Employment & Client IP Verification Checklist (`BLK-02` — **Pending Maintainer Decision**)

Git commit authorship does not independently verify freedom from employment invention-assignment or client work-for-hire claims. Written maintainer sign-off is required for:

| Verification Item                                   | Inquiry                                                                                                                         | Status                          |
| :-------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------ | :------------------------------ |
| **1. Employment Agreements**                        | Confirm no 2026 employment contract creates invention-assignment, shop-right, or work-for-hire claims on Laqta.                 | **Pending Maintainer Decision** |
| **2. Consulting / Client Work-for-Hire**            | Confirm no code, pipeline design, or brand assets originated as client deliverables.                                            | **Pending Maintainer Decision** |
| **3. Personal Hardware & Resource Separation**      | Confirm development used personal equipment/accounts rather than employer resources.                                            | **Pending Maintainer Decision** |
| **4. Trade Secrets & Confidential Info**            | Confirm no third-party confidential information or proprietary algorithms are included.                                         | **Pending Maintainer Decision** |
| **5. Employer Open-Source Release / OSRB Sign-off** | Confirm whether written employer consent is needed for open-source MIT releases (`v0.2.5+`; earlier MPL-2.0 proposal rejected). | **Pending Maintainer Decision** |

---

## 8. Git Status & Audit Report Integrity

Exact Git state verified on November 15, 2026 (no changes staged or committed):

- `git ls-files docs/PROVENANCE_AUDIT.md` -> _(empty, exit 0 — untracked in index)_
- `git check-ignore -v docs/PROVENANCE_AUDIT.md` -> _(empty, exit 1 — not gitignored)_
- `git log --oneline -n 3 -- docs/PROVENANCE_AUDIT.md` -> _(empty — no commit history)_
- `git status --short --untracked-files=all`:
  - `M tests/fixtures/README.md`
  - `D tests/fixtures/sample_captions.ar.vtt`
  - `M tests/test_fixtures.py`
  - `?? docs/LICENSING.md`, `?? docs/LICENSING_TRANSITION_AUDIT.md`, `?? docs/OPEN_SOURCE_BUSINESS_MODEL.md`, `?? docs/PROVENANCE_AUDIT.md`, `?? docs/TRADEMARKS.md`, `?? tests/fixtures/sample_captions_synthetic.ar.vtt`

Commands that suppress untracked entries (`git status -uno`, `git diff`, `git diff --cached`, `git diff --check`) only inspect tracked paths, explaining why newly created untracked files can coexist with an apparently "clean" diff/status until `--untracked-files=all` or `git add` is used.

---

## 9. Verification & Test Reporting

Exact commands executed (preserving `backend/.venv` untouched):

### 9.1 Separate Python 3.11 / 3.12 Environment Check (`BLK-05`)

- `which python3.11 python3.12`: neither binary found in `PATH`.
- `uv python list`: reports only `cpython-3.15.2-linux-x86_64-gnu` (`/usr/bin/python3.15`); `/home/thewizard/.local/share/uv/python/` does not exist (the root cause of the broken `backend/.venv/bin/python` symlink).
- Because neither Python 3.11 nor Python 3.12 (nor `pytest` / `numpy` on host `python3.15`) is available in this environment, **no disposable `/tmp/laqta-audit-venv` could be built**, and `pytest` suites could not run:
  - `backend/.venv/bin/pytest tests/test_fixtures.py` -> **FAILED TO EXECUTE** (exit `126`: `bad interpreter: No such file or directory`).
  - `backend/.venv/bin/pytest backend/tests` -> **FAILED TO EXECUTE** (exit `126`).
  - `python3 -m pytest tests/test_fixtures.py` -> **FAILED TO EXECUTE** (exit `1`: `/usr/bin/python3: No module named pytest`; `qatta/stages/s02_transcript/__init__.py` also fails to import without `numpy`).
  - Affected unexecuted test modules referencing the VTT parser or fixture: `tests/test_fixtures.py`, `tests/test_youtube_subs_first.py`, `tests/test_s01_s02.py`, `tests/test_schema_and_pipeline.py`, `backend/tests/test_youtube_extractor.py`, plus full core and backend `pytest` suites.

### 9.2 Verification Checks Executed Separately From `pytest`

- **Standalone Python 3.15.2 stdlib WebVTT structural check** on [`tests/fixtures/sample_captions_synthetic.ar.vtt`](file:///home/thewizard/Qatta/tests/fixtures/sample_captions_synthetic.ar.vtt): **PASSED** (exit `0`; `VTT OK: cues=14, rolling_overlaps=2, align_pos_cues=14`) — separate from `pytest` and **not** a substitute for runtime `pytest` verification.
- `backend/.venv/bin/ruff check tests/test_fixtures.py`: **PASSED** (exit `0`; `All checks passed!`).
- `backend/.venv/bin/ruff format --check tests/test_fixtures.py`: **PASSED** (exit `0`; `1 file already formatted`).
- `frontend/node_modules/.bin/prettier --check docs/PROVENANCE_AUDIT.md docs/LICENSING.md docs/LICENSING_TRANSITION_AUDIT.md tests/fixtures/README.md`: **PASSED** (exit `0`; `All matched files use Prettier code style!`).
- `git diff --check`: **PASSED** (exit `0`).
- `grep -rn "sample_captions" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv .`: **0** active references to `sample_captions.ar.vtt` outside historical notes in `docs/PROVENANCE_AUDIT.md`, `docs/LICENSING.md`, and `docs/LICENSING_TRANSITION_AUDIT.md` (and stale bytecode in `tests/__pycache__`).

---

## 10. Final Blocker Status Breakdown

| Blocker ID         | Scope                                                                                                                                                                             | Exact Classification                                                                        | Required Action                                                                                                                                                                                                                                                                                                         |
| :----------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BLK-01-CURRENT** | Working-tree replacement of `sample_captions.ar.vtt` with synthetic technical VTT & clean repo references                                                                         | **Resolved**                                                                                | None in working tree (ready for maintainer review/commit when ready).                                                                                                                                                                                                                                                   |
| **BLK-01-HIST**    | Blob `00778717...` in immutable historical tags `v0.1.0`–`v0.2.0` and `git archive` tarballs without source URL                                                                   | **Pending Counsel Review** (+ **Pending Maintainer Decision**)                              | Counsel & maintainer decide on release erratum vs. GitHub Release asset remediation; separate from ongoing MIT maintenance releases.                                                                                                                                                                                    |
| **BLK-02**         | Employer, client work-for-hire, personal resource, and OSRB IP ownership attestation                                                                                              | **Pending Maintainer Decision**                                                             | Maintainer reviews and signs Section 7 checklist.                                                                                                                                                                                                                                                                       |
| **BLK-03**         | Non-whitelisted lockfile licenses (`MPL-2.0`, `PSF-2.0`/`PSFL`, `CC-BY-4.0`, `BlueOak-1.0.0`, `MIT-0`, `numpy`); unpinned `[analysis]`/`[url]`; `Dockerfile`/PyAV FFmpeg binaries | **Pending Maintainer Decision** / **Technically Unverified** / **Future Distribution Gate** | Approve `POLICY.md` exception proposals (do not assume MPL dependencies relicense Laqta); resolve `[analysis]`/`[url]` locks; satisfy LGPL/GPL obligations before publishing Docker/binary artifacts.                                                                                                                   |
| **BLK-04**         | Copyright vs. `TRADEMARKS.md` alignment, `BrandIcons.tsx` SVG path provenance, AI WebP reference board (`generated-brand-direction-reference.png`)                                | **Pending Maintainer Decision**                                                             | Assign explicit copyright dispositions per Section 6 matrix; verify AI terms & `.png`/WebP status; verify `BrandIcons.tsx` SVG paths.                                                                                                                                                                                   |
| **BLK-05**         | `pytest tests/test_fixtures.py`, VTT parser tests, and core/backend `pytest` execution                                                                                            | **Resolved in Disposable Verification Env**                                                 | Re-verified on 2026-11-15 in disposable `/tmp/laqta-verify-311` (Python `3.11.17`): core `tests/` `218 passed, 1 skipped` in sandbox + loopback probe `1 passed` outside sandbox (`test_fixtures.py` `4/4` passed); `backend/tests` `295 passed, 2 skipped` (`80.57%` coverage); broken `backend/.venv` left untouched. |

> **License Decision Status:** Baseline **`v0.2.0` (MIT)** and target **`v0.2.5` (MIT)** remain permanently **MIT-licensed**; the earlier proposed MPL-2.0 transition was explicitly **rejected by the maintainer**.
