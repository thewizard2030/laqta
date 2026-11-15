# Releasing Laqta

The release is a **source-only GitHub Release** (`git archive` tarball + release notes from `CHANGELOG.md`) validated and published automatically by **CircleCI 2.1**. Laqta is MIT-licensed and is not published to PyPI, npm, or container registries — it runs from source.

---

## Versioning

The version has one source of truth:

```text
qatta/__init__.py  →  __version__ = "0.2.5"
```

Everything else mirrors it:

| Manifest                  | Field                                      |
| ------------------------- | ------------------------------------------ |
| `qatta/__init__.py`       | `__version__` — **the source of truth**    |
| `backend/app/__init__.py` | re-exports `from qatta import __version__` |
| `pyproject.toml`          | `[project].version`                        |
| `backend/pyproject.toml`  | `[project].version`                        |
| `frontend/package.json`   | `version`                                  |

`scripts/check_version.py` compares all five and fails on any mismatch.

```bash
python scripts/check_version.py        # verify (exit 1 on mismatch)
python scripts/check_version.py --show # print the version table
```

---

## CircleCI Primary CI/CD & Tag Release Pipeline

CircleCI ([`.circleci/config.yml`](../.circleci/config.yml)) is the **authoritative automated CI/CD and GitHub Release platform** for `thewizard2030/laqta`:

- **Branch/PR CI (`ci` workflow):** Runs `backend` (Ruff, `check_version.py`, Smarter Testing `backend-tests` and `core-tests`) and `frontend` (`tsc --noEmit`, ESLint, Prettier, Smarter Testing `frontend-tests`, `vite build`) on branch pushes and pull requests without access to release secrets.
- **Tag Release (`release` workflow):** Runs **only** on stable semantic tags matching `/^v\d+\.\d+\.\d+$/` (for example `v0.2.5`). Branch builds are excluded (`branches: ignore: /.*/`) and pre-release tags do not trigger publishing.
- **Dependent Job Filters:** All three jobs in `release` (`backend`, `frontend`, `publish-release`) declare identical `tags: only: /^v\d+\.\d+\.\d+$/` and `branches: ignore: /.*/` filters. `publish-release` runs **only after `backend` and `frontend` both pass**.

### Release Verification, Archive & SHA-256 Asset Integrity

1. `publish-release` verifies `CIRCLE_TAG` matches `^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$` and matches `qatta.__version__`, and checks `CHANGELOG.md` (`scripts/release_notes.py "$CIRCLE_TAG" --check`).
2. Builds `dist/laqta-${CIRCLE_TAG}.tar.gz` strictly from the immutable `$CIRCLE_TAG` commit using `git archive` (no unverified working-directory snapshot, `.env`, keys, SQLite DBs, model weights, `node_modules/`, or `frontend/dist/`).
3. Runs [`scripts/publish_github_release.py`](../scripts/publish_github_release.py) with `--verify-git-tag`, which:
   - Confirms `refs/tags/$CIRCLE_TAG^{commit}` resolves to `HEAD`, synthetic fixture `tests/fixtures/sample_captions_synthetic.ar.vtt` is included, and deprecated `tests/fixtures/sample_captions.ar.vtt` is absent.
   - Computes local archive **SHA-256** prior to upload and verifies uploaded asset `name`, byte `size`, and returned `sha256:` `digest`.
   - Enforces HTTPS on all requests, blocks unexpected redirects on API mutations, restricts asset verification download redirects strictly to trusted GitHub CDN hosts, and **strips `Authorization` headers across all redirects**.

---

## Configuring the Restricted CircleCI Context (`laqta-release-publishing`)

Never store `GITHUB_TOKEN` as a project-level CircleCI environment variable (project-level variables are exposed to every job, including PRs). Instead:

1. In **CircleCI -> Organization Settings -> Contexts**, create a Context named **`laqta-release-publishing`**.
2. Add environment variable **`GITHUB_TOKEN`** containing a **Fine-Grained GitHub Personal Access Token** scoped exclusively to repository **`thewizard2030/laqta`** with minimum permissions:
   - **`Contents: Read and write`** (required to create GitHub Releases and upload `.tar.gz` assets).
   - **`Workflows: Read and write`** (required when release commits modify files under `.github/workflows/`, as in `v0.2.5`).
3. Restrict context access in CircleCI to repository `thewizard2030/laqta` and authorized maintainer Security Groups where supported by the CircleCI organization plan. On personal GitHub accounts or CircleCI Free plans where group RBAC restrictions are unavailable, `context: laqta-release-publishing` on `publish-release` plus tag-only filters (`tags: only: /^v\d+\.\d+\.\d+$/`, `branches: ignore: /.*/`) and GitHub branch/tag rules isolate `GITHUB_TOKEN` from ordinary branch/PR jobs.

---

## Safe Retry & Conflict Behavior

`scripts/publish_github_release.py` is idempotent across retries and concurrent triggers without ever relying solely on file name + byte size:

