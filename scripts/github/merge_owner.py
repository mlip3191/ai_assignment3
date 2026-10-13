#!/usr/bin/env python3
"""Check that a merged PR was merged by an owner of the files it changed.

Team rule (PROJECT.md section 9): someone else approves, then the OWNER of the changed files
merges. Owners come from .github/CODEOWNERS (later lines win). Files with no owner (tests/)
don't count. If no changed file has an owner, the PR's author may merge.

Run by .github/workflows/merge-by-owner.yml after every merge:
  python scripts/github/merge_owner.py --author A --merger M --files changed.txt
Exit code 1 if the merger isn't allowed.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"


def parse(text: str) -> list[tuple[str, list[str]]]:
    """CODEOWNERS lines -> [(pattern, [handles without @])], in file order."""
    rules = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append((pattern, [o.lstrip("@").lower() for o in owners]))
    return rules


def matches(pattern: str, path: str) -> bool:
    if pattern == "*":
        return True
    anchored = pattern.startswith("/")
    pat = pattern.lstrip("/")
    if pat.endswith("/"):
        return path.startswith(pat) if anchored else f"/{pat}" in f"/{path}"
    if anchored:
        return fnmatch.fnmatchcase(path, pat)
    return fnmatch.fnmatchcase(path, pat) or fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pat)


def owners_of(path: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    found: list[str] = []
    for pattern, owners in rules:
        if matches(pattern, path):
            found = owners  # later rules win
    return found


def allowed_mergers(changed: list[str], rules: list[tuple[str, list[str]]], author: str) -> set[str]:
    allowed = {o for path in changed for o in owners_of(path, rules)}
    return allowed or {author.lower()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", required=True)
    ap.add_argument("--merger", required=True)
    ap.add_argument("--files", required=True, help="text file with one changed path per line")
    args = ap.parse_args()

    rules = parse(CODEOWNERS.read_text(encoding="utf-8"))
    changed = [p.strip() for p in Path(args.files).read_text(encoding="utf-8").splitlines() if p.strip()]
    allowed = allowed_mergers(changed, rules, args.author)
    who = ", ".join(f"@{a}" for a in sorted(allowed))
    if args.merger.lower() in allowed:
        print(f"OK: merged by @{args.merger}, an owner of the changed files ({who}).")
        return 0
    print(f"NOT ALLOWED: merged by @{args.merger}. Only the owner(s) of the changed files may merge: {who}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
