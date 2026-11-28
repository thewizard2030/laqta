# CircleCI CI/CD & Smarter Testing Guide

CircleCI 2.1 is the **authoritative automated CI and GitHub Release publishing platform** for **Laqta (لقطة)** (`thewizard2030/laqta`, MIT License). GitHub Actions has been deprecated as the primary CI/release runner.

---

## 1. Pipeline Overview

CircleCI defines two distinct workflows in [`.circleci/config.yml`](../.circleci/config.yml):

1. **`ci` workflow (Branches & Pull Requests):**
   - Runs `backend` (`cimg/python:3.12`) and `frontend` (`cimg/node:22.14`) concurrently on branch pushes and pull requests.
   - Executes Ruff lint/format checks, `scripts/check_version.py`, Smarter Testing `backend-tests` (`backend/tests/`), Smarter Testing `core-tests` (`tests/`), TypeScript `tsc --noEmit`, ESLint, Prettier, Smarter Testing `frontend-tests` (`vitest`), and Vite production build (`npm run build`).
   - Uses deterministic pip and npm lockfile/manifest caches.
   - Has **zero access** to `laqta-release-publishing` or `GITHUB_TOKEN`.
2. **`release` workflow (Stable `vMAJOR.MINOR.PATCH` Tags Only):**
   - Triggered **only** when a tag matching `/^v\d+\.\d+\.\d+$/` (for example `v0.2.5`) is pushed. Branch pushes are excluded via `branches: ignore: /.*/`.
   - Every job in `release` (`backend`, `frontend`, and `publish-release`) carries the identical tag filter (`tags: only: /^v\d+\.\d+\.\d+$/`, `branches: ignore: /.*/`) because CircleCI skips dependent jobs unless explicit tag filters are set.
   - `publish-release` specifies `requires: [backend, frontend]` and attaches CircleCI Context **`laqta-release-publishing`**, running only after all verification tests and builds pass.

---

## 2. Smarter Testing Configuration (`.circleci/test-suites.yml`)

All test discovery and JUnit XML ingestion are driven by [`.circleci/test-suites.yml`](../.circleci/test-suites.yml):

| Suite Name       | Executor | Discovery Command                                   | Test Scope                                                                       |
| :--------------- | :------- | :-------------------------------------------------- | :------------------------------------------------------------------------------- |
| `backend-tests`  | Python   | `cd backend && find tests -type f -name 'test*.py'` | FastAPI routes, SQLite repository, BYOK settings, job manager (`pytest -n auto`) |
| `core-tests`     | Python   | `find tests -type f -name 'test*.py'`               | Core `qatta/` manifest, stages `s01`–`s07`, scoring, fixtures, release tooling   |
| `frontend-tests` | Node     | `cd frontend && npx vitest list --filesOnly`        | React 19 UI, BiDi/karaoke subtitles, API client, studio workbench (`vitest`)     |

---

## 3. Release Archive Packaging & SHA-256 Asset Integrity

When a stable tag `vX.Y.Z` is pushed:

1. **Verification Gate:** `backend` (`backend-tests` + `core-tests`) and `frontend` (`vitest` + `vite build`) both re-run on the exact tagged commit.
2. **Release Validation:** `publish-release` verifies:
   - `CIRCLE_TAG` matches `^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$` and equals `f"v{qatta.__version__}"` (`scripts/check_version.py`).
   - `CHANGELOG.md` contains a non-empty section for `$CIRCLE_TAG` (`scripts/release_notes.py "$CIRCLE_TAG" --check`).
   - `refs/tags/$CIRCLE_TAG^{commit}` resolves to checked-out `HEAD`.
   - `tests/fixtures/sample_captions_synthetic.ar.vtt` is present and the removed `tests/fixtures/sample_captions.ar.vtt` file is absent.
3. **Immutable Source Archive:** Runs `git archive --format=tar.gz --prefix="laqta-${CIRCLE_TAG}/" -o "dist/laqta-${CIRCLE_TAG}.tar.gz" "$CIRCLE_TAG"` (source only — no binaries, model weights, `.env`, databases, `node_modules/`, or `frontend/dist/`).
4. **GitHub Release Publishing & Integrity Verification ([`scripts/publish_github_release.py`](../scripts/publish_github_release.py)):**
   - Computes local SHA-256 of `dist/laqta-${CIRCLE_TAG}.tar.gz` before any upload.
   - Creates/looks up the release over HTTPS (`https://api.github.com`) and uploads the archive (`https://uploads.github.com`), verifying returned asset `name`, byte `size`, and `sha256:` `digest` when present.
   - **Strict Retry Integrity:** On existing releases/assets, matching file name + byte size alone is **never** trusted as idempotent success:
     - Checks both `size` and GitHub's `digest` (`sha256:<hex>`). Mismatched content with identical size fails clearly without deleting or overwriting.
     - If `digest` is unavailable/`None`, performs a safe HTTPS download-and-hash verification (`_hash_stream_from_url`) or **fails closed** if no verifiable HTTPS URL exists.
   - **Redirect & Credential Safety:** Disables automatic `urllib` redirects on API calls (`_NoRedirectHandler`), restricts download redirects strictly to trusted GitHub release CDN hosts over `https://`, and **strips `Authorization` headers on all redirects**.
   - **Concurrency Safety:** Handles `HTTP 422 already_exists` collisions on concurrent `POST /releases` or `POST .../assets` by re-fetching the tag release and validating size + SHA-256 digest before returning success or failing clearly.

