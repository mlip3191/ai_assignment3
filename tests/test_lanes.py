"""Tests for the lane-issue tooling: backlog consistency, issue rendering, and auto-ticking."""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "github"))

from lanes import checkpoint_label, load, render_body, task_index  # noqa: E402
from tick_task import find_lane_issue, find_task, tick  # noqa: E402


def test_five_lanes_one_per_role() -> None:
    spec, team = load()
    assert [lane["role"] for lane in spec["lanes"]] == list("ABCDE")
    assert set(team["members"]) == set("ABCDE")


def test_task_keys_unique_and_dependencies_exist() -> None:
    spec, _ = load()
    keys = [t["key"] for lane in spec["lanes"] for t in lane["tasks"]]
    assert len(keys) == len(set(keys))
    for lane in spec["lanes"]:
        for t in lane["tasks"]:
            assert t["key"].startswith(lane["role"]), t["key"]
            for dep in t["depends"]:
                assert dep in keys, f"{t['key']} needs unknown {dep}"


def test_no_dependency_cycles() -> None:
    spec, _ = load()
    deps = {t["key"]: t["depends"] for lane in spec["lanes"] for t in lane["tasks"]}
    done: set[str] = set()

    def visit(k: str, path: tuple[str, ...]) -> None:
        assert k not in path, f"cycle: {' -> '.join((*path, k))}"
        if k in done:
            return
        for d in deps[k]:
            visit(d, (*path, k))
        done.add(k)

    for k in deps:
        visit(k, ())


def test_render_has_checkbox_per_task_and_links() -> None:
    spec, team = load()
    numbers = {r: n for n, r in enumerate("ABCDE", 1)}
    owner = task_index(spec)
    for lane in spec["lanes"]:
        body = render_body(lane, spec, team, numbers, assign=False)
        for t in lane["tasks"]:
            assert f"- [ ] **{t['key']}** " in body
            for d in t["depends"]:
                if owner[d] != lane["role"]:
                    assert f"{d} (#{numbers[owner[d]]})" in body
        assert f"Lane key: {lane['role']}" in body
        assert len(body) < 60000  # GitHub issue body limit is 65536


def test_find_task_and_issue_from_pr() -> None:
    body = "## Summary\nPart of #2\nTask: B4\n"
    assert find_task("feat(songs): client", body) == "B4"
    assert find_lane_issue(body) == 2
    assert find_task("feat(songs): add ACE-Step client (b4)", "") == "B4"
    assert find_task("no key here", "Task: <!-- task key, e.g. B4 -->") is None
    assert find_lane_issue("Closes #2") is None


def test_tick_only_touches_the_task_line() -> None:
    body = "- [ ] **B4** ACE-Step client\n  - **Done when:**\n    - [ ] not a task\n- [ ] **B5** prompts\n"
    new, changed = tick(body, "B4")
    assert changed
    assert new.startswith("- [x] **B4**")
    assert "- [ ] **B5**" in new
    assert tick(new, "B4") == (new, False)  # already ticked
    assert tick(body, "B40")[1] is False


def test_a11_prepush_hook_task_is_in_lane_a() -> None:
    spec, _ = load()
    lane_a = next(lane for lane in spec["lanes"] if lane["role"] == "A")
    task = next((t for t in lane_a["tasks"] if t["key"] == "A11"), None)
    assert task is not None
    assert task["milestone"] == "M1"
    assert task["depends"] == []
    criteria = " ".join(task["criteria"])
    assert "100755" in criteria
    assert "doctor.py" in criteria


def test_project_md_lists_every_backlog_task_and_count() -> None:
    spec, _ = load()
    keys = [t["key"] for lane in spec["lanes"] for t in lane["tasks"]]
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section19 = text.split("## 19. The five lanes", 1)[1]
    for key in keys:
        assert f"\n| {key} |" in section19, f"{key} missing from PROJECT.md section 19"
    assert f"({len(keys)} tasks total)" in text
    assert f"5 lanes, {len(keys)} tasks" in text


