#!/usr/bin/env python3
"""The team quality gate, run automatically by git before every push (.githooks/pre-push).

It runs the same checks as the /check skill and CI, so nothing reaches GitHub that the
team's tools haven't checked. Same script on macOS and Windows; uses the project .venv.

  python scripts/prepush.py     # run it by hand any time

Checks: every code change comes with test changes, ruff lint, ruff format, secret scan,
class-models-only check, config check (once it exists), and the FULL pytest suite, so new
work is always run against every existing test case. Exit code 1 blocks the push.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# Changes here are code and must come with test changes in tests/.
CODE_PREFIXES = ("jukebox/", "scripts/", ".claude/hooks/", ".githooks/")
CODE_FILES = ("app.py",)

CHECKS = [
    ("Commits written by the pusher", [PY, "scripts/check_authors.py"]),
    ("Lint (ruff check)", [PY, "-m", "ruff", "check", "."]),
    ("Format (ruff format --check)", [PY, "-m", "ruff", "format", "--check", "."]),
    ("Secret scan", [PY, "scripts/scan_secrets.py"]),
    ("Only the four class models", [PY, "scripts/check_models.py"]),
    ("Config check", [PY, "scripts/check_config.py"]),
    ("All test cases (full pytest suite)", [PY, "-P", "-m", "pytest", "-q"]),
]


def needs_tests(changed: list[str]) -> list[str]:
    """Code files changed without any change under tests/. Empty list = OK."""
    if any(f.startswith("tests/") for f in changed):
        return []
    return [f for f in changed if f.startswith(CODE_PREFIXES) or f in CODE_FILES]


def changed_files() -> list[str] | None:
    """Files that differ from origin/main, or None if there's no origin/main to compare with yet."""
    base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"], cwd=ROOT, capture_output=True, text=True
    )
    if base.returncode != 0:
        return None
    r = subprocess.run(
        ["git", "diff", "--name-only", base.stdout.strip()], cwd=ROOT, capture_output=True, text=True
    )
    return [line for line in r.stdout.splitlines() if line]


def check_tests_added() -> bool:
    changed = changed_files()
    if changed is None:
        print("[SKIP] Code changes have test cases: no origin/main to compare with yet", flush=True)
        return True
    missing = needs_tests(changed)
    if not missing:
        print("[PASS] Code changes have test cases", flush=True)
        return True
    print("[FAIL] Code changes have test cases", flush=True)
    print("       These changed without any new or updated test in tests/:", flush=True)
    for f in missing:
        print(f"         - {f}", flush=True)
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("AI Jukebox pre-push gate (same checks as /check and CI)\n", flush=True)

    failed = [] if check_tests_added() else ["Code changes have test cases"]
    for name, cmd in CHECKS:
        if cmd[1].startswith("scripts/") and not (ROOT / cmd[1]).exists():
            print(f"[SKIP] {name}: {cmd[1]} doesn't exist yet", flush=True)
            continue
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if "pytest" in name and r.returncode == 5:
            print(f"[WARN] {name}: no tests collected yet", flush=True)
            continue
        if r.returncode == 0:
            print(f"[PASS] {name}", flush=True)
        else:
            failed.append(name)
            print(f"[FAIL] {name}", flush=True)
            tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
            for line in tail:
                print(f"       {line}", flush=True)

    if failed:
        print(
            f"\nPush blocked: {len(failed)} check(s) failed. Fix them (in Claude Code: run /check), "
            "commit, and push again.",
            flush=True,
        )
        return 1
    print("\nAll checks passed. Pushing.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
