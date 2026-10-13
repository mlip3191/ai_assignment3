#!/usr/bin/env python3
"""Print PROJECT.md §19 (the 5 lanes and their tasks) from issues.json + team.json.

Re-run after editing the backlog and paste the output into PROJECT.md §19
(same command on macOS and Windows, venv active):
  python scripts/github/assignments.py
"""

from __future__ import annotations

import sys

from lanes import checkpoint_label, load, task_index

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles/pipes default to a legacy code page
except Exception:
    pass

spec, team = load()
members = team["members"]
owner_of = task_index(spec)

print("| Lane | Owner | OS | Tasks | Reviewer of their PRs | Mission (short) |")
print("|---|---|---|---|---|---|")
for lane in spec["lanes"]:
    m = members[lane["role"]]
    name = f"{m['name']} (@{m['github']})" if m.get("github") else "TBD"
    short = lane["mission"].split(". ")[0].rstrip(".") + "."
    print(
        f"| **{lane['role']}: {lane['title']}** | {name} | {m.get('os') or 'TBD'} | {len(lane['tasks'])} "
        f"| {m['reviewer']} | {short} |"
    )
print()

for lane in spec["lanes"]:
    role = lane["role"]
    print(f"### Lane {role}: {lane['title']}\n")
    print(f"**Mission:** {lane['mission']}\n")
    print("**Owns:** " + "; ".join(lane["owns"]) + "\n")
    print("**Others are waiting on this lane for:** " + "; ".join(lane["provides"]) + "\n")
    print("| Task | Checkpoint | Title | Needs |")
    print("|---|---|---|---|")
    for t in lane["tasks"]:
        needs = ", ".join(k if owner_of[k] == role else f"{k} ({owner_of[k]})" for k in t["depends"]) or "—"
        cp = checkpoint_label(spec, t["milestone"]).split(" (due ")
        print(
            f"| {t['key']} | {t['milestone']} ({cp[1].rstrip(')')}) | {t['title'].replace('|', '/')} | {needs} |"
        )
    print()

print("### Load per checkpoint\n")
print("| Checkpoint | A | B | C | D | E | Tasks |")
print("|---|---|---|---|---|---|---|")
for c in spec["checkpoints"]:
    code = c["title"].split()[0]
    counts = [sum(1 for t in lane["tasks"] if t["milestone"] == code) for lane in spec["lanes"]]
    print(f"| {checkpoint_label(spec, code)} | " + " | ".join(map(str, counts)) + f" | {sum(counts)} |")
