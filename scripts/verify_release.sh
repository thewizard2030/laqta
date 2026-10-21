#!/usr/bin/env bash
#
# Laqta — prove that a release actually works, from a clean clone.
#
#   ./scripts/verify_release.sh              # clone + install + full round trip
#   ./scripts/verify_release.sh --skip-install   # only the round trip
#
# The round trip: import → transcribe → rank → render → verify the MP4.
# It needs ffmpeg, espeak-ng (development-only: it synthesises the demo
# narration) and the local speech model.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

command -v ffmpeg >/dev/null 2>&1 || fail "ffmpeg is required (rendering)."
command -v espeak-ng >/dev/null 2>&1 || fail "espeak-ng is required to synthesise the demo narration."
command -v git >/dev/null 2>&1 || fail "git is required (the verifier clones the repository)."

PYTHON="$REPO_ROOT/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

info "Running the release verification"
"$PYTHON" "$REPO_ROOT/scripts/verify_release.py" --source "$REPO_ROOT" "$@"
