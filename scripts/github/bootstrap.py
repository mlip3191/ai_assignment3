#!/usr/bin/env python3
"""Set up the GitHub repo for the AI Jukebox team: one lane issue per person.

Creates labels, one milestone ("v1.0 submission"), and the 5 lane issues from
scripts/github/issues.json, each assigned to its owner from .github/team.json, with
the owner's full task checklist inside. Optionally invites collaborators and
protects main. Safe to re-run: labels are updated, and existing lane issues are
found by their "Lane key" marker and only refreshed with --refresh.

Requires the GitHub CLI (`gh`), logged in with `gh auth login` as a repo admin.

Usage (run from the repo root, venv active; same on macOS and Windows):
  python scripts/github/bootstrap.py --dry-run           # print what would happen
  python scripts/github/bootstrap.py --invite --skip-issues
  python scripts/github/bootstrap.py                     # labels, milestone, 5 lane issues
  python scripts/github/bootstrap.py --protect --skip-issues
  python scripts/github/bootstrap.py --no-assign         # create issues before handles are known
  python scripts/github/bootstrap.py --refresh           # re-render existing lane issue bodies after
                                                         # editing issues.json (ticked boxes are kept)
  python scripts/github/bootstrap.py --dry-run --preview B   # print lane B's issue body
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys

from lanes import LANE_MARKER, ROOT, load, render_body

# Rules for main: every change is a PR, and someone other than the last pusher approves it
# (re-approval after new commits) and CI passes before it can merge. No force pushes or deletion.
PROTECTION = {
    "required_status_checks": {"strict": False, "contexts": ["checks"]},
    "enforce_admins": True,  # no one, admins included, gets to skip review
    "required_pull_request_reviews": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews": True,
        "require_last_push_approval": True,
    },
    "restrictions": None,
    "allow_force_pushes": False,
    "allow_deletions": False,
}


class Gh:
    def __init__(self, repo: str, dry_run: bool):
        self.repo = repo
        self.dry = dry_run

    def run(
        self, args: list[str], *, stdin: str | None = None, mutate: bool = True, check: bool = True
    ) -> str:
        if self.dry and mutate:
            shown = " ".join(a if " " not in a else repr(a) for a in args)
            print(f"  [dry-run] gh {shown}")
            return ""
        proc = subprocess.run(
            ["gh", *args], input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"gh {' '.join(args[:3])}… failed: {proc.stderr.strip()}")
        return proc.stdout.strip()


def detect_repo() -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("Could not detect the repo. Run from inside the cloned repo or pass --repo owner/name.")
    return out.stdout.strip()


def strip_assignees(cmd: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == "--assignee":
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="owner/name (default: detect from current folder)")
    ap.add_argument("--dry-run", action="store_true", help="print actions without changing GitHub")
    ap.add_argument("--no-assign", action="store_true", help="create issues without assignees")
    ap.add_argument(
        "--invite", action="store_true", help="invite every handle in team.json as a collaborator"
    )
    ap.add_argument("--protect", action="store_true", help="require PR + 1 review + CI on main")
    ap.add_argument("--skip-issues", action="store_true", help="only labels/milestone/invites/protection")
    ap.add_argument("--refresh", action="store_true", help="re-render bodies of existing lane issues")
    ap.add_argument("--preview", metavar="ROLE", help="with --dry-run: print the full body of one lane issue")
    args = ap.parse_args()

    spec, team = load()
    assign = not args.no_assign

    if args.preview:
        lane = next(lane for lane in spec["lanes"] if lane["role"] == args.preview.upper())
        print(render_body(lane, spec, team, {r: n for n, r in enumerate("ABCDE", 1)}, assign))
        return

    if not shutil.which("gh"):
        sys.exit("GitHub CLI not found. Install it (see PROJECT.md §16.1) and run `gh auth login`.")

    missing = [r for r, m in team["members"].items() if not m.get("github")]
    if assign and missing and not args.skip_issues:
        sys.exit(
            f"No GitHub handle for role(s) {missing} in .github/team.json. "
            "Fill them in, or re-run with --no-assign."
        )

    repo = args.repo or (args.dry_run and "OWNER/REPO") or detect_repo()
    gh = Gh(repo, args.dry_run)
    print(f"Repo: {repo}{'  (dry run)' if args.dry_run else ''}")

    # 1. Collaborators
    if args.invite:
        print("Inviting collaborators…")
        handles = [m["github"] for m in team["members"].values() if m.get("github")]
        if team.get("professor_github"):
            handles.append(team["professor_github"])
        for h in handles:
            try:
                gh.run(["api", "-X", "PUT", f"repos/{repo}/collaborators/{h}", "-f", "permission=push"])
                print(f"  invited {h} (they must accept the email invite before they can be assigned)")
            except RuntimeError as e:
                print(f"  ! {h}: {e}")

    # 2. Labels
    print("Labels…")
    for lab in spec["labels"]:
        gh.run(
            [
                "label", "create", lab["name"], "--repo", repo, "--color", lab["color"],
                "--description", lab["description"], "--force",
            ]
        )  # fmt: skip
    print(f"  {len(spec['labels'])} labels created/updated")

    # 3. Milestone
    ms = spec["milestone"]
    print("Milestone…")
    existing_ms: set[str] = set()
    if not args.dry_run:
        raw = gh.run(["api", f"repos/{repo}/milestones?state=all&per_page=100"], mutate=False)
        existing_ms = {m["title"] for m in json.loads(raw or "[]")}
    if ms["title"] in existing_ms:
        print(f"  exists: {ms['title']}")
    else:
        gh.run(
            [
                "api", "-X", "POST", f"repos/{repo}/milestones", "-f", f"title={ms['title']}",
                "-f", f"description={ms['description']}", "-f", f"due_on={ms['due']}T23:59:59Z",
            ]
        )  # fmt: skip
        print(f"  created: {ms['title']} (due {ms['due']})")

    # 4. Lane issues (two passes: create, then fill in cross-lane links once all numbers are known)
    if not args.skip_issues:
        print("Lane issues…")
        numbers: dict[str, int] = {}
        bodies: dict[str, str] = {}
        if not args.dry_run:
            raw = gh.run(
                ["issue", "list", "--repo", repo, "--state", "all", "--label", "lane", "--limit", "50",
                 "--json", "number,body"],
                mutate=False,
            )  # fmt: skip
            for it in json.loads(raw or "[]"):
                km = re.search(rf"{LANE_MARKER} ([A-E])\b", it.get("body") or "")
                if km:
                    numbers[km.group(1)] = it["number"]
                    bodies[km.group(1)] = it.get("body") or ""
        existing = set(numbers)
        created: list[str] = []
        for n, lane in enumerate(spec["lanes"], 1):
            role = lane["role"]
            if role in existing:
                print(f"  exists: #{numbers[role]} Lane {role}: {lane['title']}")
                continue
            body = render_body(lane, spec, team, numbers, assign)
            title = f"Lane {role}: {lane['title']} ({len(lane['tasks'])} tasks)"
            cmd = [
                "issue", "create", "--repo", repo, "--title", title, "--body-file", "-",
                "--milestone", ms["title"], "--label", "lane", "--label", lane["label"],
            ]  # fmt: skip
            assignee = team["members"][role].get("github") if assign else None
            if assignee:
                cmd += ["--assignee", assignee]
            if args.dry_run:
                gh.run(cmd, stdin=body)
                numbers[role] = n
                created.append(role)
                continue
            try:
                url = gh.run(cmd, stdin=body)
            except RuntimeError as e:
                if not assignee:
                    raise
                print(f"  ! assigning {assignee} failed ({e}); creating unassigned. Assign later with")
                print("    gh issue edit <number> --add-assignee <handle>  (after they accept the invite)")
                url = gh.run(strip_assignees(cmd), stdin=body)
            numbers[role] = int(url.rstrip("/").split("/")[-1])
            created.append(role)
            print(f"  created #{numbers[role]} Lane {role}: {lane['title']} → {assignee or 'unassigned'}")

        to_render = [lane for lane in spec["lanes"] if lane["role"] in created or args.refresh]
        if to_render:
            print("Linking lanes to each other…")
        for lane in to_render:
            body = render_body(lane, spec, team, numbers, assign)
            for key in re.findall(r"^- \[x\] \*\*(\w+)\*\*", bodies.get(lane["role"], ""), re.M):
                body = body.replace(f"- [ ] **{key}**", f"- [x] **{key}**", 1)  # keep finished tasks ticked
            gh.run(
                ["issue", "edit", str(numbers[lane["role"]]), "--repo", repo, "--body-file", "-"], stdin=body
            )

    # 5. Branch protection
    if args.protect:
        print("Protecting main…")
        payload = json.dumps(PROTECTION)
        try:
            gh.run(
                ["api", "-X", "PUT", f"repos/{repo}/branches/main/protection", "--input", "-"], stdin=payload
            )
            print(
                "  main now requires a PR, 1 approval (re-approved after new commits), and the 'checks' CI job"
            )
        except RuntimeError as e:
            print(
                f"  ! could not protect main: {e}\n"
                "    Private repos on a free personal account can't use branch protection. Options:\n"
                "    make the repo public, use an account with GitHub Pro (free with the Student\n"
                "    Developer Pack), or rely on the team rule + the Claude Code guard hook."
            )

    print("Done.")


if __name__ == "__main__":
    main()
