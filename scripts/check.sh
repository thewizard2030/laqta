#!/usr/bin/env bash
#
# Laqta — run every quality gate locally, exactly like CI does.
#
#   ./scripts/check.sh            # everything
#   ./scripts/check.sh --fast     # skip the build and the audit
#
# CI runs the same steps; if this passes, the workflow should too.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/backend/.venv"
FRONTEND_DIR="$REPO_ROOT/frontend"

FAST=0
[[ "${1:-}" == "--fast" ]] && FAST=1

FAILURES=()
STEP=0

info()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
pass()  { printf '\033[0;32m  ok\033[0m %s\n' "$*"; }
fail()  { printf '\033[0;31m FAIL\033[0m %s\n' "$*"; FAILURES+=("$*"); }
skip()  { printf '\033[0;33m skip\033[0m %s\n' "$*"; }

run() {
  # run <label> <command...>
  local label="$1"; shift
  STEP=$((STEP + 1))
  info "[$STEP] $label"
  if "$@"; then
    pass "$label"
  else
    fail "$label"
  fi
}

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "No backend environment found. Run ./scripts/setup.sh first." >&2
  exit 1
fi
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "No frontend dependencies found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

PY="$VENV_DIR/bin/python"

# --- Backend ---------------------------------------------------------------
run "ruff lint"            "$VENV_DIR/bin/ruff" check qatta backend/app backend/tests tests scripts
run "ruff format"          "$VENV_DIR/bin/ruff" format --check qatta backend/app backend/tests tests scripts
run "version consistency"  "$PY" scripts/check_version.py
run "backend tests"        "$VENV_DIR/bin/pytest" -q --cov=app --cov=../qatta --cov-report=term:skip-covered backend
run "core tests"           "$VENV_DIR/bin/pytest" -q tests

# --- Frontend --------------------------------------------------------------
cd "$FRONTEND_DIR" || exit 1
run "typecheck"            npm run --silent typecheck
run "eslint"               npm run --silent lint
run "prettier"             npm run --silent format:check
run "frontend tests"       npm run --silent test

if [[ "$FAST" == "0" ]]; then
  run "production build"   npm run --silent build
  cd "$REPO_ROOT" || exit 1
  run "pip-audit"          "$VENV_DIR/bin/python" -m pip_audit --requirement backend/requirements-asr.txt --progress-spinner off
  cd "$FRONTEND_DIR" || exit 1
  run "npm audit (shipped)" npm audit --omit=dev --audit-level=high
  cd "$REPO_ROOT" || exit 1
else
  skip "build and the dependency audits (--fast)"
fi

# --- Summary ---------------------------------------------------------------
echo
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  printf '\033[0;32mAll %d gates passed.\033[0m\n' "$STEP"
  exit 0
fi

printf '\033[0;31m%d of %d gates failed:\033[0m\n' "${#FAILURES[@]}" "$STEP"
for failure in "${FAILURES[@]}"; do
  printf '  - %s\n' "$failure"
done
exit 1
