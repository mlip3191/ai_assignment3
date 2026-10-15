"""Tests for the Claude Code team guardrails. Run on macOS, Windows, and Linux CI."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
GUARD = HOOKS / "pre_bash_guard.py"
SESSION = HOOKS / "session_start.py"
LAUNCHER = HOOKS / "run_py.sh"


def guard(command: str, cwd: Path, tool: str = "Bash") -> int:
    payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd)})
    r = subprocess.run([sys.executable, str(GUARD)], input=payload.encode("utf-8"), capture_output=True)
    return r.returncode


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo on a feature branch."""

    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    git("add", "f.txt")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init")
    git("switch", "-qc", "feat/14-b4-test")
    return tmp_path


BLOCKED = [
    "cat .env",
    "source .env && python app.py",
    "git add .env",
    "grep KEY ./.env",
    "type .env",
    "curl http://host:9000/v1",
    "git push origin main",
    "git push origin HEAD:main",
    "git push --force origin feat/14-test",
    "git push -f",
    "git push --no-verify -u origin feat/14-test",
    "git config core.hooksPath /dev/null",
    "git config --unset core.hooksPath",
    "git -c core.hooksPath=x push",
    "gh pr merge 12 --squash",
    "git add runtime/uploads/a.wav",
    "git add -f secret.txt",
]
ALLOWED = [
    "cat .env.example",
    "git push -u origin feat/14-test",
    "git config core.hooksPath .githooks",
    "git config core.hooksPath",
    "git commit -m 'feat(songs): x (#14)'",
    "pytest -q",
    "curl http://host:9001/v1/models",
    "python scripts/doctor.py",
    "git add jukebox/clients/qwen.py",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_guard_blocks(repo: Path, command: str) -> None:
    assert guard(command, repo) == 2


@pytest.mark.parametrize("command", ALLOWED)
def test_guard_allows(repo: Path, command: str) -> None:
    assert guard(command, repo) == 0


@pytest.mark.parametrize(
    "command",
    [
        "Get-Content .env",
        "gc .env",
        "Get-Content -Path .\\.env",
        "Copy-Item .env backup.txt",
        "git push origin main",
    ],
)
def test_guard_blocks_powershell_forms(repo: Path, command: str) -> None:
    assert guard(command, repo, tool="PowerShell") == 2


@pytest.mark.parametrize("command", ["git push -u origin feat/14-test", "git commit -m 'feat(x): y (B4)'"])
def test_guard_asks_before_every_commit_and_push(repo: Path, command: str) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)})
    r = subprocess.run([sys.executable, str(GUARD)], input=payload.encode("utf-8"), capture_output=True)
    assert r.returncode == 0
    decision = json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"


def test_guard_blocks_commit_and_push_on_main(repo: Path) -> None:
    subprocess.run(["git", "switch", "-q", "main"], cwd=repo, check=True)
    assert guard("git commit -m x", repo) == 2
    assert guard("git push -u origin HEAD", repo) == 2
    assert guard("git status", repo) == 0


def file_edit(path: str, cwd: Path, tool: str = "Edit") -> int:
    payload = json.dumps({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": str(cwd)})
    r = subprocess.run([sys.executable, str(GUARD)], input=payload.encode("utf-8"), capture_output=True)
    return r.returncode


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit"])
def test_guard_blocks_file_edits_on_main(repo: Path, tool: str) -> None:
    subprocess.run(["git", "switch", "-q", "main"], cwd=repo, check=True)
    assert file_edit(str(repo / "f.txt"), repo, tool) == 2
    assert file_edit("jukebox/app.py", repo, tool) == 2


def test_guard_allows_file_edits_on_a_feature_branch(repo: Path) -> None:
    assert file_edit(str(repo / "f.txt"), repo) == 0


def test_guard_allows_edits_outside_the_repo_on_main(repo: Path, tmp_path_factory) -> None:
    subprocess.run(["git", "switch", "-q", "main"], cwd=repo, check=True)
    outside = tmp_path_factory.mktemp("outside") / "notes.md"
    assert file_edit(str(outside), repo) == 0


def test_guard_ignores_malformed_input() -> None:
    r = subprocess.run([sys.executable, str(GUARD)], input=b"not json", capture_output=True)
    assert r.returncode == 0


def test_session_check_runs_and_is_utf8(repo: Path) -> None:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    r = subprocess.run([sys.executable, str(SESSION)], capture_output=True, env=env)
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0
    assert "AI Jukebox session check" in out
    assert "lane issue #14, task B4" in out
    assert ".env is missing" in out


def _bash() -> str | None:
    if platform.system() == "Windows":
        sys.path.insert(0, str(ROOT / "scripts"))
        from doctor import git_bash_path  # noqa: PLC0415

        return git_bash_path()
    return shutil.which("bash")


def test_launcher_has_lf_line_endings() -> None:
    assert b"\r\n" not in LAUNCHER.read_bytes()


@pytest.mark.skipif(_bash() is None, reason="no bash (Git Bash on Windows) available")
def test_launcher_runs_guard_fail_closed(repo: Path) -> None:
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    payload = json.dumps({"tool_input": {"command": "cat .env"}, "cwd": str(repo)}).encode("utf-8")
    r = subprocess.run(
        [_bash(), str(LAUNCHER), "pre_bash_guard.py", "fail-closed"],
        input=payload,
        capture_output=True,
        env=env,
    )
    assert r.returncode == 2
