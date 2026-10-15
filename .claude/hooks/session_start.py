#!/usr/bin/env python3
"""SessionStart hook: prints a session check block that Claude Code adds to its context.

Runs on startup, resume, /clear, and compaction. It never fails the session: any
error is reported as a warning and the script exits 0.

It does NOT read the contents of .env. It only checks whether the file exists and
whether git is tracking it.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
IS_WINDOWS = platform.system() == "Windows"

# OS-specific commands to show in warnings (PROJECT.md section 16.8)
if IS_WINDOWS:
    OS_NAME = "Windows"
    SETUP = "py scripts\\setup_dev.py"
    ACTIVATE = ".venv\\Scripts\\Activate.ps1  (PowerShell)"
    COPY_ENV = "copy .env.example .env"
else:
    OS_NAME = "macOS" if platform.system() == "Darwin" else platform.system()
    SETUP = "python3 scripts/setup_dev.py"
    ACTIVATE = "source .venv/bin/activate"
    COPY_ENV = "cp .env.example .env"

# Hook output is piped, so Windows would default to a legacy code page; force UTF-8.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def git(*args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return out.returncode, out.stdout.strip()
    except Exception as exc:  # git missing, timeout, etc.
        return 1, str(exc)


def main() -> None:
    lines: list[str] = []
    warnings: list[str] = []

    code, _ = git("rev-parse", "--is-inside-work-tree")
    if code != 0:
        print("=== AI Jukebox session check ===")
        print(
            "WARNING: this folder is not a git repository. Clone the team repo instead of working in a copy."
        )
        return

    _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    issue = task = None
    m = re.match(r"^(?:feat|fix|docs|test|chore|spike)/(\d+)-(?:([a-eA-E]\d{1,2})(?:-|$))?", branch)
    if m:
        issue, task = m.group(1), (m.group(2) or "").upper() or None
    where = ""
    if issue:
        where = f" (lane issue #{issue}" + (f", task {task}" if task else "") + ")"
    lines.append(f"Branch: {branch}{where}")

    if branch in ("main", "master"):
        warnings.append(
            "You are on main. Do not edit files here. Run /start-session <task key> (e.g. B4) to create a branch."
        )
    elif not issue:
        warnings.append(
            f"Branch '{branch}' does not follow <type>/<lane#>-<task>-<desc>. "
            "Skills can't find the lane issue and task automatically."
        )
    elif not task:
        warnings.append(
            "Branch name has no task key (e.g. feat/2-b4-acestep-client), so the PR can't be tied to a task."
        )

    _, porcelain = git("status", "--porcelain=v2", "--branch")
    changed = [ln for ln in porcelain.splitlines() if ln and not ln.startswith("#")]
    lines.append(f"Working tree: {'clean' if not changed else f'{len(changed)} changed/untracked file(s)'}")
    ab = re.search(r"^# branch\.ab \+(\d+) -(\d+)", porcelain, re.M)
    if ab:
        lines.append(f"Vs. upstream: {ab.group(1)} ahead, {ab.group(2)} behind")

    # How stale is our view of origin?
    fetch_head = ROOT / ".git" / "FETCH_HEAD"
    if fetch_head.exists():
        hours = (time.time() - fetch_head.stat().st_mtime) / 3600
        lines.append(f"Last fetch from GitHub: {hours:.1f} h ago")
        if hours > 12:
            warnings.append("Your copy of GitHub is over 12 h old. /start-session will fetch and update.")
    else:
        warnings.append("This clone has never fetched from GitHub. Run /start-session to sync.")

    code, behind = git("rev-list", "--count", f"{branch}..origin/main")
    if code == 0 and behind.isdigit() and int(behind) > 0 and branch != "main":
        warnings.append(
            f"origin/main has {behind} commit(s) your branch doesn't. Pull main into your branch before building."
        )

    # Secrets and credentials (existence checks only; never read .env).
    if not (ROOT / ".env").exists():
        warnings.append(
            f".env is missing. The human must run `{COPY_ENV}` in their own terminal and fill it from "
            "class-endpoints.txt. Claude must not create, read, or edit .env."
        )
    code, tracked = git("ls-files", "--", ".env", "runtime")
    if tracked:
        warnings.append(
            f"STOP: git is tracking files that must never be committed: {tracked.splitlines()}. Tell the release lead."
        )

    # Local environment
    venv = ROOT / ".venv"
    req = ROOT / "requirements.txt"
    if not venv.exists():
        warnings.append(
            f"No .venv folder. Quit Claude Code, run `{SETUP}`, then `{ACTIVATE}`, then start `claude` again."
        )
    else:
        if req.exists() and req.stat().st_mtime > venv.stat().st_mtime:
            warnings.append(
                f"requirements.txt changed since .venv was last set up. Re-run `{SETUP}` in your terminal."
            )
        active = os.environ.get("VIRTUAL_ENV", "")
        if not active or Path(active).resolve() != venv.resolve():
            warnings.append(
                "The project's virtual environment is not active, so `python`, `pytest`, and `ruff` may be "
                f"missing or wrong. Quit Claude Code, run `{ACTIVATE}` in this folder, then start `claude` again."
            )

    # Only the four class models (PROJECT.md section 7.0)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from check_models import scan  # noqa: PLC0415

        problems = scan(ROOT)
        if problems:
            warnings.append(
                f"Model check FAILS ({len(problems)} problem(s)): the code could use something other than the four "
                f"class models. First: {problems[0]}. Run `python scripts/check_models.py` for the full list."
            )
    except Exception as exc:  # never break startup
        warnings.append(f"Couldn't run the model check: {exc}")

    # Stray audio outside samples/ (voice references must never be committed)
    _, untracked = git("ls-files", "--others", "--exclude-standard")
    stray = [
        p
        for p in untracked.splitlines()
        if Path(p).suffix.lower() in AUDIO_EXT and not p.startswith("samples/")
    ]
    if stray:
        warnings.append(
            f"Untracked audio outside samples/: {stray[:5]}. Never commit voice references or uploads."
        )

    print("=== AI Jukebox session check ===")
    for ln in lines:
        print(ln)
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"- {w}")
    else:
        print("No warnings.")
    print(
        "INSTRUCTION TO CLAUDE: Before doing anything else in this session, show the user the branch, "
        "issue, and every warning above. If the user has not run /start-session in this session, "
        "suggest it before editing any files."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break session startup
        print(f"=== AI Jukebox session check ===\nWARNING: session check failed to run: {exc}")
    sys.exit(0)
