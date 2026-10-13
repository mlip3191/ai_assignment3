"""Tests for the push author check (scripts/check_authors.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_authors", ROOT / "scripts" / "check_authors.py")
check_authors = importlib.util.module_from_spec(spec)
sys.modules["check_authors"] = check_authors
spec.loader.exec_module(check_authors)

ME = "gunnar@example.com"


@pytest.fixture(autouse=True)
def as_gunnar(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "my_email", lambda: ME)


def test_missing_git_identity_blocks(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "my_email", lambda: "")
    assert check_authors.main() == 1


def test_my_own_commits_pass() -> None:
    commits = [("abc1234", ME, "Gunnar"), ("def5678", "Gunnar@Example.com", "Gunnar")]
    assert check_authors.foreign_commits(commits, ME) == []


def test_someone_elses_commit_is_flagged() -> None:
    commits = [("abc1234", ME, "Gunnar"), ("def5678", "dillon@example.com", "Dillon")]
    assert check_authors.foreign_commits(commits, ME) == [("def5678", "dillon@example.com", "Dillon")]


def test_unvalidated_foreign_commits_block_the_push(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "commits_to_push", lambda: [("def5678", "dillon@example.com", "D")])
    monkeypatch.setattr(check_authors, "ask_in_terminal", lambda q: None)  # no terminal (e.g. Claude)
    assert check_authors.main() == 1


def test_validation_answer_other_than_yes_blocks(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "commits_to_push", lambda: [("def5678", "dillon@example.com", "D")])
    monkeypatch.setattr(check_authors, "ask_in_terminal", lambda q: "no")
    assert check_authors.main() == 1


def test_validated_foreign_commits_are_allowed(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "commits_to_push", lambda: [("def5678", "dillon@example.com", "D")])
    monkeypatch.setattr(check_authors, "ask_in_terminal", lambda q: "yes")
    assert check_authors.main() == 0


def test_no_origin_main_skips_the_check(monkeypatch) -> None:
    monkeypatch.setattr(check_authors, "commits_to_push", lambda: None)
    assert check_authors.main() == 0
