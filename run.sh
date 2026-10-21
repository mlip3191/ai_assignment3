#!/usr/bin/env bash
# AI Jukebox launcher for macOS (PROJECT.md section 0.4). Start it with: bash run.sh
# (or type "bash ", drag run.sh into Terminal, and press Enter).
# It finds Python 3.11+, makes the .venv folder, then hands off to scripts/launcher.py,
# which does the rest the same way as run.bat on Windows.
set -u
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.11 or newer was not found."
  echo "Install Python 3.12 from python.org/downloads (the macOS .pkg installer),"
  echo "then open a new Terminal window and run: bash run.sh"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Setting up the app's Python environment in the .venv folder, one time only..."
  if ! "$PY" -m venv .venv; then
    echo "Couldn't create the .venv folder. Make sure the app folder isn't inside iCloud Drive"
    echo "and that you can write to it, then try again."
    exit 1
  fi
fi

exec ".venv/bin/python" scripts/launcher.py "$@"