def test_a12_gate_parity_task_is_in_lane_a() -> None:
    spec, _ = load()
    lane_a = next(lane for lane in spec["lanes"] if lane["role"] == "A")
    task = next((t for t in lane_a["tasks"] if t["key"] == "A12"), None)
    assert task is not None
    assert task["milestone"] == "M2"
    assert task["depends"] == []
    assert "§16.5" in task["refs"]
    criteria = " ".join(task["criteria"])
    assert "pytest -q" in criteria
    assert "CI" in criteria
    assert "sys.path" in criteria


def test_a13_pin_dev_tools_task_is_in_lane_a() -> None:
    spec, _ = load()
    lane_a = next(lane for lane in spec["lanes"] if lane["role"] == "A")
    task = next((t for t in lane_a["tasks"] if t["key"] == "A13"), None)
    assert task is not None
    assert task["milestone"] == "M2"
    assert task["depends"] == []
    assert "§4" in task["refs"]
    criteria = " ".join(task["criteria"])
    for needle in ("requirements-dev.txt", "pytest", "respx", "ruff", "==", "CI"):
        assert needle in criteria, needle


def test_project_md_load_tables_match_the_backlog() -> None:
    """The per-lane task counts (section 19) and the per-checkpoint load table must match issues.json."""
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section19 = text.split("## 19. The five lanes", 1)[1]
    for lane in spec["lanes"]:
        row = next(r for r in section19.splitlines() if r.startswith(f"| **{lane['role']}: "))
        assert row.split("|")[4].strip() == str(len(lane["tasks"])), f"lane {lane['role']} task count"
    for checkpoint in spec["checkpoints"]:
        milestone = checkpoint["title"].split()[0]  # "M0 Foundations & spikes" -> "M0"
        row = next(r for r in section19.splitlines() if r.startswith(f"| {milestone} "))
        cells = [c.strip() for c in row.strip("|").split("|")]
        per_lane = [sum(t["milestone"] == milestone for t in lane["tasks"]) for lane in spec["lanes"]]
        assert cells[1:6] == [str(n) for n in per_lane], f"{milestone} per-lane counts"
        assert cells[6] == str(sum(per_lane)), f"{milestone} total"


WEEKDAY_DATE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]* (\d{1,2})/(\d{1,2})\b")
SUBMISSION_DUE = re.compile(
    r"Submission due: \*\*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]* (\d{1,2})/(\d{1,2})/(\d{4})\*\*"
)


def wrong_weekdays(text: str, year: int = 2026) -> list[str]:
    """Every 'Wed 10/21'-style pair in `text` whose weekday is wrong for that date."""
    bad = []
    for m in WEEKDAY_DATE.finditer(text):
        weekday, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        if date(year, month, day).strftime("%a") != weekday:
            bad.append(m.group(0))
    return bad


def submission_due(text: str) -> date:
    """The date in PROJECT.md's 'Submission due: **Fri 10/30/2026**' header line."""
    m = SUBMISSION_DUE.search(text)
    if m is None:
        raise ValueError("no 'Submission due: **Day MM/DD/YYYY**' line found")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))


def test_checkpoint_dates_are_in_order() -> None:
    """A half-shifted schedule shows up as dates that run backwards."""
    spec, _ = load()
    codes = [c["title"].split()[0] for c in spec["checkpoints"]]
    assert codes == ["M0", "M1", "M2", "M3", "M4"]
    dates = [date.fromisoformat(c["due"]) for c in spec["checkpoints"]]
    for earlier, later, code in zip(dates[:-1], dates[1:], codes[1:], strict=True):
        assert earlier < later, f"{code} is due on or before the checkpoint before it"


def test_milestone_due_is_the_last_checkpoint() -> None:
    spec, _ = load()
    assert spec["milestone"]["due"] == spec["checkpoints"][-1]["due"]


