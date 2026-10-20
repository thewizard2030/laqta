# Releasing Laqta

The release is a **GitHub Release** (source + tag). Laqta is not published to
PyPI or npm — it runs from source.

---

## Versioning

The version has exactly one source of truth:

```
qatta/__init__.py  →  __version__ = "0.1.0"
```

Everything else mirrors it:

| Manifest | Field |
|----------|-------|
| `qatta/__init__.py` | `__version__` — **the source of truth** |
| `backend/app/__init__.py` | re-exports `from qatta import __version__` |
| `pyproject.toml` | `[project].version` |
| `backend/pyproject.toml` | `[project].version` |
| `frontend/package.json` | `version` |

`scripts/check_version.py` compares all five and **fails** on a mismatch. CI
runs it on every push, so a forgotten bump can never reach a tag.

```bash
python scripts/check_version.py        # verify (exit 1 on mismatch)
python scripts/check_version.py --show # print the table
```

### Bumping the version

```bash
# 1. Edit the single source of truth
$EDITOR qatta/__init__.py

# 2. Mirror it into the manifests
python scripts/check_version.py --show   # shows the mismatches
#    → update pyproject.toml, backend/pyproject.toml, frontend/package.json

# 3. Verify
python scripts/check_version.py          # must exit 0

# 4. Commit
git add qatta/__init__.py pyproject.toml backend/pyproject.toml frontend/package.json
git commit -m "chore: release v0.2.0"
```

Semantic versioning is used loosely: `MAJOR.MINOR.PATCH`.

---

## Release checklist

```bash
# 1. Everything green locally
python scripts/check_version.py
cd backend && pytest && pytest ../tests
cd ../frontend && npm run typecheck && npm run test && npm run build

# 2. Update the changelog
$EDITOR CHANGELOG.md      # add the version section under "Unreleased"

# 3. Check that the release notes can be extracted for the tag
python scripts/release_notes.py v0.2.0 --check

# 4. Tag and push
git tag -a v0.1.0 -m "Laqta v0.1.0 — local-first Shorts studio"
git push origin main
git push origin v0.1.0

# 5. The release workflow builds the notes and publishes the GitHub Release
#    (triggered by the tag; see .github/workflows/release.yml)
```

The release body is extracted from `CHANGELOG.md` by
`scripts/release_notes.py`. A tag without a matching section fails the
workflow — an empty release body would look intentional.

## What a release contains

- The tagged source tree (no binaries, no model weights — those are downloaded
  on first use).
- The `CHANGELOG.md` section for that version.
- The GitHub Release notes generated from the changelog.

## Model weights

Laqta does **not** ship model weights. The local speech model
(`faster-whisper` / CTranslate2, MIT) is downloaded on first use into the
Hugging Face cache. The download size depends on the profile:

| Profile | Model | Approx. download |
|---------|-------|------------------|
| `fast` | `base` | ~145 MB |
| `balanced` | `small` | ~460 MB |
| `accurate` | `medium` | ~1.5 GB |

The UI reports the model in use and fails with a clear error when a model is
missing. A first run therefore needs network access **once**; after that the
studio works fully offline.

## Repository settings to enable once (manual, in GitHub)

- Branch protection on `main`: require CI to pass + 1 approving review.
- Secret scanning and push protection.
- Dependency graph and Dependabot alerts.
- Discussions for support questions.

---

## Known dependency advisories

Both dependency trees are audited before a release:

```bash
# Python — the shipped runtime profile
uvx pip-audit --requirement backend/requirements-asr.txt

# Node — what actually ships to users
cd frontend && npm audit --omit=dev
```

**Current state (v0.1.0):** the Python runtime profile has **no known
vulnerabilities**, and the shipped Node dependency tree has **none either**
(`npm audit --omit=dev` → 0).

`npm audit` *without* `--omit=dev` reports 13 advisories in the **development**
tooling only:

| Package | Severity | Pulled by | Shipped to users? |
|---------|----------|-----------|-------------------|
| `tinypool` | critical | `vitest@2` (test worker pool) | no |
| `postcss` / `postcss-selector-parser` | moderate | `tailwindcss@3`, `autoprefixer` (build time) | no |
| others | high / moderate | dev-only chains | no |

The fixes require breaking upgrades (`vitest` 2 → 5, `tailwindcss` 3 → 4),
which are planned for a later release rather than smuggled into a patch
release. They affect CI and local development only — never the runtime a
user installs.

## What CI checks

Every push and pull request runs four jobs (`.github/workflows/ci.yml`):

| Job | What it proves |
|-----|----------------|
| `backend` | The API **and** the core pipeline pass on Python 3.11 **and** 3.12; `ruff check` and `ruff format --check` are clean; every manifest declares the same version. |
| `frontend` | `tsc --noEmit`, ESLint, Prettier, the Vitest suite and a production build all pass. |
| `security` | No committed secrets (gitleaks), no known Python vulnerabilities in the runtime profile, no high-severity issues in the shipped Node dependencies. |
| `dependency-review` | A pull request may not introduce a vulnerable or malformed dependency. |

The `audits.yml` workflow repeats the vulnerability scans weekly and on
demand, so a newly published advisory is noticed even without a commit.

> The **core** suite (`tests/`) is part of the `backend` job. It used to live
> outside CI entirely — a change that broke the manifest pipeline could pass
> the whole workflow.

## Regenerating the dependency lock

```bash
python scripts/generate_lock.py            # rewrite backend/requirements-lock.txt
python scripts/generate_lock.py --check    # verify it is current (CI uses this)
```

The lock is resolved for **Python 3.11** (the minimum supported version) and
carries SHA-256 hashes, so it installs identically on 3.11 and 3.12:

```bash
pip install --require-hashes -r backend/requirements-lock.txt
```
