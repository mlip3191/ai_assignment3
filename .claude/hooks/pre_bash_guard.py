#!/usr/bin/env python3
"""PreToolUse hook for Bash (macOS, Windows Git Bash) and PowerShell (Windows): blocks
commands that break the team's hard rules. The same rules apply on both OSes; git and gh
commands are identical in every shell, and the .env check also catches PowerShell forms
such as `Get-Content .env` and `type .env`.

Exit code 2 blocks the command; stderr is shown to Claude as the reason.
Exit code 0 lets the normal permission flow continue.

Blocked:
  - Editing or writing any repo file while on main (everyone starts a new branch first)
  - Reading, printing, sourcing, copying or staging .env (but .env.example is fine)
  - Committing on main, or pushing to main
  - Force pushes, and pushes that skip the pre-push quality gate (--no-verify)
  - Turning off or redirecting the team git hooks (core.hooksPath)
  - Staging runtime/ or force-adding ignored files
  - Merging PRs (humans merge after review)
  - Any command that targets port 9000
  - Installing AI packages, or contacting AI providers, other than the four class models
    (lists come from scripts/model_policy.json)

Every other commit and push (on a feature branch) is not run automatically: the hook asks
the human to review and approve it first, in every permission mode.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ".env" as its own path token, not ".env.example" / ".envrc" / "my.env"
ENV_TOKEN = re.compile(r"(?:^|[\s/\\'\"=<>|;&(,`])\.env(?![\w.\-])")
PORT_9000 = re.compile(r":9000(?!\d)")
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
INSTALL = re.compile(
    r"\b(?:pip3?|python3?\s+-m\s+pip|py\s+-m\s+pip|uv\s+pip|uv|poetry|conda|pipx)\s+(?:install|add)\b(.*)"
)

# Fallback if the policy file can't be read: the most common ways to pull in another model.
FALLBACK_PACKAGES = {
    "openai",
    "anthropic",
    "transformers",
    "torch",
    "diffusers",
    "huggingface-hub",
    "gtts",
    "pyttsx3",
    "edge-tts",
    "elevenlabs",
    "replicate",
    "ollama",
    "litellm",
    "langchain",
}
FALLBACK_HOSTS = [
    "api.openai.com",
    "api.anthropic.com",
    "huggingface.co",
    "replicate.com",
    "api.elevenlabs.io",
]


def load_policy() -> tuple[set[str], list[str]]:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    try:
        pol = json.loads((root / "scripts" / "model_policy.json").read_text(encoding="utf-8"))
        return {norm_pkg(p) for p in pol["banned_packages"]}, [h.lower() for h in pol["banned_hosts"]]
    except Exception:
        return {norm_pkg(p) for p in FALLBACK_PACKAGES}, FALLBACK_HOSTS


def norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def current_branch(cwd: str | None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def in_repo(path: str, cwd: str | None) -> bool:
    """True if path is inside the git repo that cwd belongs to."""
    if not path:
        return False
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        ).stdout.strip()
        if not top:
            return False
        target = Path(path) if Path(path).is_absolute() else Path(cwd or ".") / path
        return target.resolve().is_relative_to(Path(top).resolve())
    except Exception:
        return False


def block(reason: str) -> None:
    print(f"Blocked by team guardrail: {reason}", file=sys.stderr)
    sys.exit(2)


def ask(reason: str) -> None:
    """Hand the command to the human for an explicit yes/no instead of running it."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Team rule: {reason}",
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def main() -> None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        # Read raw bytes: on Windows a piped stdin would otherwise use a legacy code page.
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except Exception:
        sys.exit(0)  # malformed input: don't interfere

    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd")

    if data.get("tool_name") in FILE_TOOLS:
        target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if in_repo(target, cwd) and current_branch(cwd) in ("main", "master"):
            block(
                "you are on main. Everyone starts a new branch before changing any file: run "
                "/start-session <task key> (it creates feat/<lane#>-<task>-<desc>), then make the change."
            )
        sys.exit(0)

    cmd = tool_input.get("command") or ""
    if not cmd:
        sys.exit(0)

    norm = " ".join(cmd.split())

    if ENV_TOKEN.search(norm):
        block(
            "commands that touch .env are not allowed for Claude. The human manages .env by hand. "
            "To check configuration, run `python scripts/check_config.py`, which never prints secrets."
        )

    if PORT_9000.search(norm):
        block("port 9000 must never be used for app requests (assignment rule H5).")

    banned_pkgs, banned_hosts = load_policy()
    m = INSTALL.search(norm)
    if m:
        for tok in m.group(1).split():
            if tok.startswith("-"):
                continue
            name = norm_pkg(re.split(r"[\[<>=!~;@]", tok.strip("'\""), maxsplit=1)[0])
            if name in banned_pkgs:
                block(
                    f"'{name}' is not allowed. The app may only use the four class models "
                    "(Qwen 9001, FLUX 9006, ACE-Step 9007, Chatterbox 9008); see PROJECT.md section 7.0."
                )
    low = norm.lower()
    for host in banned_hosts:
        if host in low:
            block(
                f"contacting {host} is not allowed; only the four class models may be used (PROJECT.md 7.0)."
            )

    if re.search(r"\bgh\s+pr\s+merge\b", norm):
        block("PRs are merged by a human after review, never by Claude.")

    if re.search(r"\bgit\s+push\b", norm):
        if re.search(r"(\s--force(?:-with-lease)?\b|\s-f\b|\s\+\S)", norm):
            block("force pushes are not allowed. Ask a human if history needs rewriting.")
        if re.search(r"\s--no-verify\b", norm):
            block("skipping the pre-push quality gate is not allowed. Fix what /check reports instead.")
        push_args = norm.split("git push", 1)[1].split()
        for tok in push_args:
            ref = tok.split(":")[-1].removeprefix("refs/heads/")
            if ref in ("main", "master"):
                block("pushing to main is not allowed. Push your feature branch and open a PR.")
        if current_branch(cwd) in ("main", "master"):
            block("you are on main. Create a branch (feat/<lane#>-<task>-<desc>) and push that instead.")
        ask(
            "every push needs your review and approval. Check the commits and changed files Claude "
            "showed you, then approve only if you want this on GitHub."
        )

    # The pre-push quality gate lives in .githooks; only reading it or turning it on is allowed.
    hooks_path = re.search(r"core\.hookspath\s*[= ]?\s*(\S*)", low)
    if hooks_path and ("--unset" in low or hooks_path.group(1) not in ("", ".githooks")):
        block("the team git hooks (core.hooksPath = .githooks) can't be changed or turned off.")

    if re.search(r"\bgit\s+commit\b", norm):
        if current_branch(cwd) in ("main", "master"):
            block("committing on main is not allowed. Switch to your feature branch first.")
        ask(
            "every commit needs your approval. Read Claude's summary of the changes and the list of "
            "files being committed, then approve only if that is exactly what you want committed."
        )

    if re.search(r"\bgit\s+add\b", norm):
        if re.search(r"\s(-f|--force)\b", norm):
            block("force-adding ignored files is not allowed.")
        if re.search(r"(?:^|\s)runtime(?:/|\s|$)", norm):
            block("runtime/ holds generated files and voice uploads and must never be committed.")

    sys.exit(0)


if __name__ == "__main__":
    main()
