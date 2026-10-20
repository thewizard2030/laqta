#!/usr/bin/env bash
#
# Laqta — run the API and the studio frontend together (development).
#
#   ./scripts/dev.sh
#
# Ctrl-C stops both processes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

HOST="${QATTA_HOST:-127.0.0.1}"
PORT="${QATTA_PORT:-8000}"

info() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$VENV_DIR/bin/uvicorn" ]] || fail "No backend environment found. Run ./scripts/setup.sh first."
command -v npm >/dev/null 2>&1 || fail "npm was not found. Install Node.js 20+."

pids=()
cleanup() {
  echo
  info "Stopping Laqta…"
  for pid in "${pids[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

info "Starting the API on http://$HOST:$PORT"
(
  cd "$BACKEND_DIR"
  exec "$VENV_DIR/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --reload
) &
pids+=("$!")

info "Starting the studio on http://127.0.0.1:5173"
(
  cd "$FRONTEND_DIR"
  exec npm run dev
) &
pids+=("$!")

echo
info "Both processes are running. Press Ctrl-C to stop."
wait -n
