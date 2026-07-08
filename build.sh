#!/usr/bin/env bash
# Build dist/mendeley-libreoffice.oxt from src/.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf dist
mkdir -p dist

# Sanity: byte-compile all Python to catch syntax errors early.
python3 -m compileall -q src/python

(
  cd src
  find . -name '__pycache__' -type d -exec rm -rf {} +
  zip -r -X ../dist/mendeley-libreoffice.oxt . >/dev/null
)

echo "Built dist/mendeley-libreoffice.oxt"
echo "Install:  unopkg add --force dist/mendeley-libreoffice.oxt"
echo "     or:  LibreOffice > Tools > Extensions > Add..."
