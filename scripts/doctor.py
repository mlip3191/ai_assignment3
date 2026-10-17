#!/usr/bin/env python3
"""Check that this machine is ready to work on AI Jukebox. Same script on macOS and Windows.

  macOS:    python scripts/doctor.py     (venv active)   or   python3 scripts/doctor.py
  Windows:  python scripts\\doctor.py    (venv active)   or   py scripts\\doctor.py

Prints PASS / WARN / FAIL for each check with the fix for YOUR operating system.
Exit code 1 if anything FAILs. Standard library only. Never reads .env contents.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
HOOK = ".githooks/pre-push"
GATE = "Pre-push quality gate"

results: list[tuple[str, str, str, str]] = []  # (status, check, detail, fix)


def add(status: str, check: str, detail: str = "", fix: str = "") -> None:
    results.append((status, check, detail, fix))


def fix_for(mac: str, win: str) -> str:
    return win if IS_WINDOWS else mac


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **kw
    )


def check_python() -> None:
    v = sys.version_info
    ok = v >= (3, 11)
    add(
        "PASS" if ok else "FAIL",
        "Python 3.11+",
        f"{platform.python_version()} ({sys.executable})",
        "" if ok else fix_for("brew install python@3.12", "winget install Python.Python.3.12"),
    )


def check_venv() -> None:
    if not VENV_PY.exists():
        add(
            "FAIL",
            "Project virtual environment (.venv)",
            "missing",
            fix_for("python3 scripts/setup_dev.py", "py scripts\\setup_dev.py"),
        )
        return
    r = run([str(VENV_PY), "-c", "import pytest, respx, ruff; print('ok')"])
    if r.returncode == 0:
        add("PASS", "Project virtual environment (.venv)", "dev tools installed")
    else:
        add(
            "FAIL",
            "Project virtual environment (.venv)",
            "dev tools missing",
            fix_for("python3 scripts/setup_dev.py", "py scripts\\setup_dev.py"),
        )
    active = os.environ.get("VIRTUAL_ENV")
    if active and Path(active).resolve() == VENV.resolve():
        add("PASS", "venv active in this terminal")
    else:
        add(
            "WARN",
            "venv active in this terminal",
            "not active (fine during setup; required before starting `claude`)",
            fix_for(
                "source .venv/bin/activate",
                ".venv\\Scripts\\Activate.ps1 (PowerShell) or .venv\\Scripts\\activate.bat (cmd)",
            ),
        )


def check_git() -> None:
    if not shutil.which("git"):
        add("FAIL", "git", "not found", fix_for("xcode-select --install", "winget install Git.Git"))
        return
    add("PASS", "git", run(["git", "--version"]).stdout.strip())
    name = run(["git", "config", "user.name"]).stdout.strip()
    email = run(["git", "config", "user.email"]).stdout.strip()
    if name and email:
        add("PASS", "git identity", f"{name} <{email}>")
    else:
        add(
            "FAIL",
            "git identity",
            "user.name / user.email not set (your commits won't count as yours)",
            'git config --global user.name "Your Name"  &&  git config --global user.email "you@example.com"',
        )
    if run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT).returncode != 0:
        add(
            "FAIL",
            "Inside a git clone",
            "this folder is not a git repository",
            "Clone the team repo with `gh repo clone OWNER/ai-jukebox`",
        )
        return
    check_hook(ROOT)


def hook_index_mode(root: Path) -> str | None:
    """The file mode git has stored for the pre-push hook (e.g. '100755'), or None if it isn't tracked."""
    out = run(["git", "ls-files", "-s", HOOK], cwd=root).stdout.split()
    return out[0] if out else None


