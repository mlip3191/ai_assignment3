#!/usr/bin/env python3
"""Tick a task's checkbox in its lane issue when the PR for that task is merged.

Run by .github/workflows/tick-task.yml on every merged PR. It reads the PR's title
and body for the task key ("Task: B4" in the body, or "(B4)" at the end of the title)
and the lane issue ("Part of #3"), then changes "- [ ] **B4**" to "- [x] **B4**".

Can also be run by hand (same on macOS and Windows, venv active):
  python scripts/github/tick_task.py --issue 3 --task B4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys


def find_task(title: str, body: str) -> str | None:
    m = re.search(r"(?im)^\s*\**task\**\s*:\s*\**\s*([A-E]\d{1,2})\b", body or "")
    if m:
        return m.group(1).upper()
    m = re.search(r"(?i)\(([A-E]\d{1,2})\)\s*$", title or "")
    return m.group(1).upper() if m else None


def find_lane_issue(body: str) -> int | None:
    m = re.search(r"(?i)part of\s+#(\d+)", body or "")
    return int(m.group(1)) if m else None


def tick(body: str, task: str) -> tuple[str, bool]:
    """Return (new_body, changed). Only the top-level task checkbox is touched."""
    pattern = re.compile(rf"^(- )\[ \]( \*\*{re.escape(task)}\*\*)", re.M)
    new, n = pattern.subn(r"\1[x]\2", body, count=1)
    return new, n > 0


def gh(*args: str, stdin: str | None = None) -> str:
    out = subprocess.run(
        ["gh", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if out.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed: {out.stderr.strip()}")
    return out.stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int)
    ap.add_argument("--task")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    args = ap.parse_args()

    issue, task = args.issue, args.task
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if (issue is None or task is None) and event_path:
        with open(event_path, encoding="utf-8") as f:
            pr = json.load(f)["pull_request"]
        task = task or find_task(pr.get("title", ""), pr.get("body") or "")
        issue = issue or find_lane_issue(pr.get("body") or "")
    if not issue or not task:
        print("No 'Part of #N' and task key found in this PR; nothing to tick.")
        return

    repo_args = ["--repo", args.repo] if args.repo else []
    body = json.loads(gh("issue", "view", str(issue), *repo_args, "--json", "body"))["body"]
    new, changed = tick(body, task.upper())
    if not changed:
        print(f"Task {task} not found unticked in #{issue} (already ticked, or wrong lane).")
        return
    gh("issue", "edit", str(issue), *repo_args, "--body-file", "-", stdin=new)
    print(f"Ticked {task} in #{issue}.")
    remaining = len(re.findall(r"^- \[ \] \*\*[A-E]\d{1,2}\*\*", new, re.M))
    if remaining == 0:
        gh(
            "issue", "comment", str(issue), *repo_args, "--body",
            "All tasks in this lane are ticked. Owner: check the lane's done criteria, then close this issue.",
        )  # fmt: skip


if __name__ == "__main__":
    main()
