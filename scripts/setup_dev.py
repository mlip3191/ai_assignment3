#!/usr/bin/env python3
"""One-time (and after-pull) developer setup. Same script on macOS and Windows.

  macOS:    python3 scripts/setup_dev.py
  Windows:  py scripts\\setup_dev.py          (PowerShell or Command Prompt)

What it does:
  1. Checks you're running Python 3.11+
  2. Creates .venv if missing (with this same Python)
  3. Installs requirements-dev.txt and requirements.txt (if present) into .venv
  4. Creates .env from .env.example if you don't have one yet (you then fill it in)
  5. Turns on the team git hooks (.githooks/pre-push runs the quality gate before every push)
  6. Runs scripts/doctor.py to check git, gh, Claude Code, hooks, and more

Safe to re-run any time, e.g. after someone changes requirements.txt.
Uses only the standard library, so it works before anything is installed.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = platform.system() == "Windows"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
MIN = (3, 11)
HOOK = ROOT / ".githooks" / "pre-push"


def say(msg: str) -> None:
    print(msg, flush=True)


def ensure_hook_executable(hook: Path = HOOK) -> bool:
    """Make sure git will run the pre-push hook. True if it is (now) runnable, False if it is missing
    or cannot be made executable.

    git silently skips a hook that is not executable. Windows has no execute bit, so nothing to do there.
    """
    if not hook.exists():
        return False
    if not IS_WINDOWS and not os.access(hook, os.X_OK):
        try:
            hook.chmod(hook.stat().st_mode | 0o111)
        except OSError:
            return False
    return True


def run(cmd: list[str]) -> None:
    say("  $ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    say(f"AI Jukebox developer setup ({platform.system()} {platform.machine()})\n")

    # 1. Python version
    if sys.version_info < MIN:
        say(f"Python {platform.python_version()} is too old; 3.11 or newer is required.")
        if IS_WINDOWS:
            say("Install it:  winget install Python.Python.3.12   then run:  py -3.12 scripts\\setup_dev.py")
        else:
            say("Install it:  brew install python@3.12   then run:  python3.12 scripts/setup_dev.py")
        return 1
    say(f"[1/6] Python {platform.python_version()} at {sys.executable}  OK")

    # 2. Virtual environment
    if VENV.exists() and not VENV_PY.exists():
        say(f"[2/6] .venv exists but has no {VENV_PY.relative_to(ROOT)}. It was probably made on another OS")
        say("      or by a different Python. Delete the .venv folder and run this script again.")
        return 1
    if not VENV.exists():
        say("[2/6] Creating .venv")
        run([sys.executable, "-m", "venv", ".venv"])
    else:
        say("[2/6] .venv already exists  OK")

    # 3. Dependencies
    say("[3/6] Installing dependencies into .venv")
    run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    run([VENV_PY, "-m", "pip", "install", "-r", "requirements-dev.txt", "--quiet"])
    if (ROOT / "requirements.txt").exists():
        run([VENV_PY, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
    else:
        say("      (requirements.txt doesn't exist yet; only dev tools installed)")
    os.utime(VENV, None)  # lets the session check know the venv is up to date

    # 4. .env (created from the template only; the human fills in real values)
    env, example = ROOT / ".env", ROOT / ".env.example"
    if env.exists():
        say("[4/6] .env exists  OK (not read by this script)")
    else:
        shutil.copyfile(example, env)
        say("[4/6] Created .env from .env.example.")
        say("      NOW open .env in your editor and fill it in from class-endpoints.txt.")

    # 5. Team git hooks: the quality gate runs before every push, from any terminal
    say("[5/6] Turning on the team git hooks (quality gate before every push)")
    run(["git", "config", "core.hooksPath", ".githooks"])
    if ensure_hook_executable():
        say("      .githooks/pre-push is executable  OK")
    else:
        say("      ! .githooks/pre-push is missing or can't be made executable. Run `git pull origin main`")
        say("        (macOS: also `chmod +x .githooks/pre-push`), then run this script again.")

    # 6. Doctor
    say("[6/6] Checking your environment\n")
    code = subprocess.run([str(VENV_PY), str(ROOT / "scripts" / "doctor.py")], cwd=ROOT).returncode

    say("\nNext steps:")
    if IS_WINDOWS:
        say(
            "  .venv\\Scripts\\Activate.ps1      (PowerShell)   or   .venv\\Scripts\\activate.bat   (Command Prompt)"
        )
    else:
        say("  source .venv/bin/activate")
    say("  claude")
    say("  then in Claude Code:  /start-session <your task key, e.g. B1>")
    return code


if __name__ == "__main__":
    sys.exit(main())
