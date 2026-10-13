"""Tests for the pre-push quality gate (scripts/prepush.py) and the secret scan's .env handling."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


def test_gate_runs_the_full_test_suite() -> None:
    cmds = [cmd for _, cmd in prepush.CHECKS]
    assert [sys.executable, "-m", "pytest", "-q"] in cmds


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
