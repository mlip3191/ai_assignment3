"""Shared helpers for the 5 lane issues: load the backlog and render issue bodies / summaries.

Used by bootstrap.py (creates the GitHub issues) and assignments.py (PROJECT.md §19).
Standard library only.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISSUES_FILE = ROOT / "scripts" / "github" / "issues.json"
TEAM_FILE = ROOT / ".github" / "team.json"
LANE_MARKER = "Lane key:"


def load() -> tuple[dict, dict]:
    spec = json.loads(ISSUES_FILE.read_text(encoding="utf-8"))
    team = json.loads(TEAM_FILE.read_text(encoding="utf-8"))
    order = [c["title"].split()[0] for c in spec["checkpoints"]]
    for lane in spec["lanes"]:
        lane["tasks"].sort(key=lambda t: order.index(t["milestone"]))  # stable: keeps dependency order
    return spec, team


def task_index(spec: dict) -> dict[str, str]:
    """task key -> lane role letter"""
    return {t["key"]: lane["role"] for lane in spec["lanes"] for t in lane["tasks"]}


def checkpoint_label(spec: dict, code: str) -> str:
    for c in spec["checkpoints"]:
        if c["title"].split()[0] == code:
            d = date.fromisoformat(c["due"])
            return f"{c['title']} (due {d.strftime('%a %m/%d')})"
    return code


def who(member: dict, role: str, assign: bool = True) -> str:
    if assign and member.get("github"):
        return f"@{member['github']}"
    return f"role {role}"


def render_body(lane: dict, spec: dict, team: dict, numbers: dict[str, int], assign: bool = True) -> str:
    """Markdown body for one lane issue. `numbers` maps role letter -> issue number (may be partial)."""
    members = team["members"]
    me = members[lane["role"]]
    reviewer_role = me["reviewer"]
    owner_of = task_index(spec)

    def lane_ref(role: str) -> str:
        return f"#{numbers[role]}" if role in numbers else f"lane {role}"

    def dep_text(key: str) -> str:
        role = owner_of[key]
        return key if role == lane["role"] else f"{key} ({lane_ref(role)})"

    lines = [
        f"# Lane {lane['role']}: {lane['title']}",
        "",
        f"**Owner:** {who(me, lane['role'], assign)}"
        + (f" ({me['os']})" if me.get("os") else "")
        + f" · **Your PRs are reviewed by:** {who(members[reviewer_role], reviewer_role, assign)}",
        "",
        "## Mission",
        lane["mission"],
        "",
        "## You own (only you change these without asking)",
        *[f"- {x}" for x in lane["owns"]],
        "",
        "Anything else belongs to another lane: ask its owner, or open a small PR and request their review.",
        "",
        "## Hand-offs",
        "**Others are waiting on you for:**",
        *[f"- {x}" for x in lane["provides"]],
        "",
        "**You're waiting on:**",
        *[f"- {x}" for x in lane["needs"]],
        "",
        "## How to work this lane",
        "- **One task per Claude Code session:** `/start-session <task key>` (e.g. "
        f"`/start-session {lane['tasks'][0]['key']}`). No key? `/start-session` picks your next ready task.",
        "- **One task = one branch = one PR.** Branch `feat/<this issue #>-<task key>-<desc>`, PR title ends with "
        "`(<task key>)`, PR body says `Part of #<this issue>` and `Task: <key>`. `/finish-session` does all of this.",
        "- **The checkbox ticks itself** when that PR is merged. Close this issue when every box is ticked.",
        "- A task is ready when every task it needs is ticked (look it up in the linked lane).",
        "",
        "## Tasks",
    ]
    current = None
    for t in lane["tasks"]:
        if t["milestone"] != current:
            current = t["milestone"]
            lines += ["", f"### {checkpoint_label(spec, current)}", ""]
        needs = ", ".join(dep_text(k) for k in t.get("depends", [])) or "nothing"
        lines.append(f"- [ ] **{t['key']}** {t['title']}")
        lines.append(f"  - **Goal:** {t['goal']}")
        lines.append(f"  - **Needs:** {needs}")
        lines.append(
            f"  - **Refs:** {', '.join(t['refs']) or '—'} · **Requirements:** {', '.join(t['reqs']) or '—'}"
        )
        lines.append("  - **Done when:**")
        lines += [f"    - {c}" for c in t["criteria"]]
    lines += ["", "## Lane directory"]
    for role, m in members.items():
        lines.append(f"- {lane_ref(role)}: Lane {role} ({m['role']}) — {who(m, role, assign)}")
    lines += ["", f"<sub>{LANE_MARKER} {lane['role']}</sub>"]
    return "\n".join(lines)
