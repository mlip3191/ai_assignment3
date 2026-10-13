"""Tests for the team's GitHub workflow rules."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGE_BY_OWNER = ROOT / ".github" / "workflows" / "merge-by-owner.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_requires_tests_for_code_changes() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "Code changes include test cases" in text
    assert r"^(jukebox/|scripts/|\.claude/hooks/|\.githooks/|app\.py$)" in text


def test_ci_checks_commit_authors_and_only_the_owner_can_validate() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "Commits written by the PR author" in text
    assert "authors-validated" in text
    assert '[ "$validated_by" = "$OWNER" ]' in text


def test_ci_server_side_checks_are_in_the_required_checks_job() -> None:
    text = CI.read_text(encoding="utf-8")
    checks_job = text.split("  checks:", 1)[1].split("\n  cross-platform:", 1)[0]
    assert "Code changes include test cases" in checks_job
    assert "Commits written by the PR author" in checks_job


def test_merge_by_owner_runs_on_merged_prs() -> None:
    text = MERGE_BY_OWNER.read_text(encoding="utf-8")
    assert "types: [closed]" in text
    assert "github.event.pull_request.merged == true" in text


def test_merge_by_owner_checks_merger_against_codeowners_and_fails_on_mismatch() -> None:
    text = MERGE_BY_OWNER.read_text(encoding="utf-8")
    assert "github.event.pull_request.merged_by.login" in text
    assert "scripts/github/merge_owner.py" in text
    assert "merged-by-non-owner" in text
    assert "exit 1" in text
