#!/usr/bin/env python3
"""Check that every commit being pushed was written by the person pushing it.

Run by the pre-push gate (scripts/prepush.py). Compares each commit's author email with
your git identity (`git config user.email`). Commits already on origin/main are ignored.

If some commits were written by someone else, the push isn't silently allowed: you get a
validation step in your own terminal. You confirm the author agreed to you pushing them
(e.g. you paired). With no terminal to ask in (e.g. a push run by Claude Code), the push is
blocked and you're told to run it yourself.

  python scripts/check_authors.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def my_email() -> str:
    return git("config", "user.email").stdout.strip()


def foreign_commits(commits: list[tuple[str, str, str]], me: str) -> list[tuple[str, str, str]]:
    """Commits (sha, email, name) whose author email isn't mine (case-insensitive)."""
    me = me.strip().lower()
    return [c for c in commits if c[1].strip().lower() != me]


def commits_to_push() -> list[tuple[str, str, str]] | None:
    """(sha, author email, author name) for commits not yet on origin/main; None if no origin/main."""
    if git("rev-parse", "--verify", "-q", "origin/main").returncode != 0:
        return None
    out = git("log", "--no-merges", "--format=%h%x09%ae%x09%an", "origin/main..HEAD").stdout
    return [tuple(line.split("\t", 2)) for line in out.splitlines() if line.count("\t") == 2]


def ask_in_terminal(question: str) -> str | None:
    """Ask the human directly in their terminal. None if there's no terminal to ask in."""
    try:
        if os.name == "nt":
            fin, fout = open("CONIN$", encoding="utf-8"), open("CONOUT$", "w", encoding="utf-8")
        else:
            fin, fout = open("/dev/tty", encoding="utf-8"), open("/dev/tty", "w", encoding="utf-8")
    except OSError:
        return None
    with fin, fout:
        fout.write(question)
        fout.flush()
        answer = fin.readline()
    return answer.strip() if answer else None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    me = my_email()
    if not me:
        print('No git identity set. Run: git config --global user.email "you@example.com"')
        return 1
    commits = commits_to_push()
    if commits is None:
        print("No origin/main to compare with yet; skipping author check.")
        return 0
    foreign = foreign_commits(commits, me)
    if not foreign:
        print(f"All {len(commits)} commit(s) were written by you ({me}).")
        return 0

    lines = "\n".join(f"  {sha}  {name} <{email}>" for sha, email, name in foreign)
    print(f"These commits were written by someone other than you ({me}):\n{lines}")
    answer = ask_in_terminal(
        f"\nValidation: these commits were written by someone else:\n{lines}\n"
        "Did their author agree to you pushing them? Type 'yes' to continue: "
    )
    if answer is None:
        print(
            "Push blocked: this needs a person to validate it. Run the push yourself in your own "
            "terminal and answer the question, or ask the author to push their own commits."
        )
        return 1
    if answer.lower() != "yes":
        print("Push blocked: not validated.")
        return 1
    print("Validated by the pusher.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