def hook_problem(index_mode: str | None, runnable_on_disk: bool, check_disk: bool) -> tuple[str, str] | None:
    """Why git would skip the pre-push hook, as (detail, fix), or None when it will run.

    git ignores a hook that is not executable. Git for Windows ignores the bit, so there the committed
    mode is the only reliable signal; on macOS and Linux the checked-out file has to be executable too.
    """
    if index_mode is None:
        return f"{HOOK} is not tracked by git", "git pull origin main"
    if index_mode != "100755":
        return (
            f"{HOOK} is committed as mode {index_mode}, not 100755, so git skips it and no checks run",
            f"Ask the release lead to run `git update-index --chmod=+x {HOOK}` and commit it",
        )
    if check_disk and not runnable_on_disk:
        return f"{HOOK} is not executable on disk, so git skips it and no checks run", f"chmod +x {HOOK}"
    return None


def check_hook(root: Path) -> None:
    hooks = run(["git", "config", "core.hooksPath"], cwd=root).stdout.strip()
    if hooks != ".githooks":
        add(
            "FAIL",
            GATE,
            "team git hooks are off, so pushes skip the checks",
            "git config core.hooksPath .githooks",
        )
        return
    problem = hook_problem(hook_index_mode(root), os.access(root / HOOK, os.X_OK), not IS_WINDOWS)
    if problem:
        add("FAIL", GATE, *problem)
    else:
        add("PASS", GATE, "git runs scripts/prepush.py before every push")


