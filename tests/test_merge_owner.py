"""Tests for the 'owner of the files merges' rule (scripts/github/merge_owner.py, .github/CODEOWNERS)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "github"))

from merge_owner import CODEOWNERS, allowed_mergers, owners_of, parse  # noqa: E402

RULES = parse(CODEOWNERS.read_text(encoding="utf-8"))


def test_each_lane_owns_its_files() -> None:
    assert owners_of("jukebox/clients/acestep.py", RULES) == ["gunnaroc"]
    assert owners_of("jukebox/services/art.py", RULES) == ["felcervino"]
    assert owners_of("samples/covers/a.png", RULES) == ["felcervino"]
    assert owners_of("jukebox/services/dj.py", RULES) == ["mlip3191"]
    assert owners_of("run.bat", RULES) == ["mlip3191"]
    assert owners_of("app.py", RULES) == ["afondale"]
    assert owners_of("jukebox/config.py", RULES) == ["mlip3191"]
    assert owners_of("PROJECT.md", RULES) == ["mlip3191"]


def test_specific_ui_files_beat_lane_e_ui_folder() -> None:
    assert owners_of("jukebox/ui/player_panel.py", RULES) == ["afondale"]
    assert owners_of("jukebox/ui/generate_tab.py", RULES) == ["gunnaroc"]
    assert owners_of("jukebox/ui/dj_settings.py", RULES) == ["mlip3191"]


def test_tests_have_no_owner() -> None:
    assert owners_of("tests/test_acestep.py", RULES) == []


def test_owner_of_changed_files_may_merge() -> None:
    changed = ["jukebox/clients/acestep.py", "tests/test_acestep.py"]
    assert allowed_mergers(changed, RULES, author="gunnaroc") == {"gunnaroc"}


def test_touching_another_lane_lets_either_owner_merge_but_not_others() -> None:
    changed = ["jukebox/services/songs.py", "jukebox/clients/base.py"]
    allowed = allowed_mergers(changed, RULES, author="gunnaroc")
    assert allowed == {"gunnaroc", "mlip3191"}
    assert "afondale" not in allowed


def test_only_unowned_files_fall_back_to_the_author() -> None:
    assert allowed_mergers(["tests/test_x.py"], RULES, author="afondale") == {"afondale"}


def test_codeowners_handles_match_team_json() -> None:
    team = json.loads((ROOT / ".github" / "team.json").read_text(encoding="utf-8"))
    handles = {m["github"].lower() for m in team["members"].values()}
    owners = {o for _, os_ in RULES for o in os_}
    assert owners <= handles


MEMBERS = json.loads((ROOT / ".github" / "team.json").read_text(encoding="utf-8"))["members"]


def test_lane_d_is_reviewed_by_gunnar() -> None:
    assert MEMBERS["D"]["github"] == "mlip3191"
    assert MEMBERS["D"]["reviewer"] == "B"
    assert MEMBERS["B"]["github"] == "gunnaroc"


def test_lane_b_is_reviewed_by_felipe() -> None:
    assert MEMBERS["B"]["reviewer"] == "C"
    assert MEMBERS["C"]["github"] == "felcervino"


def test_everyone_reviews_someone_and_no_one_reviews_themselves() -> None:
    """PROJECT.md section 3: each person reviews at least one teammate's PR, never their own."""
    reviewers = {MEMBERS[m["reviewer"]]["github"] for m in MEMBERS.values()}
    assert reviewers == {m["github"] for m in MEMBERS.values()}
    for role, m in MEMBERS.items():
        assert MEMBERS[m["reviewer"]]["github"] != m["github"], role


def test_project_md_review_column_matches_team_json() -> None:
    """The 'Reviews PRs from' column in PROJECT.md section 3 says the same as team.json."""
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    listed = {}
    for role, last in re.findall(r"^\| \*\*([A-E]) — .*\| ([^|]*) \|$", text, re.MULTILINE):
        listed[role] = set(re.findall(r"\b[A-E]\b", last))
    expected = {role: {r for r, m in MEMBERS.items() if m["reviewer"] == role} for role in MEMBERS}
    assert listed == expected