- Looks up the release by tag (`GET /repos/{owner}/{repo}/releases/tags/{tag}`). Creates it if `404`; handles concurrent `422 already_exists` collisions by re-fetching the release.
- Inspects any existing asset matching `laqta-${CIRCLE_TAG}.tar.gz`:
  - Size mismatch -> fails immediately without deleting or overwriting.
  - Matching size + matching GitHub `sha256:` `digest` -> safe idempotent success.
  - Matching size + different `sha256:` `digest` -> fails immediately (`SHA-256 digest mismatch`).
  - Matching size + missing `digest` -> executes safe HTTPS download-and-hash verification (stripping `Authorization` on redirects) or **fails closed** if no verifiable HTTPS download URL exists.
- Handles concurrent `422 already_exists` during asset upload by re-fetching and verifying size + SHA-256 content.

To retry after fixing a token or transient error, re-run the `publish-release` job in CircleCI.

---

## Completed Release Record: `v0.2.5` (2026-11-15)

- **Tag & Verified Target Commit:** `v0.2.5` (`ac93f32810332cf2cbe5e8fbd43f77b7680856df`) -> [`8030cf5dd1a3acaa7b5f129a69e314f7739dc650`](https://github.com/thewizard2030/laqta/commit/8030cf5dd1a3acaa7b5f129a69e314f7739dc650) (PR #19)
- **CircleCI Release Workflow:** [`1a3a76df-da76-472a-a5f4-8a5631483787`](https://app.circleci.com/workflow/1a3a76df-da76-472a-a5f4-8a5631483787) (`backend`: `success`, `frontend`: `success`, `publish-release`: `success`)
- **Published GitHub Release:** https://github.com/thewizard2030/laqta/releases/tag/v0.2.5
- **Source Tarball Asset:** [`laqta-v0.2.5.tar.gz`](https://github.com/thewizard2030/laqta/releases/download/v0.2.5/laqta-v0.2.5.tar.gz) (`5468774` bytes, SHA-256 `a7a0117c2e4c36a7d6a3944d9100628f6af85d400378dc1f4384b5cdc038019e`)

---

## Release Checklist (Future Releases: `vX.Y.Z`)

Standard release flow: **candidate branch/PR -> merge to `main` -> annotated tag on verified `main` commit -> CircleCI `release` workflow -> GitHub Release verification**. Publishing the GitHub Release remains CircleCI's automated responsibility (`publish-release` via [`scripts/publish_github_release.py`](../scripts/publish_github_release.py)).

```bash
# 1. Verify version alignment, changelog, tests, and CircleCI config locally
python scripts/check_version.py
python scripts/release_notes.py vX.Y.Z --check
pytest tests --tb=short
cd backend && pytest tests -n auto && cd ..
cd frontend && npm run check && npm run build && cd ..
circleci config validate .circleci/config.yml

# 2. Push release candidate branch, open PR, wait for CircleCI `ci` pass, and merge to `main`
git push origin release/vX.Y.Z

# 3. Fetch updated `main`, confirm target commit SHA and CircleCI Context `laqta-release-publishing`,
#    create annotated tag on the exact verified `main` commit, and push ONLY the release tag
git fetch origin main
git rev-parse origin/main
git tag -a vX.Y.Z <VERIFIED_MAIN_SHA> -m "Laqta vX.Y.Z"
git push origin refs/tags/vX.Y.Z
```

### Post-Tag CircleCI & GitHub Release Verification (`vX.Y.Z`)

1. Confirm CircleCI `release` workflow (`backend`, `frontend`, and `publish-release`) completes with `success` on the pushed tag. Do not claim release publishing succeeded while any job is pending or failed.
2. Verify [GitHub Releases](https://github.com/thewizard2030/laqta/releases) contains a single non-duplicate release for `vX.Y.Z` pointing to `<VERIFIED_MAIN_SHA>`, populated with `CHANGELOG.md` notes, and attaching `laqta-vX.Y.Z.tar.gz` with verified byte size, SHA-256 digest, and expected repository contents.

---

## Legacy GitHub Actions Workflows (Manual Fallback Only)

GitHub Actions is **deprecated** as the automatic CI/CD and release platform:

- All six workflows under `.github/workflows/` (`release.yml`, `ci.yml`, `audits.yml`, `scorecard.yml`, `evaluation.yml`, `release-check.yml`) are configured for explicit **`workflow_dispatch` only** — none run automatically on `push`, `pull_request`, or `schedule`.
- [`.github/workflows/release.yml`](../.github/workflows/release.yml) requires explicit `confirm_manual_fallback: true` and runs [`scripts/publish_github_release.py`](../scripts/publish_github_release.py) so it cannot duplicate or overwrite CircleCI releases. See [`docs/CIRCLECI_MIGRATION.md`](../docs/CIRCLECI_MIGRATION.md) §5 for the full inventory.

---

## What a Release Contains & Model Weights Policy

- Tagged source tree tarball (`dist/laqta-vMAJOR.MINOR.PATCH.tar.gz`) under the **MIT License**.
- Release notes extracted from `CHANGELOG.md`.
- **No model weights, FFmpeg binaries, Docker images, or secrets.** `faster-whisper` weights download on first use; after download, Laqta operates offline.

---

## Regenerating the Python Dependency Lock

```bash
python scripts/generate_lock.py            # rewrite backend/requirements-lock.txt
python scripts/generate_lock.py --check    # verify hashes against backend/requirements-asr.txt
pip install --require-hashes -r backend/requirements-lock.txt
```
