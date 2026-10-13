---
name: check
description: Run the team quality gate (ruff lint, pytest, secret scan, class-models-only check, config check) and report results in a table. Use before committing, before opening a PR, and when reviewing a PR.
allowed-tools: Bash(python scripts/doctor.py) Bash(ruff check *) Bash(ruff format --check *) Bash(pytest *) Bash(pytest) Bash(python -m pytest *) Bash(python scripts/scan_secrets.py) Bash(python scripts/scan_secrets.py *) Bash(python scripts/check_models.py) Bash(python scripts/check_config.py)
---

# Quality gate

Run each check from the repo root. If a script doesn't exist yet (early in the project), mark it "not yet available" instead of failing.

1. `ruff check .`
2. `ruff format --check .`
3. `pytest -q` (exit code 5 means "no tests collected": report it as a warning, not a pass)
4. `python scripts/scan_secrets.py`
5. `python scripts/check_models.py` (fails if anything could use an AI model other than Qwen 9001, FLUX 9006, ACE-Step 9007, Chatterbox 9008, or if a feature uses the wrong one)
6. `python scripts/check_config.py` (only if it exists; it validates `.env` without printing secrets)
7. If any command above fails with "command not found" or the wrong Python, run `python scripts/doctor.py` and show the user its FAIL lines; they include the fix for their OS.

Report a table:

| Check | Result | Notes |
|---|---|---|

Rules:
- Never claim a check passed unless you ran it in this session and saw it pass.
- If something fails, show the relevant output lines and propose a fix. Only apply fixes the user approves. `ruff check --fix` and `ruff format` are fine to suggest; run them only if the user agrees.
- A secret-scan or model-check failure is always blocking. Never "fix" a model-check failure by editing `scripts/model_policy.json`; change the code to use the right class model.
- A secret-scan failure is always blocking. Do not print the matched value; point to the file and line.
- Also run `git status --porcelain` and flag any staged or untracked `.env`, `runtime/`, or audio files outside `samples/`.
