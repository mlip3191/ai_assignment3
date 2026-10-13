# CLAUDE.md — AI Jukebox

Read `PROJECT.md` before doing anything. `docs/STARTER_PROMPT.md` is the team's build brief: the assignment's starter prompt, kept word for word, plus the team's additions. Treat it as the requirements for everything you build, and read it at the start of every session. It defines scope, ownership, the data model, client interfaces, the error model, the test plan, and the team workflow. Follow it; if a task requires deviating, say so and propose a PR to `PROJECT.md` instead of silently diverging.

## If someone asks what to do or how to get this running
Follow PROJECT.md §0: check §0.1 status, ask their goal and OS, and walk the matching path (§0.4 run the app, §0.5 teammate setup and building, §0.6 release lead) one step at a time. Use §0.7 and §0.8 for non-technical users. Never ask anyone to paste credentials.

## At the start of every session
1. A SessionStart hook puts an "AI Jukebox session check" block in your context. Before anything else, show the user the branch, the issue, and every warning in it.
2. **Essential: a new branch before any code change, for everyone.** If the user is on `main` or hasn't run `/start-session <task key>` in this session, stop and have them run it (it creates the task's branch) before editing any file. Never edit files or commit while on `main`; the guard hook blocks it.
3. Work on one task per session. Each person has one lane issue on GitHub (label `lane`) with a checklist of tasks (keys like B4). If the user asks for unrelated work, suggest finishing this task first. If a change touches files another lane owns (see the lane issue's "You own" list), keep it minimal and tag that owner as a reviewer.

## Hard rules
- Never read, print, log, create, edit, or commit `.env` or any credential. Use `.env.example` placeholders in docs and examples. The human manages `.env` by hand.
- **Only four AI models, each for its own job (PROJECT.md §7.0):** Qwen3.6-35B-A3B on 9001 for all text (titles, lyrics, cover prompts, DJ scripts); FLUX.2 klein 4B on 9006 for cover art; ACE-Step 1.5 XL Turbo on 9007 for music; Chatterbox Multilingual V3 on 9008 for DJ speech. Never port 9000.
- Never add or suggest any other model: no AI SDKs (OpenAI, Anthropic, Hugging Face, ...), no local models (transformers, torch, diffusers, TTS libraries), no `gr.load`, no browser speech synthesis, no other class endpoint, and no "fallback" model. On failure: show the §7.3 error and offer Retry.
- Model calls only through `jukebox/clients/<service>.py`. Feature modules use only their allowed clients: songs = qwen + acestep, art = qwen + flux, dj = qwen + chatterbox, player/UI = none. `python scripts/check_models.py` must pass. Never edit `scripts/model_policy.json` to make it pass.
- No paid services, no third-party music/lyrics/art/voice samples.
- Never write user uploads or voice references anywhere except `runtime/uploads/` (gitignored).
- Follow each service's documented request format exactly (PROJECT.md §7.1). If it says TBD, stop and ask; don't guess.
- Never commit on or push to `main`, force push, or merge PRs. **Someone else approves; the author merges.** A PR's author merges it themselves after a teammate approves. Reviewers never merge someone else's PR.
- **Every push is validated against who wrote the code.** The pre-push gate (`scripts/check_authors.py`) blocks commits authored by anyone other than the pusher unless the pusher validates them in their own terminal. Never try to answer or bypass that validation, and never rewrite commit authors. If it blocks, tell the user to push from their own terminal or have the author push.
- **Every commit needs a summary and the user's approval first.** Before any `git commit`, in any skill or session: give a brief summary of the changes (2–4 bullets), list every file being committed (`git diff --cached --stat`) and the commit message, say what is *not* being committed, and wait for a clear yes. No yes, no commit. The guard hook and settings also stop every commit for approval.
- **Every push, by anyone, goes through the skills, an agent review, and the user's approval, in that order.** Before any `git push`: (1) `/check` passed on the commit being pushed; (2) a separate review agent reviewed `git diff origin/main...HEAD` and every Blocking finding is fixed (`/finish-session` step 6 has the details); (3) you showed the branch, `git log origin/main..HEAD --oneline`, and `git diff origin/main...HEAD --stat`, and the user gave a clear yes. No yes, no push. The guard hook and settings stop every push for approval, and git's pre-push hook (`scripts/prepush.py`) re-runs the checks and blocks the push if any fail. Never use `--no-verify` or change `core.hooksPath`.
- Never claim a test passed, a feature works, or a result was observed unless you ran it in this session or the user told you they saw it. Audio and images need a human check.

## Conventions
- Python 3.11+, Gradio Blocks, httpx. Pin new dependencies to exact versions in `requirements.txt`.
- Service calls only through `jukebox/clients/*`; raise `ServiceError` (PROJECT.md §7.3) on any failure.
- UI code lives in `jukebox/ui/`; keep `app.py` thin.
- Long-running handlers are generators that `yield` status updates; buttons re-enable on success and failure.
- Look up tracks by `track_id`, never by list position.
- **Every change needs test cases.** Build the tests first, in `tests/` (mock services with `respx`), for every code, script, or hook change; only docs-only changes are exempt. Then run the **full** suite (`pytest -q`) so the change is checked against all existing test cases. The pre-push gate blocks pushes that change code without touching `tests/`, and runs every test on every push.
- Before finishing: run the `/check` skill (ruff, pytest, `scripts/scan_secrets.py`).

## macOS and Windows
The team develops on both, and the grader may use either. Everything you write must work on both.
- You run commands in bash on both systems (Git Bash on Windows). Use only `git`, `gh`, `python`, `pytest`, `ruff`, and repo scripts. No `open`, `start`, `xdg-open`, `sed -i`, `brew`, `winget`, or other OS-specific commands.
- Use `python`, not `python3`. The user activates the project venv before starting Claude Code, and the venv provides `python` on both OSes. If `python` is missing, tell the user to activate the venv (PROJECT.md §16.8) instead of working around it.
- In code: `pathlib.Path` for all paths; `encoding="utf-8"` for text files; binary mode for audio and images; no shell-outs from app code; no ffmpeg.
- New people-run scripts go in `scripts/*.py`. Don't add `.sh`/`.ps1` pairs. Only `run.sh` and `run.bat` are OS-specific.
- Temporary files you create (PR bodies, review drafts) go in `runtime/tmp/` (gitignored, exists on both OSes), never `/tmp` or `%TEMP%`.
- When you tell the user to run something in *their* terminal, give both the macOS and the Windows (PowerShell) form if they differ.

## Git and GitHub
- Branch: `<type>/<lane#>-<task>-<short-desc>` (feat, fix, docs, test, spike), e.g. `feat/2-b4-acestep-client`.
- Commit: `<type>(<area>): <summary> (<task>)`, with body line `AI-assisted: Claude Code; reviewed and tested by <user>`.
- Stage files by name; show `git status` before committing.
- PR body: `Part of #<lane#>` and `Task: <key>`, never `Closes #<lane#>` (that closes the whole lane). The task box ticks itself on merge.
- Ask before any GitHub write action (PR, comment, label, issue).

## Team skills
`/start-session <task key>`, `/check`, `/finish-session`, `/review-pr <pr#>`, `/log-test <TC-ID>`. See PROJECT.md §16.4.

## Working style
- Small diffs. After each step, run tests and show the diff.
- Explain what you changed and how you verified it, so the human can paste that into the PR, including what you did NOT test.
