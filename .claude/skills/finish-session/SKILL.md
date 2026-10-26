---
name: finish-session
description: Close out a work session on one lane task. Runs the quality gate, checks the work against the task's done criteria, updates docs, commits, runs an agent review of the diff, asks the user to review and approve before pushing the branch (git re-runs the quality gate on push), and opens a PR (Part of the lane issue, Task key) with the right reviewer, or posts a progress note on the lane issue if the task isn't done.
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(gh issue view *) Bash(gh api user *) Bash(ruff check *) Bash(ruff format --check *) Bash(pytest *) Bash(pytest) Bash(python scripts/scan_secrets.py) Bash(python scripts/check_config.py)
---

# Finish a work session

## 1. Find the lane issue and task
The branch name is `<type>/<lane#>-<task key>-<desc>` (e.g. `feat/2-b4-acestep-client` → lane issue #2, task B4). Run `gh issue view <lane#> --json body` and reload that task's "Done when" criteria from the line `- [ ] **B4**` and its sub-bullets.

## 2. Run the quality gate
Do everything in the `/check` skill. If the secret scan fails, stop. If lint or tests fail, show the user and ask whether to fix now or open a draft PR.

## 2b. Test cases were built and the whole suite passes
- Every changed code file (`jukebox/`, `scripts/`, `.claude/hooks/`, `.githooks/`, `app.py`) must come with new or updated test cases in `tests/`. If any are missing, stop and build them with the user before going on. The pre-push gate blocks pushes without them.
- Run the **full** suite (`pytest -q`), not just the new tests, so the change is checked against every existing test case. Any failure, old or new, blocks the push.
- List the new or updated test names and what each proves. They go in the PR's "How it was tested".

## 3. Check the work against the task
- `git diff origin/main...HEAD --stat` and read the full diff.
- For every "Done when" criterion: **Met / Not met / Partly**, with evidence (test name, command output, or "user verified in browser"). Never mark something Met that nobody verified.
- List any changed files outside the lane's "You own" list (in the lane issue). Those need the owning lane's person tagged as an extra reviewer.
- Confirm against CLAUDE.md hard rules: no credentials, no port 9000, uploads only in `runtime/uploads/`, service calls only through `jukebox/clients/*`, tracks looked up by `track_id`, new dependencies pinned.

## 4. Docs that may need updating
Ask yourself, and tell the user which apply:
- PROJECT.md §2 decision log (did we decide something someone might question later?)
- PROJECT.md §7.1 endpoint table (did we learn a real request format, limit, or latency?)
- README section for this feature
- Prompt templates in `jukebox/prompts/` (record why a prompt changed)
Make doc edits only with the user's OK.

## 5. Commit (mandatory summary and approval, every time)
- Show `git status` and stage files by name. Never `git add -A` or `git add .` without the user reviewing the file list first.
- Before **every** `git commit`, tell the user, in plain words:
  - **Summary:** 2–4 bullets on what changed and why.
  - **Being committed:** every staged file (`git diff --cached --stat`), marked added / changed / deleted, plus the exact commit message.
  - **Not being committed:** anything left unstaged or untracked.
- Ask them to approve. Commit only after a clear yes. A vague or missing answer is a no. If anything changes after they approve (a file added, the message edited), summarize again and ask again.
- Message format: `<type>(<area>): <summary> (<TASK>)`, e.g. `feat(songs): add ACE-Step client with retries (B4)`.
- Add a body line: `AI-assisted: Claude Code; reviewed and tested by <user>`.

## 6. Push (only after the agents, the skills, and the user all sign off)
Every push, for everyone, goes through all of these in order. Skip none, even for a one-line change:
1. **Skills:** `/check` (step 2) ran in this session on the commit being pushed, and every check passed. If anything changed since, run it again.
2. **Agent review:** start a separate review agent (the Agent tool, `general-purpose`) on `git diff origin/main...HEAD`. Tell it to follow `.claude/skills/review-pr/SKILL.md` steps 3–4 and to report only Blocking / Should fix findings with file:line. Show the user its findings. Fix every Blocking finding (with the user's OK), recommit, and repeat steps 1–2.
3. **Human approval:** see below.

Never push without explicit approval. Before pushing:
- Show the user what will go to GitHub: the branch name, `git log origin/main..HEAD --oneline`, and `git diff origin/main...HEAD --stat`.
- Point out anything they should look at closely: files outside their lane, deleted files, config or dependency changes, and any done criteria still Not met / Partly.
- Ask them to review it and reply with a clear yes to push. A vague or missing answer is a no. If they want changes, make them, recommit, and ask again.

Only after that yes: `git push -u origin <branch>` (the guard hook blocks pushes to main, force pushes, and `--no-verify`). Git then runs the pre-push gate (`.githooks/pre-push` → `scripts/prepush.py`, the same checks as `/check`). If it fails, the push is blocked: show the user the output, fix, recommit, and go back to item 1. Their teammate's review and approval on the PR (step 7a) is still required before anything merges.

## 7a. If all done criteria are met: open a PR
- Reviewer: take the lane letter from the task key (D4 → D). In `.github/team.json`, look up that role and read its `reviewer` role letter, then use the `github` handle of the member in that reviewer role (D → C → Felipe). Go by the task's lane, not the user's login: one person can hold more than one lane. If the resolved reviewer is the PR's author (e.g. working a task in another lane), ask the user who should review. If files outside the lane changed, add that lane's owner as a second `--reviewer`, unless that owner is the PR's author (GitHub won't let authors review their own PR). If a lookup fails or a handle is blank, ask the user.
- Create it with `gh pr create --base main --title "<summary> (<TASK>)" --reviewer <handle> --body-file runtime/tmp/pr_body.md` (write that file with your file tool first; `runtime/` is gitignored and works on macOS and Windows), filling `.github/pull_request_template.md`:
  - `Part of #<lane#>` and `Task: <TASK>` on their own lines. **Never `Closes #<lane#>`**: that would close the whole lane. The task's checkbox ticks itself when this PR is merged.
  - Requirement IDs
  - What changed (bullets)
  - How it was tested: exact commands and results from this session, manual browser steps the user did
  - The task's "Done when" checklist with the Met/Partly status from step 3
  - Screenshots: leave a TODO for the user to paste if this touches UI
- Ask the user before running `gh pr create`.

## 7b. If not done: progress note
Ask the user before posting. Post on the lane issue with `gh issue comment <lane#> --body-file runtime/tmp/progress.md`, starting with the task key:
- Done this session
- Next steps
- Blockers / questions (tag the person who can unblock)
Optionally open a draft PR (`gh pr create --draft`) so teammates can see the work.

## 8. Hand-off summary
Tell the user: PR or comment link; that once a teammate approves it and CI is green, **the owner of the changed files merges it** (squash merge on GitHub; owners are in `.github/CODEOWNERS`, normally the user themselves; if they changed another lane's files, that owner may merge too), and that non-owners should never merge it; that the task box ticks itself when the PR merges (if it doesn't, run `python scripts/github/tick_task.py --issue <lane#> --task <TASK>`) and that they close the lane issue only when every box is ticked; anything they must verify by hand (UI, audio playback, screenshots), and the reminder that work only on their laptop doesn't count — it's pushed now.