def test_submission_date_matches_project_md() -> None:
    """PROJECT.md says when we submit; the GitHub milestone is due the day before."""
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    milestone = date.fromisoformat(spec["milestone"]["due"])
    assert milestone + timedelta(days=1) == submission_due(text)


# ---- no feature freeze (dropped 10/28) ------------------------------------------------------------
# The release lead dropped the freeze; teammates were holding work back for it. The schedule must not
# bring it back, but the decision log (section 2) may, and should, say why it was dropped.


def _freeze_rows(text: str) -> list[str]:
    """The table rows that mention a freeze (prose is allowed to)."""
    return [line for line in text.splitlines() if line.startswith("|") and "freeze" in line.lower()]


def test_no_freeze_row_in_the_schedule() -> None:
    spec, _ = load()
    for checkpoint in spec["checkpoints"]:
        assert "freeze" not in checkpoint["description"].lower(), checkpoint["title"]
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section10 = text.split("## 10. Schedule & milestones", 1)[1].split("\n## 11.", 1)[0]
    assert _freeze_rows(section10) == []


def test_freeze_check_catches_the_old_row() -> None:
    old_row = "| Feature freeze Tue 10/27, 9 pm — after this, only bug fixes and docs | All |"
    assert _freeze_rows(f"| Task | Owner |\n|---|---|\n{old_row}") == [old_row]
    assert _freeze_rows("We dropped the freeze, so D5 could merge.") == []
    assert _freeze_rows("| Tag rc2; fix what the deploy test found | A |") == []


def test_decision_log_records_dropping_the_freeze() -> None:
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section2 = text.split("## 2. Key decisions (decision log)", 1)[1].split("\n## 3.", 1)[0]
    rows = [
        line for line in section2.splitlines() if line.startswith("| 10/28 |") and "freeze" in line.lower()
    ]
    assert len(rows) == 1


