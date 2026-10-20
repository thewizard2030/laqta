#!/usr/bin/env bash
#
# Laqta — one-command development setup.
#
#   ./scripts/setup.sh              # backend (API + local ASR) + frontend
#   ./scripts/setup.sh --all        # + URL ingestion and the analysis stages
#   ./scripts/setup.sh --api-only   # backend only, no heavy ASR models
#   ./scripts/setup.sh --no-frontend
#
# The script is idempotent: running it twice is safe.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

PROFILE="asr"
WITH_FRONTEND=1

info() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m!!\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) PROFILE="all"; shift ;;
    --api-only) PROFILE="api"; shift ;;
    --no-frontend) WITH_FRONTEND=0; shift ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) fail "Unknown option: $1" ;;
  esac
done

# --- Python -----------------------------------------------------------------
PYTHON_BIN="${PYTHON:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "python3 was not found. Install Python 3.11+."

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  fail "Python 3.11+ is required (found $PY_VERSION)."
fi
info "Python $PY_VERSION"

# --- Backend ----------------------------------------------------------------
if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating the backend virtual environment"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  info "Reusing the existing virtual environment"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

info "Upgrading pip"
python -m pip install --quiet --upgrade pip

case "$PROFILE" in
  api)  REQUIREMENTS="requirements.txt" ;;
  asr)  REQUIREMENTS="requirements-asr.txt" ;;
  all)  REQUIREMENTS="requirements-all.txt" ;;
  *)    fail "Unknown profile: $PROFILE" ;;
esac

info "Installing the backend ($PROFILE profile)"
python -m pip install --quiet -r "$BACKEND_DIR/$REQUIREMENTS"

info "Installing the backend development tools"
python -m pip install --quiet -r "$BACKEND_DIR/requirements-dev.txt"

# The core package and the CLI are used straight from the source tree.
info "Installing Laqta (core package + CLI) in editable mode"
python -m pip install --quiet -e "$REPO_ROOT"

# --- Frontend ---------------------------------------------------------------
if [[ "$WITH_FRONTEND" == "1" ]]; then
  command -v npm >/dev/null 2>&1 || warn "npm was not found — skipping the frontend."
  if command -v npm >/dev/null 2>&1; then
    cd "$FRONTEND_DIR"
    if [[ -f package-lock.json ]]; then
      info "Installing the frontend dependencies (npm ci)"
      npm ci --silent
    else
      info "Installing the frontend dependencies (npm install)"
      npm install --silent
    fi
    cd "$REPO_ROOT"
  fi
fi

# --- Report -----------------------------------------------------------------
echo
info "Setup complete."
echo
echo "  Start the API:      cd backend && .venv/bin/uvicorn app.main:app --reload"
echo "  Start the studio:   cd frontend && npm run dev"
echo "  Check the machine:  .venv/bin/laqta doctor"
echo
echo "  Docs: $REPO_ROOT/docs"
echo
