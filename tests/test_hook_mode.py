"""Tests for A11: the pre-push hook must be executable in git, and doctor/setup must catch and fix it.

git skips a hook that is not executable ("hook was ignored because it's not set as executable"), so the
whole pre-push gate is silently off. Git for Windows ignores the bit, so doctor reads the mode git stores
in the index instead of trusting the file on disk. Runs on macOS, Windows and Linux CI.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ".githooks/pre-push"
POSIX = platform.system() != "Windows"
GATE = "Pre-push quality gate"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


doctor = load("doctor")
setup_dev = load("setup_dev")


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")
    return r.stdout


def make_executable(repo: Path) -> None:
    """Mark the hook executable the way A11 does: in the git index, and on disk where that matters."""
    git(repo, "update-index", "--chmod=+x", HOOK)
    if POSIX:
        (repo / HOOK).chmod(0o755)


@pytest.fixture
def hook_repo(tmp_path: Path) -> Path:
    """A throwaway repo with the hook committed as mode 100644 and the team hooks path switched on."""
    git(tmp_path, "init", "-q", "-b", "main")
    hook = tmp_path / ".githooks" / "pre-push"
    hook.parent.mkdir()
    hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n")
    git(tmp_path, "add", HOOK)
    git(
        tmp_path,
        "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false",
        "commit", "-qm", "init",
    )  # fmt: skip
    git(tmp_path, "config", "core.hooksPath", ".githooks")
    return tmp_path


def gate_results() -> list[tuple[str, str, str, str]]:
    return [r for r in doctor.results if r[1] == GATE]


# --- the real hook in this repo ------------------------------------------------------------------


def test_committed_pre_push_hook_is_executable() -> None:
    r = subprocess.run(["git", "ls-files", "-s", HOOK], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        pytest.skip("not a git checkout (for example a downloaded ZIP)")
    assert r.stdout.split()[0] == "100755", "run: git update-index --chmod=+x .githooks/pre-push"


def test_hook_runs_the_prepush_gate() -> None:
    text = (ROOT / HOOK).read_bytes()
    assert text.startswith(b"#!/usr/bin/env bash")
    assert b"scripts/prepush.py" in text
    assert b"\r" not in text  # CRLF would break the shebang on macOS and Linux


# --- hook_problem: the pure decision --------------------------------------------------------------


def test_hook_problem_flags_non_executable_index_mode() -> None:
    detail, fix = doctor.hook_problem("100644", True, True)
    assert "100755" in detail
    assert "git update-index --chmod=+x .githooks/pre-push" in fix


def test_hook_problem_flags_untracked_hook() -> None:
    problem = doctor.hook_problem(None, True, True)
    assert problem is not None
    assert "not tracked" in problem[0]


def test_hook_problem_checks_the_file_on_disk_only_when_asked() -> None:
    detail, fix = doctor.hook_problem("100755", False, True)  # POSIX: file not executable
    assert "not executable" in detail
    assert "chmod +x .githooks/pre-push" in fix
    assert doctor.hook_problem("100755", False, False) is None  # Windows: the bit means nothing there


def test_hook_problem_ok_when_executable() -> None:
    assert doctor.hook_problem("100755", True, True) is None


# --- doctor against a real (temporary) git repo --------------------------------------------------


def test_hook_index_mode_reads_real_git(hook_repo: Path) -> None:
    assert doctor.hook_index_mode(hook_repo) == "100644"
    make_executable(hook_repo)
    assert doctor.hook_index_mode(hook_repo) == "100755"


def test_check_hook_fails_when_not_executable(hook_repo: Path) -> None:
    doctor.results.clear()
    doctor.check_hook(hook_repo)
    [(status, _, detail, fix)] = gate_results()
    assert status == "FAIL"
    assert "100644" in detail
    assert "git update-index --chmod=+x" in fix


def test_check_hook_passes_when_executable(hook_repo: Path) -> None:
    make_executable(hook_repo)
    doctor.results.clear()
    doctor.check_hook(hook_repo)
    [(status, *_)] = gate_results()
    assert status == "PASS"


@pytest.mark.skipif(not POSIX, reason="the execute bit on disk only matters on macOS and Linux")
def test_check_hook_fails_when_file_on_disk_is_not_executable(hook_repo: Path) -> None:
    git(hook_repo, "update-index", "--chmod=+x", HOOK)  # index says 100755 ...
    (hook_repo / HOOK).chmod(0o644)  # ... but the checked-out file is not executable
    doctor.results.clear()
    doctor.check_hook(hook_repo)
    [(status, _, _, fix)] = gate_results()
    assert status == "FAIL"
    assert "chmod +x .githooks/pre-push" in fix


def test_check_hook_fails_when_hooks_path_unset(hook_repo: Path) -> None:
    git(hook_repo, "config", "--unset", "core.hooksPath")
    make_executable(hook_repo)
    doctor.results.clear()
    doctor.check_hook(hook_repo)
    [(status, _, _, fix)] = gate_results()
    assert status == "FAIL"
    assert fix == "git config core.hooksPath .githooks"


# --- setup_dev ----------------------------------------------------------------------------------


@pytest.mark.skipif(not POSIX, reason="execute bits are a macOS and Linux concept")
def test_setup_dev_makes_hook_executable(tmp_path: Path) -> None:
    hook = tmp_path / "pre-push"
    hook.write_text("#!/usr/bin/env bash\n", encoding="utf-8", newline="\n")
    hook.chmod(0o644)
    assert setup_dev.ensure_hook_executable(hook) is True
    assert os.access(hook, os.X_OK)
    mode = hook.stat().st_mode
    assert setup_dev.ensure_hook_executable(hook) is True  # already executable: left alone
    assert hook.stat().st_mode == mode
    assert setup_dev.ensure_hook_executable(tmp_path / "missing") is False  # no crash