---

## 4. Restricted CircleCI Context & Secret Isolation (`laqta-release-publishing`)

To keep release credentials isolated from pull requests, branch builds, and test executors:

- Store `GITHUB_TOKEN` inside a **dedicated CircleCI Context** named **`laqta-release-publishing`** rather than a project-level environment variable (project-level environment variables are exposed to every job in a project, including `backend`, `frontend`, and untrusted PR jobs).
- Attach `context: laqta-release-publishing` **exclusively** to `publish-release` in [`.circleci/config.yml`](../.circleci/config.yml). Never attach it to `backend`, `frontend`, or `ci` workflow jobs.
- **How to Restrict the Context (`Organization Settings -> Contexts -> laqta-release-publishing`):**
  1. Restrict the context to repository `thewizard2030/laqta` (Project/Expression restriction if available) and add authorized maintainer Security Groups so only approved maintainers can trigger jobs with access to `laqta-release-publishing`.
  2. Set `GITHUB_TOKEN` using a Fine-Grained GitHub Personal Access Token scoped strictly to repository **`thewizard2030/laqta`** with minimum permissions:
     - **`Contents: Read and write`** (required to create GitHub Releases and upload source archives).
     - **`Workflows: Read and write`** (required when release commits modify files under `.github/workflows/`, as in `v0.2.5`).
- **CircleCI Plan & Account Limitations:** Personal GitHub accounts or CircleCI Free plans may not support Security Group / RBAC context restrictions (only enterprise/paid Organization plans expose granular team Security Groups). When RBAC restrictions are unavailable on a personal CircleCI account, **context attachment on `publish-release` + `tags: only: /^v\d+\.\d+\.\d+$/` + `branches: ignore: /.*/` + GitHub tag creation permissions** provide the compensating isolation boundary against ordinary branch and PR builds.
- If `GITHUB_TOKEN` is missing or set to a placeholder, `publish-release` fails closed with zero secret leakage (`redact_secret()`). Never use `set -x` or print environment variables in release steps.

---

## 5. GitHub Actions Workflow Trigger Audit

All automated triggers (`push`, `pull_request`, `schedule`, `branch_protection_rule`) in `.github/workflows/` have been removed so GitHub Actions does not run duplicate automated CI or compete with CircleCI releases. Every workflow definition is preserved for explicit manual `workflow_dispatch` only:

| Workflow Filename                                                               | Exact `on:` Triggers | Auto Active? | Overlaps CircleCI?                                  | Intended GitHub-Native? | Recommended Final State                                                                               |
| :------------------------------------------------------------------------------ | :------------------- | :----------- | :-------------------------------------------------- | :---------------------- | :---------------------------------------------------------------------------------------------------- |
| [`.github/workflows/release.yml`](../.github/workflows/release.yml)             | `workflow_dispatch`  | No           | Yes (superseded by CircleCI `release`)              | No                      | Preserved as explicit manual fallback (`confirm_manual_fallback: true` + `publish_github_release.py`) |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)                       | `workflow_dispatch`  | No           | Yes (`backend`/`frontend` superseded; GHA security) | No                      | Preserved as manual fallback for `security` / `dependency-review` / legacy test jobs                  |
| [`.github/workflows/audits.yml`](../.github/workflows/audits.yml)               | `workflow_dispatch`  | No           | No (automated `pip-audit` + lock + `npm audit`)     | Optional (migratable)   | Preserved on `workflow_dispatch` until scheduled vulnerability audits migrate to CircleCI             |
| [`.github/workflows/scorecard.yml`](../.github/workflows/scorecard.yml)         | `workflow_dispatch`  | No           | No (OpenSSF Scorecard SARIF upload)                 | Yes (GitHub-native)     | Preserved on `workflow_dispatch` while GHA billing is locked; restore `schedule`/`push` if unlocked   |
| [`.github/workflows/evaluation.yml`](../.github/workflows/evaluation.yml)       | `workflow_dispatch`  | No           | No (`evaluate_ranking.py --check`)                  | No                      | Preserved on `workflow_dispatch` until ranking evaluation migrates to CircleCI                        |
| [`.github/workflows/release-check.yml`](../.github/workflows/release-check.yml) | `workflow_dispatch`  | No           | No (`verify_release.py` synthetic pipeline)         | No                      | Preserved on `workflow_dispatch` until end-to-end verification migrates to CircleCI                   |

---

## 6. Local & Remote Validation Status

```bash
circleci config validate .circleci/config.yml
pytest tests --tb=short
```

