#!/usr/bin/env bash
# Launches a team hook script with whatever Python works on this machine.
#   macOS:   python3 (the venv's, if you activated it)
#   Windows: Claude Code runs hooks in Git Bash; the venv provides `python`,
#            otherwise the `py` launcher. Microsoft Store "python3" stubs are skipped.
#
# Usage: bash run_py.sh <script.py> [fail-closed]
#   fail-closed: if no Python is found, exit 2 so the guarded command is BLOCKED
#                (used by the command guard: no Python = no protection = stop).

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HOOK_DIR/$1"

for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    exec "$candidate" "$SCRIPT"
  fi
done

if [ "$2" = "fail-closed" ]; then
  echo "Team guardrail could not run: no working Python 3 on PATH. Every command is blocked until this is fixed. See PROJECT.md section 16.9 (Troubleshooting), then restart Claude Code." >&2
  exit 2
fi

echo "=== AI Jukebox session check ==="
echo "WARNING: no working Python 3 on PATH, so the team hooks cannot run. See PROJECT.md section 16.9 (Troubleshooting)."
exit 0
