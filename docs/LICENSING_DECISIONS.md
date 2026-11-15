# Laqta — Licensing Decisions Record (MIT Continuity & Governance)

**Baseline Release:** `v0.2.0` (MIT License)  
**Target Release:** `v0.2.5` (**MIT License** — Permanently Retained)  
**Maintainer Decision Status:** **MPL-2.0 Transition REJECTED; MIT License Permanently Retained**  
**Date:** November 15, 2026

> [!IMPORTANT]
> **Definitive Maintainer Licensing Decision:** The maintainer explicitly **rejected** the previously proposed transition to MPL-2.0 for `v0.2.5`. **Laqta remains permanently licensed under the [MIT License](file:///home/thewizard/Qatta/LICENSE)** across all releases (`v0.1.0`–`v0.2.5+`). Root [`LICENSE`](file:///home/thewizard/Qatta/LICENSE), package license metadata, and historical Git tags remain under MIT. Earlier Phase 3.1/3.2 MPL-2.0 evaluation notes are preserved strictly as **historical superseded proposals**.

---

## 0. Final Software License Decision (`DEC-00`)

- **Decision:** **RETAIN MIT PERMANENTLY.** Reject MPL-2.0 relicensing for `v0.2.5` and future first-party Laqta releases.
- **Preserved Artifact Separation:**
  1. First-party code in `qatta/`, `backend/`, `frontend/src/`, `tests/`, `scripts/` remains under the **MIT License**.
  2. Third-party dependencies (including `MPL-2.0` packages such as `certifi`, `tqdm`, and build-time `lightningcss`) retain their own separate upstream licenses and notice obligations and do not alter Laqta's MIT first-party licensing.
  3. Non-code assets (`Laqta_Brand_Kit/`, `packaging/icons/`, `docs/assets/`) remain governed separately from code copyright and subject to [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md).

---

## 1. Historical Caption Fixture Exposure Decision (`BLK-01-HIST`)

### 1.1 Verified Factual Record

Inspection of repository history and release tags establishes:

- **Introduction:** `tests/fixtures/sample_captions.ar.vtt` (1,175 lines of Arabic broadcast political commentary) was added in commit `1726837f7ed69057bd5ae60ad44a5ee539392056` (`feat: Laqta v0.1.0`, Oct 20, 2026).
- **Affected Tags:** Identical Git blob `00778717c2ac5a1604d01c317353fc8265feab57` is present in all five published tags: **`v0.1.0`**, **`v0.1.1`**, **`v0.1.2`**, **`v0.1.3`**, and **`v0.2.0`**.
- **Archive Exposure:** `git archive --format=tar --prefix=laqta-v0.2.0/ v0.2.0` (the release packaging mechanism in [`.github/workflows/release.yml`](file:///home/thewizard/Qatta/.github/workflows/release.yml)) includes `laqta-v0.2.0/tests/fixtures/sample_captions.ar.vtt`. No other historical release archive formats exist in workflow definitions.
- **Provenance Gap:** **No verified original source URL** appears in commit messages, historical [`tests/fixtures/README.md`](file:///home/thewizard/Qatta/tests/fixtures/README.md) (which described it only as `"public broadcast captions"`), or anywhere in the repository. Because the original source, copyright owner, and any applicable broadcast/platform terms are unknown, **this package does not assert confirmed copyright infringement**.
- **Current Tree Remediation:** `tests/fixtures/sample_captions.ar.vtt` has been deleted from the working tree (`BLK-01-CURRENT` **Resolved**) and replaced with the original synthetic technical track [`tests/fixtures/sample_captions_synthetic.ar.vtt`](file:///home/thewizard/Qatta/tests/fixtures/sample_captions_synthetic.ar.vtt).

### 1.2 Legal Scope Distinctions

1. **Historical Exposure vs. Ongoing MIT Releases:** Historical presence of a removed third-party fixture in `v0.1.0`–`v0.2.0` is legally separate from prospective maintenance releases (`v0.2.5+`) continuing cleanly under MIT with the original synthetic fixture. _(Historical note: an earlier Phase 3.2 draft evaluated prospective MPL-2.0 at `v0.2.5`; that MPL-2.0 proposal has since been rejected.)_
2. **History Immutability:** Public Git history and immutable tags (`v0.1.0`–`v0.2.0`) should **not** be rewritten (`git filter-repo` / force-push is rejected as destructive to downstream clones and cryptographic release provenance).
3. **Supplementary Snapshots:** Attaching a separate corrected snapshot to an existing release does **not** remove GitHub's tag-generated source `.zip`/`.tar.gz` archives or erase historical distribution exposure.

### 1.3 Evaluated Options

| Option                                            | Action                                                                                                                                                                                                                                           | Benefits                                                                                                                                                    | Limitations & Risks                                                                                                                                                                         |
| :------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Option A** _(Release Erratum Only)_             | Preserve existing tags and archives unchanged; publish a factual release erratum in release notes / `CHANGELOG` documenting removal from the current tree (`v0.2.5` or erratum note) while leaving `v0.1.0`–`v0.2.0` history intact.             | Preserves immutable Git/tag history; transparent factual record; zero repository breakage; minimal operational risk.                                        | Prior `v0.1.0`–`v0.2.0` GitHub tag archives continue to contain the removed fixture blob.                                                                                                   |
| **Option B** _(Supplementary Corrected Snapshot)_ | Preserve historical tags, keep the existing release history visible, and attach a clearly labeled supplementary cleaned source tarball (e.g., `laqta-v0.2.0-fixture-remediated.tar.gz`) to the `v0.2.0` GitHub Release with an explanatory note. | Gives users visiting the `v0.2.0` release page an immediate cleaned tarball download without changing tags.                                                 | **Does not erase historical exposure**; GitHub's automatic tag-based `Source code (zip/tar.gz)` archives still include the old fixture; adds asset-management complexity on an old MIT tag. |
| **Option C** _(Specialist Legal Advice First)_    | Seek qualified copyright counsel review of historical distribution exposure before publishing any erratum or modifying GitHub Release assets.                                                                                                    | Obtains jurisdiction-specific legal guidance on whether passive historical tag availability requires affirmative archive/release action or a simple notice. | Introduces counsel consultation lead time and cost before finalizing `v0.2.5` historical closure.                                                                                           |

### 1.4 Recommendation

- **Safest Practical Recommendation:** **Combine Option C with Option A** — obtain brief specialist legal review (Option C) confirming that **Option A** (preserving immutable tags, publishing a factual release erratum documenting working-tree removal, and keeping prospective `v0.2.5` clean) is sufficient without altering or removing `v0.1.0`–`v0.2.0` release assets. Option B is **not** recommended as a substitute for legal certainty because GitHub tag archives remain immutable unless the release/tag itself is altered. Final selection remains solely with the maintainer.

---

## 2. Companion Policy Proposals

Detailed dependency and visual-asset rules are broken out into companion proposal documents:

- **Dependency Policy Proposal (`BLK-03`):** [`docs/DEPENDENCY_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/DEPENDENCY_POLICY_PROPOSAL.md) — covers Category A (runtime packages), Category B (build/test/dev tools including GPL `espeak-ng`), Category C (`CC-BY-4.0` datasets & non-code content), exact audited Python/frontend lockfile findings, and unverified `[analysis]`/`[url]` extras.
- **Asset Copyright Policy Proposal (`BLK-04`):** [`docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md) — covers copyright vs. trademark separation across `Laqta_Brand_Kit/`, `Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png`, `packaging/icons/`, `frontend/public/`, `docs/assets/`, and `frontend/src/components/ui/BrandIcons.tsx`.

---

## 3. FFmpeg & Future Container Distribution Policy (`BLK-03` Gate)

### 3.1 Current Verified State

- **No Published Container Images:** Neither [`.github/workflows/`](file:///home/thewizard/Qatta/.github/workflows) (`release.yml`, `release-check.yml`, `ci.yml`, `evaluation.yml`, `audits.yml`, `scorecard.yml`) nor [`docker-compose.yml`](file:///home/thewizard/Qatta/docker-compose.yml) builds or publishes official Docker images to `ghcr.io`, Docker Hub, or any container registry. `docker-compose.yml` executes a **local** build on the user's host.
- **Source-Only GitHub Releases:** [`.github/workflows/release.yml`](file:///home/thewizard/Qatta/.github/workflows/release.yml) publishes only `git archive` source `.tar.gz` files (`0` FFmpeg binaries, `0` PyAV wheels, `0` desktop installers).
- **What [`Dockerfile`](file:///home/thewizard/Qatta/Dockerfile) & PyAV Pull If Built:**
  - Installs Debian `ffmpeg`, `libass9`, and `curl`, plus `pip install --no-cache-dir -e ".[asr]"` (unpinned to `backend/requirements-lock.txt`).
  - Inspection of `backend/.venv/lib/python3.12/site-packages/av.libs/` (`av==19.0.2`; lockfile pins `av==18.1.0`, `BSD-3-Clause`) confirms bundled **30 `.so` libraries**, including FFmpeg core libraries (`libavcodec-d61378e8.so.63.1.102`, `libavdevice`, `libavfilter`, `libavformat`, `libavutil`, `libswresample`, `libswscale`) and GPL codecs **`libx264-d6533a8d.so.165`** and **`libx265-eebb7db1.so.217`**.
- **Classification:** Because no official images or PyAV binary bundles are published today, this is a **Future Distribution Gate**, **not** an active published-binary violation. However, invoking `ffmpeg` via `subprocess` in Laqta Python code does **not** exempt binary redistribution obligations whenever a container image, PyAV wheel bundle, or installer containing FFmpeg binaries is distributed.

### 3.2 Mandatory Future Container & Binary Distribution Checklist

Before publishing any official Docker image (`Dockerfile`), binary Python bundle, or desktop installer that includes FFmpeg or PyAV wheels, release engineering must complete all six gates:

1. **Exact FFmpeg Version & Build Configuration:** Record exact Debian/system `ffmpeg` package version and `ffmpeg -buildconf` output (`--enable-gpl`, `--enable-version3`, `--enable-nonfree` verification — `--enable-nonfree` renders builds unredistributable).
2. **PyAV Version & Wheel Provenance:** Pin exact `av` wheel version (reconciling lockfile `av==18.1.0` vs. PyPI `19.0.2`), hash, and upstream wheel source repository (`PyAV-Org/PyAV` / `ffmpeg` build matrix), or evaluate building/installing without redistributable GPL wheels if LGPL-only distribution is desired.
3. **GPL / LGPL Component Identification:** Enumerate bundled codecs and shared objects (e.g., `libx264`, `libx265`, `libavcodec`, `libgnutls`, `libdav1d`, `libvpx`, `libSvtAv1Enc`) and identify whether GPL-2.0+, GPL-3.0, or LGPL-2.1+ governs the distributed artifact.
4. **Corresponding Source Availability:** Verify upstream Debian `apt-get source` / `PyAV` + FFmpeg + x264/x265 build scripts and exact corresponding source archive matching the distributed binary versions.
5. **Copyright & License Notices:** Bundle complete `LICENSE` / `COPYING` files, copyright disclosures, and a binary/image SBOM inside the distributed artifact and release page.
6. **Written Offer / Corresponding Source Mechanism:** Publish a compliant corresponding-source download link or written offer under GPL §6 / LGPL §4 alongside the distributed container tag or installer (especially given `Dockerfile` also ships `certifi`/`tqdm` under `MPL-2.0`, whose §3.1/§3.2 source notice obligations apply concurrently).

---

## 4. Technical Validation Status (`BLK-05` — Verified in Clean-Room Python 3.11)

### 4.1 Environment Isolation & Verification Closure

- `backend/.venv` remains untouched (broken symlink to missing Python 3.12).
- On November 15, 2026, a disposable Python `3.11.17` virtual environment was provisioned outside the repository (`/tmp/laqta-verify-311`) with `backend/requirements-dev.txt` plus editable core/backend packages (`av==18.1.0`, `numpy==2.4.6`, `pytest==9.2.0`, `faster-whisper==1.2.1`, `yt-dlp==2026.10.26`).
- Measured verification results (`BLK-05` **Resolved** in isolated verification env):
  - `tests/` (core): `218 passed, 1 skipped` in sandbox + `test_http_probe_reads_a_local_response` passed (`1 passed` outside sandbox; failed inside sandbox solely because loopback socket access is restricted).
  - `backend/tests/`: `295 passed, 2 skipped` (`80.57%` coverage vs. `78.78%` baseline).
  - `frontend/`: `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test` (`18 files, 116 tests`), and `npm run build` all passed; `npm audit --omit=dev --audit-level=high` found `0` vulnerabilities.

---

## 5. Maintainer Decision Checklist

> [!NOTE]
> **All checkboxes below are intentionally left blank (`[ ]`) for the maintainer.** Checking or approving any item authorizes implementation in a subsequent phase only; nothing in this package takes effect until approved and implemented.

### 5.1 Policy & Release Governance Decisions

| ID         | Decision Item                                                                                                                                                                                                                                                        | Proposal Reference                                                                                                           | Maintainer Decision _(Select One)_                                      |
| :--------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------- |
| **DEC-01** | **Historical Caption Fixture (`BLK-01-HIST`):** Adopt Option A (factual release erratum, keep historical tags intact), Option B (erratum + supplementary snapshot), or Option C (seek counsel advice first)                                                          | Section 1                                                                                                                    | `[ ] Option A` `[ ] Option B` `[ ] Option C` `[ ] Option C -> Option A` |
| **DEC-02** | **Expanded Runtime Dependency Policy:** Permit `MPL-2.0`, `PSF-2.0`, `BlueOak-1.0.0`, `MIT-0` (plus `numpy` permissive subcomponents) alongside `MIT`/`Apache-2.0`/`BSD`/`ISC`/`Unlicense`; keep GPL/AGPL runtime prohibited                                         | [`DEPENDENCY_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/DEPENDENCY_POLICY_PROPOSAL.md) §1                        | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |
| **DEC-03** | **Separate Development / Build / Test Dependency Policy:** Separate dev-only tooling (`lightningcss`, `defusedxml`, `minimatch`, `@csstools/color-helpers`, GPL-3.0 `espeak-ng`) from shipped runtime bundles, requiring notices if dev tools are ever redistributed | [`DEPENDENCY_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/DEPENDENCY_POLICY_PROPOSAL.md) §2                        | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |
| **DEC-04** | **CC-BY / Non-Code Dataset Policy:** Govern `CC-BY-4.0` content/data dependencies (`caniuse-lite`, future datasets) with source, attribution, link, modification notice, and redistribution review                                                                   | [`DEPENDENCY_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/DEPENDENCY_POLICY_PROPOSAL.md) §3                        | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |
| **DEC-05** | **Documentation & Screenshot Copyright License:** License [`docs/assets/`](file:///home/thewizard/Qatta/docs/assets) (`10` files) under `CC BY 4.0` (with `TRADEMARKS.md` preserved for embedded marks) once ownership is confirmed                                  | [`ASSET_COPYRIGHT_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md) §2.5            | `[ ] Approve CC BY 4.0` `[ ] Keep MIT` `[ ] Reject`                     |
| **DEC-06** | **Laqta Brand Asset Redistribution Permission:** Reserve copyright in `Laqta_Brand_Kit/`, `packaging/icons/`, and `frontend/public/` with narrow explicit copyright permission for unchanged redistribution in official/OS/self-hosted Laqta packages                | [`ASSET_COPYRIGHT_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md) §§2.1, 2.3, 2.4 | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |
| **DEC-07** | **AI Concept Board & `BrandIcons.tsx` Exclusion Pending Provenance:** Exclude `generated-brand-direction-reference.png` (lossless WebP) and verify/replace `BrandIcons.tsx` GitHub/YouTube SVG paths before `v0.2.5`                                                 | [`ASSET_COPYRIGHT_POLICY_PROPOSAL.md`](file:///home/thewizard/Qatta/docs/ASSET_COPYRIGHT_POLICY_PROPOSAL.md) §§2.2, 2.6      | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |
| **DEC-08** | **Future Docker / Binary Distribution Gate:** Maintain prohibition on publishing official Docker images or binary installers until the Section 3.2 FFmpeg/PyAV GPL/LGPL & MPL-2.0 compliance checklist is completed                                                  | Section 3                                                                                                                    | `[ ] Approve` `[ ] Reject` `[ ] Modify`                                 |

### 5.2 Separate Maintainer IP Ownership Attestation (`BLK-02`)

_(Kept strictly separate from policy governance decisions above — see [`docs/PROVENANCE_AUDIT.md`](file:///home/thewizard/Qatta/docs/PROVENANCE_AUDIT.md) Section 7.)_

- `[ ]` **Employment Agreements:** Confirmed no 2026 employment agreement grants invention-assignment, shop-right, or work-for-hire claims over Laqta code, tests, docs, or original assets.
- `[ ]` **Consulting & Client Work-for-Hire:** Confirmed no Laqta code, schemas, or assets originated as client deliverables.
- `[ ]` **Hardware & Account Separation:** Confirmed development used personal hardware/accounts.
- `[ ]` **Trade Secrets & Third-Party Confidentiality:** Confirmed no employer or client confidential material is present.
- `[ ]` **Employer / OSRB Consent (If Applicable):** Confirmed written consent obtained or not required for Laqta's open-source MIT releases (`v0.1.0`–`v0.2.5+`; earlier prospective MPL-2.0 transition proposal rejected).

---

## 6. Legal Questions Intentionally Left Open

This audit package does **not** render legal opinions on the following open questions requiring maintainer or counsel judgment:

1. Whether passive historical availability of blob `00778717...` in immutable `v0.1.0`–`v0.2.0` GitHub tags requires GitHub Release archive replacement beyond a factual erratum.
2. Whether [`Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png`](file:///home/thewizard/Qatta/Laqta_Brand_Kit/guidelines/generated-brand-direction-reference.png) enjoys protectable copyright or clean commercial redistribution rights under its generator's terms and applicable law.
3. Exact statutory scope of unregistered trademark claims in [`docs/TRADEMARKS.md`](file:///home/thewizard/Qatta/docs/TRADEMARKS.md) across civil-law and common-law jurisdictions.
4. Exact LGPL/GPL binary redistribution mechanics (Debian source matching vs. PyAV custom/no-GPL build) if official container images or desktop installers are introduced after `v0.2.5`.
5. Lockfile resolution and license clearance of optional Python `[analysis]` (`librosa`, `soundfile`, `scenedetect[opencv]`, `mediapipe`) and `[url]` (`yt-dlp`) dependency trees.
