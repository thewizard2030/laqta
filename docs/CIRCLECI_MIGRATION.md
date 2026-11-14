# CircleCI Migration & Smarter Testing Guide

This document records the migration of continuous integration for **Laqta (لقطة)** from GitHub Actions to **CircleCI 2.1** with **Smarter Testing**.

---

## 1. Executive Summary

Laqta's CI infrastructure has been migrated to a high-speed, parallel CircleCI pipeline that runs on Linux Docker convenience images (`cimg/python:3.12` and `cimg/node:22.14`).

- **Deterministic Caching**: Lockfile and manifest checksum keys prevent stale dependency builds and eliminate redundant downloads.
- **Smarter Testing**: Configured via `.circleci/test-suites.yml`, providing atom-level test discovery, JUnit XML reporting, and test results ingestion for both Python (backend & core) and TypeScript (frontend).
- **Concurrency**: Backend and frontend verification jobs execute concurrently.
- **Fail-Safe GitHub Actions Retention**: Existing GitHub Actions workflows (`.github/workflows/`) remain present in the repository and active until CircleCI is fully verified on the default branch.

---

## 2. CI Architecture Mapping Table

| GitHub Actions Job / Workflow | CircleCI Job | Image / Environment | Commands & Tools |
| :--- | :--- | :--- | :--- |
| **`ci.yml` &rarr; `backend`** | `backend` | `cimg/python:3.12` | `ruff check`, `ruff format --check`, `python scripts/check_version.py`, `circleci testsuite run "backend-tests"` |
| **`ci.yml` &rarr; `frontend`** | `frontend` | `cimg/node:22.14` | `npm run typecheck`, `npm run lint`, `npm run format:check`, `circleci testsuite run "frontend-tests"`, `npm run build` |
| **`ci.yml` &rarr; `security`** | Can run as step in `backend`/`frontend` or dedicated job | `cimg/python` / `cimg/node` | `pip-audit --requirement backend/requirements-asr.txt`, `npm audit --omit=dev --audit-level=high` |
| **`evaluation.yml`** | Scheduled / Manual job | `cimg/python:3.12` | `python scripts/evaluate_ranking.py --check` (ranking benchmark with zero regressions) |
| **`release.yml`** | Tag-triggered release | `cimg/base` | Releases published on verified Git tags matching manifest versions |

---

## 3. Smarter Testing Configuration (`.circleci/test-suites.yml`)

The Smarter Testing configuration defines two isolated test suites:

### Backend Test Suite (`backend-tests`)
```yaml
---
name: backend-tests
discover: find tests backend/tests -type f -name 'test*.py' | sort
run: pytest --disable-pytest-warnings --no-header --quiet --tb=short --override-ini=junit_family=legacy --junit-xml="<< outputs.junit >>" << test.atoms >>
options:
  store-test-results: true
```
- **Discovery**: Automatically identifies all 42 Python test files across root `tests/` (core pipeline) and `backend/tests/` (API routes, services, settings, jobs).
- **Execution**: Invokes pytest with JUnit XML output directly delivered to CircleCI's test results collector.

### Frontend Test Suite (`frontend-tests`)
```yaml
---
name: frontend-tests
discover: cd frontend && npx vitest list --filesOnly
run: cd frontend && npx vitest run --reporter=junit --outputFile="<< outputs.junit >>" --bail 0 << test.atoms >>
options:
  store-test-results: true
```
- **Discovery**: Queries Vitest for all 18 test suites in `frontend/src/tests/`.
- **Execution**: Executes selected test atoms with `--reporter=junit` to stream XML results to `<< outputs.junit >>`.

---

## 4. Local Validation

Both configurations are locally validated with the CircleCI CLI:

```bash
# Validate main pipeline configuration:
circleci config validate .circleci/config.yml

# Validate backend test suite:
circleci testsuite doctor "backend-tests"

# Validate frontend test suite:
circleci testsuite doctor "frontend-tests"
```

All commands exit with code `0`.
