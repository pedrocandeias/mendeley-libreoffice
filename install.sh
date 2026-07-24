#!/usr/bin/env bash
# Build and install the Mendeley Cite extension into LibreOffice.
# Detects native, snap, and flatpak LibreOffice installations.
#
# Usage:
#   ./install.sh              build and install
#   ./install.sh --uninstall  remove the extension
set -euo pipefail
cd "$(dirname "$0")"

EXT_ID="org.mendeley.libreoffice"
OXT="dist/mendeley-libreoffice.oxt"

# Find a way to run unopkg, preferring native > snap > flatpak.
run_unopkg() {
  if command -v unopkg >/dev/null 2>&1; then
    unopkg "$@"
  elif command -v snap >/dev/null 2>&1 && snap list libreoffice >/dev/null 2>&1; then
    # The snap doesn't expose unopkg; run it inside the snap's confinement
    # so the extension lands in the snap's user profile.
    printf '"$SNAP"/lib/libreoffice/program/unopkg %s\n' "$*" | snap run --shell libreoffice.writer
  elif command -v flatpak >/dev/null 2>&1 && flatpak info org.libreoffice.LibreOffice >/dev/null 2>&1; then
    flatpak run --command=/app/libreoffice/program/unopkg org.libreoffice.LibreOffice "$@"
  else
    echo "Error: no LibreOffice installation found (looked for unopkg, snap, flatpak)." >&2
    echo "Install manually via LibreOffice > Tools > Extensions > Add... using $OXT" >&2
    exit 1
  fi
}

if pgrep -x soffice.bin >/dev/null 2>&1; then
  echo "LibreOffice is running. Close it first, then re-run this script." >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  run_unopkg remove "$EXT_ID"
  echo "Uninstalled $EXT_ID."
  exit 0
fi

bash build.sh
run_unopkg add --force "$(pwd)/$OXT"
echo
echo "Installed. Open LibreOffice Writer — the Mendeley menu/toolbar should appear."
