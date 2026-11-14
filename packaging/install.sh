#!/usr/bin/env bash
#
# Laqta — Install Linux desktop launcher and icons according to XDG specifications.
#
# Usage:
#   ./packaging/install.sh            # Install to ~/.local/share (user mode)
#   ./packaging/install.sh --user     # Install to ~/.local/share (user mode)
#   ./packaging/install.sh --system   # Install to /usr/local/share (system mode)
#   DESTDIR=/tmp/stage ./packaging/install.sh --user  # Staging mode
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DESTDIR="${DESTDIR:-}"
MODE="user"

for arg in "$@"; do
  case "$arg" in
    --system)
      MODE="system"
      ;;
    --user)
      MODE="user"
      ;;
    -h|--help)
      echo "Usage: $0 [--user|--system]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$MODE" == "system" ]]; then
  PREFIX="${DESTDIR}/usr/local/share"
else
  PREFIX="${DESTDIR}${HOME}/.local/share"
fi

APP_DIR="$PREFIX/applications"
ICON_DIR="$PREFIX/icons"

echo "==> Installing Laqta desktop integration to: $PREFIX"

mkdir -p "$APP_DIR"
mkdir -p "$ICON_DIR"

# Install desktop file with exact repository path
DESKTOP_SRC="$SCRIPT_DIR/laqta.desktop"
DESKTOP_TARGET="$APP_DIR/laqta.desktop"

# Copy desktop file and update Exec with absolute path to scripts/dev.sh
sed \
  -e "s|cd \\\\\$(dirname \\\\\$(readlink -f %k))/.. && ./scripts/dev.sh|$REPO_ROOT/scripts/dev.sh|g" \
  "$DESKTOP_SRC" > "$DESKTOP_TARGET"
chmod 0644 "$DESKTOP_TARGET"

# Install XDG hicolor icon hierarchy
if [[ -d "$SCRIPT_DIR/icons/hicolor" ]]; then
  cp -r "$SCRIPT_DIR/icons/hicolor" "$ICON_DIR/"
  find "$ICON_DIR/hicolor" -type f -exec chmod 0644 {} +
  find "$ICON_DIR/hicolor" -type d -exec chmod 0755 {} +
fi

# Update icon cache if tools exist and not in DESTDIR mode
if [[ -z "$DESTDIR" ]]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_DIR/hicolor" >/dev/null 2>&1 || true
  fi
fi

echo "  ok Installed desktop entry at: $DESKTOP_TARGET"
echo "  ok Installed icons under: $ICON_DIR/hicolor"