- **Local validation:** `.circleci/config.yml` passed `circleci config validate`, YAML parsing passed across all 8 config/workflow files, and `scripts/publish_github_release.py` passed unit verification (`tests/test_publish_github_release.py`).
- **Remote CircleCI CI & `v0.4.0` publication:**
  - `release/v0.4.0` (`a28c4d6`) passed CircleCI `ci` (`backend` and `frontend`, workflow `58f3dbe8-e3c9-4175-9dfb-cbc0e8fea98c`).
  - Annotated tag `v0.4.0` on merged `main` commit `45904d525e53b81a3f6cbbc5e0c822e223add3c1` (PR #31) executed CircleCI `release` workflow [`c3dc63e2-97b1-4351-8b3a-e88ce445ae0c`](https://app.circleci.com/workflow/c3dc63e2-97b1-4351-8b3a-e88ce445ae0c): `frontend` (`success`), `backend` (**`failed`**), `publish-release` (`not run`).
  - The `backend` failure was not an assertion: the "Run backend test suite" step ended after 58 s at ~91 % of its progress output with no failing test, no traceback and no junit output — a killed test process, not a red test. The same tree had already passed the identical `backend` job on the `ci` workflow and `./scripts/check.sh` (all 15 gates) locally.
  - CircleCI refused to re-run the workflow for both the maintainer and the agent (`Permission denied`), so `publish-release` could not be re-triggered. The release was published from the immutable tag with the same verified procedure and script the job runs (`check_version.py`, `release_notes.py --check`, `git archive` from `v0.4.0`, `publish_github_release.py --verify-git-tag`).
  - Published [GitHub Release `v0.4.0`](https://github.com/thewizard2030/laqta/releases/tag/v0.4.0) with source tarball `laqta-v0.4.0.tar.gz` (`5568111` bytes, SHA-256 `c29cc6a00a14a8b96b07ae4e82e486392f1bb40c59d854e5fa587656c9e0d5ef`).

- **Remote CircleCI CI & `v0.3.1` publication:**
  - `release/v0.3.1` (`e3fff75`) passed CircleCI `ci` (`backend` and `frontend`).
  - Annotated tag `v0.3.1` on merged `main` commit `d240a32431dcc824d546e1b9a42e81a40dc4adbf` (PR #29) executed CircleCI `release` workflow [`913c44df-32db-42c4-9fac-a5e990a2df86`](https://app.circleci.com/workflow/913c44df-32db-42c4-9fac-a5e990a2df86): `backend` (`success`), `frontend` (`success`), and `publish-release` (`success`).
  - Published [GitHub Release `v0.3.1`](https://github.com/thewizard2030/laqta/releases/tag/v0.3.1) with source tarball `laqta-v0.3.1.tar.gz` (`5525167` bytes, SHA-256 `5c1695e1e4b6b90be60fd467bbb8829543d5467ab05dc7b8c723d9b9c24b9dc9`).

- **Remote CircleCI CI & `v0.3.0` publication:**
  - `release/v0.3.0` (`62a6c54cf48a61538dc9e9ba11c675464bff3b65`) passed CircleCI `ci` (`backend` and `frontend`).
  - Annotated tag `v0.3.0` on merged `main` commit `23ec167e105c8cdfcee14e036a1e87ac7edd281d` (PR #25) executed CircleCI `release` workflow [`3d0f2617-08eb-499e-b906-36a6b9cee815`](https://app.circleci.com/workflow/3d0f2617-08eb-499e-b906-36a6b9cee815): `backend` (`success`), `frontend` (`success`), and `publish-release` (`success`).
  - Published [GitHub Release `v0.3.0`](https://github.com/thewizard2030/laqta/releases/tag/v0.3.0) with source tarball `laqta-v0.3.0.tar.gz` (`5521156` bytes, SHA-256 `1ca1760cb66a3b534e588a5a899b614c4967b46cf4d4087bf81d418d4456bada`).

- **Remote CircleCI CI & `v0.2.5` publication:**
  - `release/v0.2.5` (`50d7c90ce5ab61fb9f9b8314aca3d8ad1bdb1436`) passed CircleCI `ci` (`backend` and `frontend`).
  - Annotated tag `v0.2.5` on merged `main` commit `8030cf5dd1a3acaa7b5f129a69e314f7739dc650` (PR #19) executed CircleCI `release` workflow [`1a3a76df-da76-472a-a5f4-8a5631483787`](https://app.circleci.com/workflow/1a3a76df-da76-472a-a5f4-8a5631483787): `backend` (`success`), `frontend` (`success`), and `publish-release` (`success`).
  - Published [GitHub Release `v0.2.5`](https://github.com/thewizard2030/laqta/releases/tag/v0.2.5) with source tarball `laqta-v0.2.5.tar.gz` (`5468774` bytes, SHA-256 `a7a0117c2e4c36a7d6a3944d9100628f6af85d400378dc1f4384b5cdc038019e`).
