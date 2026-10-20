"""Tests for the lane-issue tooling: backlog consistency, issue rendering, and auto-ticking."""

from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "github"))

from lanes import load, render_body, task_index  # noqa: E402
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


# ---- the milestone due date in issues.json must match the target submission in PROJECT.md ----------

TARGET = re.compile(r"Target submission: \*\*(\w{3}) (\d{1,2})/(\d{1,2})/(\d{4})\*\*")


def _date_problems(milestone_due: str, project_text: str) -> list[str]:
    """What is wrong between the milestone due date and the 'Target submission' line, if anything."""
    found = TARGET.search(project_text)
    if found is None:
        return ["PROJECT.md has no 'Target submission: **Day M/D/YYYY**' line"]
    weekday, month, day, year = found.group(1), int(found.group(2)), int(found.group(3)), int(found.group(4))
    target = datetime.date(year, month, day)
    problems = []
    if target.strftime("%a") != weekday:
        problems.append(f"{weekday} {target.isoformat()} is a {target.strftime('%a')}")
    if target.isoformat() != milestone_due:
        problems.append(
            f"PROJECT.md says {target.isoformat()} but issues.json milestone due is {milestone_due}"
        )
    return problems


def test_milestone_due_matches_the_target_submission_in_project_md() -> None:
    spec, _ = load()
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    assert _date_problems(spec["milestone"]["due"], text) == []


def test_a_mismatched_or_misnamed_date_is_reported() -> None:
    line = "Target submission: **Fri 10/30/2026** (note)"
    assert _date_problems("2026-10-30", line) == []
    assert _date_problems("2026-10-22", line) == [
        "PROJECT.md says 2026-10-30 but issues.json milestone due is 2026-10-22"
    ]
    assert _date_problems("2026-10-26", "Target submission: **Fri 10/26/2026**") == [
        "Fri 2026-10-26 is a Mon"
    ]
    assert _date_problems("2026-10-30", "no date here") == [
        "PROJECT.md has no 'Target submission: **Day M/D/YYYY**' line"
    ]


def test_checkpoints_are_in_order_and_not_after_the_milestone() -> None:
    spec, _ = load()
    dues = [c["due"] for c in spec["checkpoints"]]
    assert dues == sorted(dues)
    assert dues[-1] <= spec["milestone"]["due"]


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
