# Scripts

## Overview
Development, testing, benchmarking, and lifecycle automation scripts for Laqta backend, frontend, and core pipeline.

## Interface
- `scripts/check.sh [--fast]`: Local CI runner executing all backend and frontend quality gates (ruff, version check, pytest with coverage, coverage baseline check, typecheck, eslint, prettier, vitest, and optional audits)
- `scripts/dev.sh`: Concurrent development launcher starting FastAPI uvicorn server on loopback (http://127.0.0.1:8000) and Vite studio frontend on http://127.0.0.1:5173
- `scripts/setup.sh [--all | --api-only | --no-frontend]`: POSIX environment bootstrap script setting up Python 3.11+ venv, installing backend requirements, editable qatta core, and frontend npm packages
- `scripts/setup.ps1`: Windows PowerShell setup script provisioning Python 3.11+ venv, backend dependencies, editable qatta core, and frontend npm packages
- `scripts/check_version.py [--show]`: Manifest version synchronization checker ensuring consistent version declarations across Python and Node manifests
- `scripts/check_coverage.py [--backend <file>] [--frontend <file>] [--show]`: Test coverage regression validator comparing current coverage against `config/coverage-baseline.json`
- `scripts/generate_lock.py [--profile {default,api,all}] [--python-version <ver>] [--no-hashes] [--check]`: Dependency lockfile generator and checker targeting Python 3.11 for `backend/requirements-lock.txt`
- `scripts/evaluate_ranking.py [--dataset <file>] [--baseline <file>] [--base <url>] [--no-start-api] [--check] [--write-baseline] [--json]`: Benchmark suite measuring clip selection precision, recall, F1, and coverage against synthesized ground-truth media
- `scripts/release_notes.py <tag> [--check]`: Changelog parser extracting release notes for a Git tag from `CHANGELOG.md`

## Invariants
- `[scripts/check.sh]`: Requires existing virtual environment at `backend/.venv` and frontend `node_modules` before execution
- `[scripts/dev.sh]`: Binds exclusively to loopback (127.0.0.1) by default and traps EXIT, INT, and TERM signals to terminate child processes cleanly
- `[scripts/setup.sh]`: Idempotent execution; requires Python >= 3.11 and installs qatta in editable mode
- `[scripts/check_version.py]`: `qatta/__init__.py.__version__` is the authoritative source of truth; exits 1 on mismatch
- `[scripts/check_coverage.py]`: Fails with exit code 1 if measured coverage regresses below the recorded baseline in `config/coverage-baseline.json`
- `[scripts/generate_lock.py]`: Resolves dependencies against the minimum supported Python version (3.11)
- `[scripts/evaluate_ranking.py]`: Ranking evaluation metrics must not regress beyond tolerance limits (0.10 for precision/recall/F1, 0.05 for bad coverage) against `benchmarks/baseline.json`
- `[scripts/release_notes.py]`: Target tag must have a corresponding release section in `CHANGELOG.md`; empty notes trigger exit code 1

## Side Effects
- `[scripts/setup.sh, scripts/setup.ps1]`: Provisions `backend/.venv/`, installs Python packages via pip, and executes npm ci / npm install in `frontend/`
- `[scripts/dev.sh]`: Spawns uvicorn and Vite processes, binding to loopback TCP ports 8000 and 5173
- `[scripts/check.sh]`: Writes `.coverage` and `coverage-backend.json`, compiles frontend into `frontend/dist/`
- `[scripts/generate_lock.py]`: Writes resolved package versions and hashes to `backend/requirements-lock.txt`
- `[scripts/evaluate_ranking.py]`: Spawns temporary uvicorn backend on port 8124, creates temporary directories, synthesizes WAV/MP4 files with espeak-ng and ffmpeg, and queries API endpoints

## Verification
- Run: `./scripts/check.sh --fast`
