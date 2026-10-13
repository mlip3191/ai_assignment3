---
name: start-session
description: Start a Claude Code work session on one task from your lane issue (e.g. B4). Syncs with GitHub, puts you on the right branch, loads the task and the matching PROJECT.md sections, restates its done criteria, and proposes a plan for approval. Run this first in every session.
argument-hint: [task-key e.g. B4]
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git fetch *) Bash(git branch *) Bash(git log *) Bash(gh issue view *) Bash(gh issue list *) Bash(gh pr list *) Bash(gh api user *)
---

# Start a work session

Task key: $ARGUMENTS

How the team tracks work: each person has **one lane issue** on GitHub (label `lane`), titled "Lane B: Song Generation" etc. Inside it is a checklist of **tasks** with keys like `B4`. Each task has a goal, "Needs" (other task keys), and "Done when" criteria. One session works on one task. One task = one branch = one PR.

Follow these steps in order. Do not edit any file until step 9 is approved.

## 1. Report the session check
The SessionStart hook put an "AI Jukebox session check" block in your context. Show the user the branch, the lane issue/task, and every warning in it. If it says `STOP`, stop here and tell the user to contact the release lead.
The block also shows the user's OS. Whenever you tell the user to run something in *their own* terminal (activating the venv, setup, editing `.env`), give the command for that OS (PROJECT.md §16.8). Commands you run yourself are the same on both.

## 2. Find the lane and the task
- Find the user's lane issue: `gh issue list --label lane --assignee @me --state open --json number,title`.
  If there's none, run `gh issue list --label lane --json number,title,assignees` and ask which lane is theirs.
- Read it: `gh issue view <lane#> --json number,title,body`.
- **If a task key was given**, find the line `- [ ] **<KEY>**` in that body. If the key belongs to another lane, say so and ask whether they really mean to work outside their lane.
- **If no key was given**, list the unticked tasks (`- [ ] **KEY**`) in order and suggest the first one whose "Needs" are all done (step 4). Ask the user to confirm.
- If the task is already ticked (`- [x]`), tell the user it's done and suggest the next one.
- One session = one task. If the user wants two, suggest finishing and opening a PR for the first.

## 3. Sync with GitHub
- `git fetch origin`
- `git status -sb`
- If there are uncommitted changes that belong to a different task/branch, stop and ask the user whether to commit them on that branch or stash them. Never discard changes.

## 4. Check the task's "Needs"
- For each key in "Needs": if it's marked `(#N)`, it lives in another lane issue. Run `gh issue view N --json body` and check whether `- [x] **KEY**` is ticked. Keys without `(#N)` are in this lane.
- If any are unticked, warn the user, name the owner (from the lane directory at the bottom of the issue), and ask whether to proceed against a stub/mock or pick a different task.

## 5. Get on the right branch
Branch name: `<type>/<lane#>-<task key lowercase>-<short-desc>`, where type is feat, fix, docs, test, or spike (e.g. `feat/2-b4-acestep-client`).
- If on `main`: `git switch main && git pull --ff-only`, then `git switch -c <branch>`.
- If this task's branch already exists locally: `git switch <branch>`. If `origin/main` has commits the branch doesn't, tell the user and offer `git pull origin main` (merge, not rebase). Resolve conflicts with the user, not silently.
- If on some other branch: stop and ask.

## 6. Load project context
Read `CLAUDE.md` and `docs/STARTER_PROMPT.md` (the build brief). Then read only the PROJECT.md sections this task needs: the task's "Refs" line, plus this table for the lane:

| Lane | Always read |
|---|---|
| A Platform & Release | §5, §6, §7 |
| B Song Generation | §6, §7.2, §7.3, §8.1 |
| C Cover Art, Samples & Evidence | §6, §7.2, §7.3, §8.2, §8.5 |
| D AI DJ & Launchers | §6, §7.2, §7.3, §8.3, §0.4 (launchers) |
| E Player, UX & QA | §6, §8.4, §12 |

Also read the §1 rows for the task's requirement IDs. If §7.1 still says TBD for a service this task calls, tell the user: do not invent request formats. Respect the lane's "You own" list: if the task needs changes to another lane's files, plan to keep them minimal and to tag that lane's owner as a reviewer.

## 7. Check the review queue
`gh pr list --search "review-requested:@me" --state open`. If anything is waiting, remind the user that reviews unblock teammates and offer to run `/review-pr <n>` first.

## 8. Session brief
- **Task:** KEY title (lane #N), checkpoint and due date
- **Goal:** from the task
- **Done when:** the task's criteria as a checklist
- **Requirement IDs:** from the task
- **Files likely touched:** paths (flag any outside the lane)
- **How we'll verify:** tests to write first, plus manual steps in the browser
- **Risks / open questions:** anything blocking, especially missing endpoint docs or unfinished "Needs"

## 9. Plan and wait
Propose a plan of at most 8 steps. **Step 1 is always building the test cases**: list each new or updated test in `tests/` (file and test name) and what it proves. Cover every "Done when" criterion and at least one failure path, and mock class services with `respx`. Write the tests first and run them to show they fail, then write the code until they pass. Every change needs test cases: code, scripts, and hooks alike. Only docs-only changes are exempt. Ask the user to approve or adjust the plan. Do not write code until they say go.
