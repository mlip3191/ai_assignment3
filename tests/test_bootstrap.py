"""Tests for the branch protection rules that bootstrap.py applies to main."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "github"))

from bootstrap import PROTECTION  # noqa: E402


def test_main_requires_a_pr_with_one_approval() -> None:
    reviews = PROTECTION["required_pull_request_reviews"]
    assert reviews["required_approving_review_count"] >= 1


def test_new_commits_need_fresh_approval_from_someone_else() -> None:
    reviews = PROTECTION["required_pull_request_reviews"]
    assert reviews["dismiss_stale_reviews"] is True
    assert reviews["require_last_push_approval"] is True


def test_ci_must_pass_before_merge() -> None:
    assert "checks" in PROTECTION["required_status_checks"]["contexts"]


def test_rules_apply_to_admins_too() -> None:
    assert PROTECTION["enforce_admins"] is True


def test_no_force_push_or_deleting_main() -> None:
    assert PROTECTION["allow_force_pushes"] is False
    assert PROTECTION["allow_deletions"] is False