@pytest.mark.parametrize("path", ["PROJECT.md", "scripts/github/issues.json"])
def test_weekday_names_match_dates(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert WEEKDAY_DATE.search(text), f"no 'Day MM/DD' dates found in {path}; did the pattern break?"
    assert wrong_weekdays(text) == [], f"{path} has weekday names that don't match their dates"


def test_date_helpers_reject_bad_input() -> None:
    assert wrong_weekdays("due Wed 10/22") == ["Wed 10/22"]  # 10/22/2026 is a Thursday
    assert wrong_weekdays("due Thu 10/22") == []
    assert submission_due("Submission due: **Fri 10/30/2026**") == date(2026, 10, 30)
    with pytest.raises(ValueError):
        submission_due("Target submission: **Fri 10/30/2026**")


def heading_end_label(line: str) -> str:
    """The last 'Day MM/DD' in a section 10 heading, ignoring any '(...)' note, e.g. 'Wed 10/21'."""
    found = [m.group(0) for m in WEEKDAY_DATE.finditer(line.split("(", 1)[0])]
    if not found:
        raise ValueError(f"no 'Day MM/DD' date in heading: {line!r}")
    return found[-1]


def _due_label(due: str) -> str:
    return date.fromisoformat(due).strftime("%a %m/%d")


def test_section10_headings_end_on_the_checkpoint_due_date() -> None:
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section10 = text.split("## 10. Schedule & milestones", 1)[1].split("\n## 11.", 1)[0]
    for c in spec["checkpoints"]:
        code = c["title"].split()[0]
        heading = next(line for line in section10.splitlines() if line.startswith(f"### {code} "))
        assert heading_end_label(heading) == _due_label(c["due"]), f"section 10 heading for {code}"


def test_section19_tables_use_the_checkpoint_dates() -> None:
    """The per-checkpoint load table and every task row must carry issues.json's dates."""
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    section19 = text.split("## 19. The five lanes", 1)[1]
    due = {c["title"].split()[0]: c["due"] for c in spec["checkpoints"]}
    for code in due:
        row = next(r for r in section19.splitlines() if r.startswith(f"| {code} "))
        assert row.split("|")[1].strip() == checkpoint_label(spec, code), f"load table row for {code}"
    milestone_of = {t["key"]: t["milestone"] for lane in spec["lanes"] for t in lane["tasks"]}
    task_row = re.compile(r"^\| ([A-E]\d+) \| (M\d) \((.+?)\) \|", re.MULTILINE)
    rows = task_row.findall(section19)
    assert len(rows) == len(milestone_of), "a section 19 task row is missing or its date format changed"
    for key, code, label in rows:
        assert code == milestone_of[key], f"{key} milestone in section 19"
        assert label == _due_label(due[code]), f"{key} date in section 19"


def test_prose_dates_match_the_checkpoints() -> None:
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    due = {c["title"].split()[0]: c["due"] for c in spec["checkpoints"]}
    milestone = date.fromisoformat(spec["milestone"]["due"])
    assert f'"v1.0 submission" (due {milestone.month}/{milestone.day})' in text
    assert f"Your M0 tasks are due {_due_label(due['M0'])}" in text


def test_heading_end_label_reads_ranges_and_rejects_bad_headings() -> None:
    assert heading_end_label("### M0 — Foundations & spikes · Tue 10/20 – Wed 10/21") == "Wed 10/21"
    assert heading_end_label("### M4 — Docs · Thu 10/29 (Fri 10/30 buffer)") == "Thu 10/29"
    assert heading_end_label("### M3 — Deploy test · Wed 10/28") == "Wed 10/28"
    with pytest.raises(ValueError):
        heading_end_label("### M5 — no dates here")


# ---- the repo-visibility decision (section 14 Q5, DL12) -------------------------------------------
# Decided 10/21: the repo stays public until we submit, then goes private and the professor is invited.


def _contradicts_visibility_decision(text: str) -> list[str]:
    """Wording from before the decision: a ban on going private, or a public repo counting as access."""
    old_wording = ("privatiz", "accepted invite or public repo", "Still open**", "Q5 stays open")
    return [phrase for phrase in old_wording if phrase.lower() in text.lower()]


@pytest.mark.parametrize("path", ["PROJECT.md", "scripts/github/issues.json"])
def test_no_wording_contradicts_the_repo_visibility_decision(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert _contradicts_visibility_decision(text) == [], f"{path} still has pre-decision Q5/DL12 wording"


def test_visibility_check_catches_the_old_wording() -> None:
    assert _contradicts_visibility_decision("Nobody privatizes the repo") == ["privatiz"]
    assert _contradicts_visibility_decision("Professor has repo access (accepted invite or public repo)")
    assert _contradicts_visibility_decision("Q5 | ... | **Still open** (not answered in A5)")
    assert _contradicts_visibility_decision("accepted invite; private only at submission (DL12)") == []


def test_dl12_and_q5_say_private_only_at_submission() -> None:
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    dl12 = next(line for line in text.splitlines() if line.startswith("| DL12 |"))
    q5 = next(line for line in text.splitlines() if line.startswith("| Q5 |"))
    assert "private is allowed only at submission" in dl12
    assert "public until we submit" in q5
    blockers = next(line for line in text.splitlines() if line.startswith("| **Blockers** |"))
    assert "§14 Q5" in blockers and "decided" in blockers


def test_a10_requires_an_accepted_invite_for_the_professor() -> None:
    spec, _ = load()
    a10 = next(t for lane in spec["lanes"] for t in lane["tasks"] if t["key"] == "A10")
    criteria = "\n".join(a10["criteria"])
    assert "Professor has repo access (accepted invite)" in criteria
    # The repo stays public (decided 11/01); `bootstrap.py --refresh` renders these criteria into lane issue #2.
    assert "the repo stays public, with the professor invited as a collaborator" in criteria
    assert "goes private" not in criteria


def test_issues_json_never_says_the_repo_goes_private() -> None:
    text = (ROOT / "scripts" / "github" / "issues.json").read_text(encoding="utf-8")
    assert "goes private" not in text
