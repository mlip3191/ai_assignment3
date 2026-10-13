---
name: log-test
description: Record the result of a live test case (e.g. TC-05) from PROJECT.md §12.2 into docs/TEST_EVIDENCE.md, using only results the user actually observed or command output from this session.
argument-hint: [test-id]
disable-model-invocation: true
allowed-tools: Bash(gh api user *) Bash(git log *)
---

# Log test result: $ARGUMENTS

The README's test section is graded, and it must separate tested results from unchecked claims. You never invent or assume a result.

1. Find test case `$ARGUMENTS` in PROJECT.md §12.2. Copy its Feature, Input/steps, and Expected text. If the ID doesn't exist, ask whether to add a new row to §12.2 first.
2. Ask the user:
   - What exactly did you do? (inputs, settings, **OS (macOS/Windows)**, browser)
   - What actually happened? (include timings, error text, anything odd)
   - Pass, Fail, or Partial?
   - Screenshot or audio evidence path? (screenshots go in `docs/screenshots/`; never commit voice recordings)
   If the user says they haven't run it yet, stop: there is nothing to log.
3. Get the tester's handle with `gh api user -q .login`, today's date, and the current commit with `git log -1 --format=%h`.
4. Append a row to the table in `docs/TEST_EVIDENCE.md` (create the file with the header row if it's missing):

   `| ID | Feature | Input / steps | Expected | Actual | Status | Tester | OS | Date | Commit | Evidence |`

   Use the user's own words for "Actual". Don't polish a failure into a pass.
5. If the status is Fail or Partial, offer to open a bug issue (bugs are separate issues; mention the task key and lane issue that owns the broken part in its body): `gh issue create --label bug --title "<ID> fails: <short>" --body-file runtime/tmp/bug.md` (ask first). Ask which OS it happened on and add the `os:windows` or `os:macos` label if it only fails on one.
6. Remind the user to commit `docs/TEST_EVIDENCE.md` on their current branch.
