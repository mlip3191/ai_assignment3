---
name: review-pr
description: Review a teammate's pull request. Checks out the PR, runs the quality gate, reviews the diff against the lane task's done criteria, PROJECT.md interfaces, and the hard rules, then drafts review comments and manual test steps for the human reviewer. Never approves or merges.
argument-hint: [pr-number]
disable-model-invocation: true
allowed-tools: Bash(gh pr view *) Bash(gh pr diff *) Bash(gh pr list *) Bash(gh issue view *) Bash(git status *) Bash(git branch *) Bash(ruff check *) Bash(ruff format --check *) Bash(pytest *) Bash(pytest) Bash(python scripts/scan_secrets.py) Bash(python scripts/check_models.py)
---

# Review PR $ARGUMENTS

You help the human reviewer. The human decides whether to approve. You never approve, request changes, or merge on your own.

## 1. Load the PR
- `gh pr view $ARGUMENTS --json number,title,author,body,headRefName,files`
- `gh pr diff $ARGUMENTS`
- From the PR body, read `Part of #<lane#>` and `Task: <KEY>`. Open the lane issue (`gh issue view <lane#> --json body`) and copy that task's "Done when" criteria. If either line is missing, a blocking comment is: add them, or the task box won't tick on merge.

## 2. Check it out and run it
- Note the current branch. If the working tree has uncommitted changes, ask the user before switching.
- `gh pr checkout $ARGUMENTS` (ask first).
- Run everything in the `/check` skill.

## 3. Review checklist
Go through each and note findings with file:line:
- **Done criteria:** each one met? Is there evidence (test or described manual check)?
- **Interfaces:** matches PROJECT.md §6 data model and §7.2 client signatures? Any new shared shape that should have been a PROJECT.md change?
- **Models (PROJECT.md §7.0):** text only from Qwen (9001), covers only from FLUX (9006), music only from ACE-Step (9007), DJ speech only from Chatterbox (9008). No other model, SDK, hosted service, browser speech, or "fallback" model; `scripts/model_policy.json` unchanged unless the whole team agreed.
- **Hard rules:** no credentials or `.env` values; no port 9000; uploads only in `runtime/uploads/`; no bundled third-party content; dependencies pinned.
- **Errors (R6):** service failures become `ServiceError` with a user-facing message; UI buttons re-enable on failure; inputs preserved; retry offered where §7.3 says.
- **Status (R5):** long actions yield visible status.
- **Correctness:** tracks looked up by `track_id`; no race on shared library state; prompts ask for original content only.
- **Tests:** every changed code file comes with new or updated test cases in `tests/`; if not, that's **Blocking**. Do they test behavior, including at least one failure path? Would they fail if the feature broke? Does the full suite (`pytest -q`, all existing test cases) pass on this branch?
- **Scope:** anything unrelated to the task? Ask to split it out. Files outside the author's lane ("You own" list in their lane issue)? The owning lane's person should review those too.
- **PR body:** says `Part of #N`, not `Closes #N` (Closes would close the whole lane).

## 4. Draft the review
Write, for the human:
- **Blocking** (must fix before merge)
- **Should fix**
- **Nits**
- **Questions for the author**, including at least one "How did you verify X?"
- **Manual test steps** the human reviewer should do in the browser (exact clicks and expected results), especially for audio, covers, and the DJ.

## 5. Post only with permission
Ask the user whether to post the draft as a comment. If yes: write it to `runtime/tmp/review.md` and run `gh pr review $ARGUMENTS --comment --body-file runtime/tmp/review.md`. The approve/request-changes decision is the human's, made in GitHub after their own manual test. Remind the reviewer: **approve, but don't merge unless you own the changed files**. The owner of the changed files (`.github/CODEOWNERS`) merges.

## 6. Clean up
Switch back to the branch the user was on before step 2.