def git_bash_path() -> str | None:
    """Git Bash on Windows (not the WSL bash.exe in System32)."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env and Path(env).exists():
        return env
    git = shutil.which("git")
    candidates = []
    if git:
        g = Path(git).resolve()
        for parent in list(g.parents)[:3]:
            candidates.append(parent / "bin" / "bash.exe")
    candidates += [
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Git" / "bin" / "bash.exe")
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def check_bash_and_hooks() -> None:
    bash = git_bash_path() if IS_WINDOWS else shutil.which("bash")
    if not bash:
        add(
            "FAIL",
            "Bash for Claude Code hooks",
            "Git Bash not found" if IS_WINDOWS else "bash not found",
            fix_for(
                "bash ships with macOS; check your PATH",
                "Install Git for Windows (winget install Git.Git). If it's installed somewhere unusual, set "
                'CLAUDE_CODE_GIT_BASH_PATH to its bin\\bash.exe in ".claude/settings.local.json" under "env".',
            ),
        )
        return
    add("PASS", "Bash for Claude Code hooks", bash)

    launcher = ROOT / ".claude" / "hooks" / "run_py.sh"
    if b"\r\n" in launcher.read_bytes():
        add(
            "FAIL",
            "Hook launcher line endings",
            "run_py.sh has Windows (CRLF) line endings, so bash can't run it",
            "Delete .claude/hooks/run_py.sh, then run: git checkout -- .claude/hooks/run_py.sh "
            "(re-creates it with LF endings per .gitattributes)",
        )
        return

    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    r = run([bash, str(launcher), "session_start.py"], cwd=ROOT, env=env)
    if "AI Jukebox session check" in r.stdout and "no working Python" not in r.stdout:
        add("PASS", "Session-check hook runs")
    else:
        add(
            "FAIL",
            "Session-check hook runs",
            (r.stdout + r.stderr).strip()[:200],
            fix_for(
                "Make sure `python3 --version` works in Terminal",
                "Make sure `py --version` or `python --version` works in Git Bash; see PROJECT.md 16.9",
            ),
        )

    payload = json.dumps({"tool_input": {"command": "cat .env"}, "cwd": str(ROOT)})
    g = subprocess.run(
        [bash, str(launcher), "pre_bash_guard.py", "fail-closed"],
        input=payload.encode("utf-8"),
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=60,
    )
    if g.returncode == 2 and b"Blocked by team guardrail" in g.stderr:
        add("PASS", "Command guard blocks `cat .env`")
    else:
        add(
            "FAIL",
            "Command guard blocks `cat .env`",
            f"exit {g.returncode}: {g.stderr.decode('utf-8', 'replace').strip()[:200]}",
            "Fix the Python/Git Bash items above, then re-run this check. Tell the release lead if it persists.",
        )


def check_gh() -> None:
    if not shutil.which("gh"):
        add("FAIL", "GitHub CLI (gh)", "not found", fix_for("brew install gh", "winget install GitHub.cli"))
        return
    r = run(["gh", "auth", "status"])
    if r.returncode == 0:
        add("PASS", "GitHub CLI logged in")
    else:
        add("FAIL", "GitHub CLI logged in", "not logged in", "gh auth login   (GitHub.com, HTTPS, browser)")


def check_claude() -> None:
    exe = shutil.which("claude")
    if not exe:
        add(
            "FAIL",
            "Claude Code",
            "`claude` not found",
            fix_for(
                "curl -fsSL https://claude.ai/install.sh | bash   (then open a new terminal)",
                "irm https://claude.ai/install.ps1 | iex   (in PowerShell; then open a new terminal)",
            ),
        )
        return
    v = run([exe, "--version"]).stdout.strip()
    add("PASS", "Claude Code", v or exe)


def check_env_file() -> None:
    env = ROOT / ".env"
    if env.exists():
        add("PASS", ".env present", "contents not read")
    else:
        add(
            "FAIL",
            ".env present",
            "missing",
            fix_for("cp .env.example .env   then fill it in", "copy .env.example .env   then fill it in"),
        )
    tracked = run(["git", "ls-files", "--", ".env", "runtime"], cwd=ROOT).stdout.strip()
    if tracked:
        add("FAIL", "Secrets not tracked by git", tracked, "Tell the release lead immediately; do not push.")
    else:
        add("PASS", "Secrets not tracked by git")


def check_location() -> None:
    p = str(ROOT)
    synced = ("OneDrive" in p) if IS_WINDOWS else ("Mobile Documents" in p or "CloudStorage" in p)
    if synced:
        add(
            "WARN",
            "Project folder location",
            f"{p} is inside a cloud-synced folder; syncing can lock or corrupt .venv and git files",
            fix_for("Move the clone to ~/dev/ai-jukebox", "Move the clone to C:\\dev\\ai-jukebox"),
        )
    elif IS_WINDOWS and len(p) > 80:
        add(
            "WARN",
            "Project folder location",
            f"path is {len(p)} characters; long paths can break pip installs on Windows",
            "Move the clone to a short path such as C:\\dev\\ai-jukebox",
        )
    else:
        add("PASS", "Project folder location", p)


def check_windows_extras() -> None:
    if not IS_WINDOWS:
        return
    stub = shutil.which("python3")
    if stub and "WindowsApps" in stub:
        add(
            "WARN",
            "Microsoft Store python3 alias",
            stub,
            "Settings > Apps > Advanced app settings > App execution aliases: turn off python.exe and python3.exe",
        )
    if shutil.which("powershell"):
        r = run(["powershell", "-NoProfile", "-Command", "Get-ExecutionPolicy"])
        policy = r.stdout.strip()
        if policy in ("Restricted", "AllSigned", "Undefined"):
            add(
                "WARN",
                "PowerShell can run Activate.ps1",
                f"execution policy is {policy}",
                "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned   "
                "(or activate with .venv\\Scripts\\activate.bat in Command Prompt)",
            )
        elif policy:
            add("PASS", "PowerShell can run Activate.ps1", f"execution policy {policy}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os_name = "Windows" if IS_WINDOWS else ("macOS" if IS_MAC else platform.system())
    print(f"AI Jukebox doctor: {os_name} {platform.release()} ({platform.machine()})\n")

    for check in (
        check_python,
        check_venv,
        check_git,
        check_gh,
        check_claude,
        check_bash_and_hooks,
        check_env_file,
        check_location,
        check_windows_extras,
    ):
        try:
            check()
        except Exception as exc:  # a broken check shouldn't hide the others
            add("WARN", check.__name__, f"check crashed: {exc}")

    width = max(len(c) for _, c, _, _ in results)
    for status, check, detail, fix in results:
        print(f"[{status}] {check.ljust(width)}  {detail}")
        if fix and status != "PASS":
            print(f"        fix: {fix}")
    fails = sum(1 for s, *_ in results if s == "FAIL")
    warns = sum(1 for s, *_ in results if s == "WARN")
    print(
        f"\n{fails} fail(s), {warns} warning(s).",
        "Ready to work." if not fails else "Fix the FAIL items first.",
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
