"""Tests for the pre-push quality gate (scripts/prepush.py) and the secret scan's .env handling."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


prepush = load("prepush")
scan_secrets = load("scan_secrets")


def test_code_change_without_tests_is_flagged() -> None:
    assert prepush.needs_tests(["jukebox/clients/qwen.py", "README.md"]) == ["jukebox/clients/qwen.py"]


def test_code_change_with_tests_passes() -> None:
    assert prepush.needs_tests(["jukebox/clients/qwen.py", "tests/test_qwen.py"]) == []


def test_docs_only_change_needs_no_tests() -> None:
    assert prepush.needs_tests(["README.md", "PROJECT.md", "docs/TEST_EVIDENCE.md"]) == []


def test_scripts_hooks_and_app_count_as_code() -> None:
    changed = ["scripts/doctor.py", ".claude/hooks/pre_bash_guard.py", ".githooks/pre-push", "app.py"]
    assert prepush.needs_tests(changed) == changed


TESTS_CHECK = "All test cases (full pytest suite)"


def gate_pytest_cmd() -> list[str]:
    return dict(prepush.CHECKS)[TESTS_CHECK]


def test_gate_runs_the_full_test_suite() -> None:
    cmd = gate_pytest_cmd()
    assert cmd[0] == sys.executable
    assert "pytest" in cmd
    assert "-q" in cmd
    assert not any(part.endswith(".py") or "/" in part for part in cmd[1:]), "must run the whole suite"


# ---- the gate runs tests the way CI does (A12) ------------------------------------------------------
#
# CI runs plain `pytest -q`. `python -m pytest` also puts the current directory on sys.path, so a test
# file that imports `jukebox` without any sys.path setup passed the gate and then failed in CI (PR #25).


def clean_env() -> dict[str, str]:
    """The environment with everything that could put the project on sys.path or steer pytest removed."""
    drop = {"PYTHONPATH", "PYTHONSAFEPATH", "PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST", "PYTEST_PLUGINS"}
    return {k: v for k, v in os.environ.items() if k not in drop and not k.startswith("GIT_")}


def run_in(folder: Path, cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=folder, env=clean_env(), capture_output=True, text=True, timeout=120, encoding="utf-8"
    )


@pytest.fixture
def bare_project(tmp_path: Path) -> Path:
    """A throwaway project whose only test does `import jukebox` with no sys.path setup (the PR #25 bug)."""
    (tmp_path / "jukebox").mkdir()
    (tmp_path / "jukebox" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_imports_jukebox.py").write_text(
        "import jukebox\n\n\ndef test_imports() -> None:\n    assert jukebox\n", encoding="utf-8"
    )
    return tmp_path


def test_the_old_python_dash_m_command_hid_the_problem(bare_project: Path) -> None:
    """Control: `python -m pytest` puts the folder on sys.path, so the bad test passes. This is the bug."""
    result = run_in(bare_project, [sys.executable, "-m", "pytest", "-q"])
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_pytest_command_fails_a_test_that_needs_the_repo_root_on_sys_path(bare_project: Path) -> None:
    result = run_in(bare_project, gate_pytest_cmd())
    assert result.returncode != 0, "the gate must not pass what CI would fail:\n" + result.stdout
    assert "ModuleNotFoundError" in result.stdout + result.stderr


def test_gate_and_ci_agree_on_sys_path(bare_project: Path) -> None:
    ci_pytest = shutil.which("pytest", path=str(Path(sys.executable).parent))
    if ci_pytest is None:
        pytest.skip("no pytest executable next to this Python (it is not a venv)")
    ci = run_in(bare_project, [ci_pytest, "-q"])
    gate = run_in(bare_project, gate_pytest_cmd())
    assert (gate.returncode == 0) == (ci.returncode == 0), (
        f"gate exit {gate.returncode} but CI-style exit {ci.returncode}"
    )


def test_ci_runs_plain_pytest() -> None:
    """If CI moves to `python -m pytest` (or stops running pytest), the gate's choice must be revisited."""
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    pytest_lines = [line.strip() for line in text.splitlines() if re.search(r"(^|\s)pytest\b", line)]
    commands = [line for line in pytest_lines if not line.startswith(("#", "- name:", "name:"))]
    assert commands, "ci.yml no longer runs pytest"
    assert all(re.match(r"^pytest(\s|$)", line) for line in commands), commands
    assert not re.search(r"-m\s+pytest", text), "ci.yml runs `python -m pytest`; update the gate to match"


def test_gate_checks_commits_were_written_by_the_pusher() -> None:
    cmds = [cmd for _, cmd in prepush.CHECKS]
    assert [sys.executable, "scripts/check_authors.py"] in cmds


def test_unfilled_env_placeholder_is_not_treated_as_a_secret(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("CLASS_API_KEY=your-class-api-key-here\n", encoding="utf-8")
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)
    assert scan_secrets.local_env_values() == []


def test_real_env_value_is_still_caught(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("CLASS_API_KEY=a1b2c3d4e5f6g7h8\n", encoding="utf-8")  # fake key
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)
    assert scan_secrets.local_env_values() == ["a1b2c3d4e5f6g7h8"]
