#!/bin/bash
# Artbench from its source code on a Mac: double-click this file. It needs Python 3.11 or newer
# (python.org/downloads, or Homebrew: brew install python). The first time, macOS may say it is from an
# unidentified developer: right-click it, choose Open, then Open again.
cd "$(dirname "$0")" || exit 1
for py in python3.13 python3.12 python3.11 python3; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    exec "$py" -m artbench --app
  fi
done
echo
echo "  Artbench needs Python 3.11 or newer, and this Mac does not have it."
echo "  Install it from https://www.python.org/downloads/ (or: brew install python), then open this file again."
echo
read -r -p "Press Return to close."
