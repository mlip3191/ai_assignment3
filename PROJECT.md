# AI Jukebox — Project Plan

MBAX 6418 · Assignment 3 · Team of 5
Submission due: **Fri 10/30/2026** (confirmed 10/20, §14 Q2)

This is the team's working plan. It is the single source of truth for scope, ownership, interfaces, schedule, and definition of done. Change it through a PR like any other file.

> **New here, or an AI assistant asked to explain this project?** Start at **§0**. It routes you to the right step-by-step path: running the app with no coding (§0.4), setting up to build it (§0.5), or creating the GitHub repo (§0.6).

---

## 0. Start here

### 0.1 Project status (release lead updates this at least daily)

| | |
|---|---|
| **Phase** | Build under way (as of 10/21). Merged: the five spikes (including the playback spike), config, the client layer, the library, the song prompts and pipeline, the cover prompt and service, and the DJ prompt and service. In review: the app shell, the queue, the real-artist screen, and the sample generator. Integration (A7) is not done. The original M0 and M1 dates have passed (the whole schedule moved +7 days on 10/20, §14 Q2). |
| **Is the app built?** | **No.** There is nothing to run yet. Path 1 below describes the finished app (v1.0) and is the contract the team builds to. |
| **What works today** | The repo scaffold: setup script, doctor, Claude Code skills and guardrails, GitHub automation, and CI (Ubuntu on every PR; Windows and macOS after each merge to `main`). |
| **Latest release** | none (will be the `v1.0` tag) |
| **Due date** | Fri 10/30/2026 (§14 Q2, answered 10/20) |
| **Blockers** | None on formats: §7.1 is filled for all four services (§14 Q3). Repo access (§14 Q5) is decided: the repo stays public until we submit; at submission the release lead makes it private and invites the professor (#42). |

### 0.2 Notes for AI assistants reading this file

If someone asks you to read this file and tell them what to do, follow these rules:

1. **Find out who they are and what they want**, using the table in §0.3. Ask if it's unclear. Also ask whether they're on **macOS or Windows**; most commands differ.
2. **Check §0.1 first.** If the app isn't built yet and they want to *run* it, say so plainly. Offer Path 2 (teammate setup) or Path 3 (release lead) instead of inventing steps.
3. **Follow the matching path exactly, one step at a time.** For each step, say what to do, the exact command or click for their OS, and what they should see if it worked. Wait for them to confirm before the next step. Don't skip or reorder steps.
4. **Assume no technical background** unless they show otherwise. Explain terms with the glossary (§0.8), and use the terminal primer (§0.7) the first time they need a terminal.
5. **Never ask them to paste their API key, `.env` contents, or `class-endpoints.txt`** into the chat. They type secrets only into `.env`, on their own machine.
6. **Don't invent anything this file marks TBD**, such as wait times (§0.4.6). Say it's not decided yet and who owns it.
7. **If a step fails,** check §0.4.7 (app users) or §16.9 (teammates) for that symptom first. If it isn't there, ask for the exact error text.
8. **For teammates who will build the app,** your job is Path 2. Get them set up, find their **lane** (one GitHub issue per person, §19) and its task checklist, and point them to the sections for their part (§0.5 step 4). The work itself happens in Claude Code with `/start-session <task key>`.

### 0.3 Pick your path

| I am… | I want to… | Go to | Time |
|---|---|---|---|
| Anyone (grader, classmate, teammate who doesn't code) | **Run the finished app** and try its features | **Path 1** (§0.4) | ~20 min + generation time |
| A teammate | **Set up my computer and build my part** of the app | **Path 2** (§0.5) | ~30 min setup, then per task |
| The release lead (role A) | **Create the GitHub repo**, the 5 lane issues, and releases | **Path 3** (§0.6) | ~45 min |
| A teammate doing QA or the deploy test | **Test the app the way the grader will** | Path 1, then record results with §12.2 | ~1 h |

---

### 0.4 Path 1: Run the finished app (no coding needed)

> **Available from v1.0.** Until then this section is the specification the team builds to (owners: D builds the launchers, E tests this path, C runs the non-coder usability test). Any change to the real app must be reflected here **and** in the README "Setup" section.

#### 0.4.1 What you need

- A computer running **Windows 10/11** or **macOS 13 or newer**.
- An internet connection that can reach the class servers. A VPN or the campus network was not needed when tested from a home Wi-Fi network (§14 Q7); a restrictive network could still differ.
- The **class credentials**: `class-endpoints.txt` from the course materials. Ask the instructors if you don't have it.
- The **app ZIP file**: from the Canvas submission (grader), or from the `v1.0` release on GitHub (teammates: the repo's **Releases** or **Tags** page → **Source code (zip)**).

#### 0.4.2 Install Python (one time)

| Windows | macOS |
|---|---|
| 1. Go to **python.org/downloads** and download Python 3.12 for Windows. | 1. Go to **python.org/downloads** and download Python 3.12 for macOS (the `.pkg` installer). |
| 2. Run the installer. **Tick "Add python.exe to PATH"** at the bottom of the first screen, then click **Install Now**. | 2. Open the `.pkg` and click through the installer. |
| 3. Check it: open **Terminal** (§0.7), type `py --version`, press Enter. You should see `Python 3.12.x`. | 3. Check it: open **Terminal** (§0.7), type `python3 --version`, press Enter. You should see `Python 3.12.x`. |

#### 0.4.3 Unzip the app

| Windows | macOS |
|---|---|
| **First, unblock the ZIP:** right-click it → **Properties** → at the bottom of the General tab, tick **Unblock** → **OK**. Without this, Smart App Control blocks `run.bat`. (No Unblock box means it's already unblocked.) | |
| Right-click the ZIP → **Extract All…** → set the destination to `C:\jukebox` → **Extract**. | Double-click the ZIP in Downloads. Drag the folder it creates into your home folder (Finder → Go → Home). |
| Open the extracted folder until you see `run.bat`, `README.md`, and `PROJECT.md`. That's the **app folder**. | Open the folder until you see `run.sh`, `README.md`, and `PROJECT.md`. That's the **app folder**. |

Don't put the app folder inside OneDrive or iCloud Drive (sync tools interfere), and don't run it from inside the ZIP without extracting.

#### 0.4.4 First start: add your credentials

| Windows | macOS |
|---|---|
| In the app folder, **double-click `run.bat`**. If Windows shows "Windows protected your PC", click **More info → Run anyway**. | Open **Terminal** (§0.7). Type `bash ` (with a space after it), drag **`run.sh`** from Finder into the Terminal window, and press **Enter**. |

On the very first start, the launcher:
1. Sees you have no settings file yet.
2. Creates one called `.env`.
3. Opens it for you in **Notepad** (Windows) or **TextEdit** (macOS).
4. Stops.

In that window:
- Fill in each value from `class-endpoints.txt`. Replace the placeholder text after each `=`, with no spaces or quotes around the value.
- **Save** the file and close the editor.
- **Don't rename it.** It must be exactly `.env`.
- This file stays on your computer. Never email it, paste it into a chat, or upload it.

#### 0.4.5 Start the app

Run the launcher again (double-click `run.bat`, or the `bash` + drag `run.sh` steps in Terminal). This time it:
1. Installs what the app needs. **The first time takes a few minutes**; you'll see lots of text scroll by. Later starts are quick.
2. Checks it can reach the class servers.
3. Opens your web browser at **http://127.0.0.1:7860**. That's the app. If the browser doesn't open, type that address into it yourself.

**Keep the launcher window open** while you use the app; closing it stops the app. To stop on purpose: on Windows, close the window; on macOS, close it or click in it and press **Ctrl+C**.

#### 0.4.6 Try the three features

- **Play the sample songs with the AI DJ**
  - The library already has **3 sample songs**, each with a title and cover.
  - Click **Play queue** (the browser needs this first click before it will play sound).
  - You'll hear the **DJ** introduce each song by name, then the song itself, automatically, one after another with no overlap.
  - Use **Pause/Play** and **Skip** at any time.
- **Generate your own song**
  - Open the **Generate** tab. Choose a **style**, a **mood**, a **duration**, and **Instrumental** or **Vocal**. Optionally add a theme ("road trip").
  - Click **Generate**. A status line shows each stage: writing lyrics, composing music, painting the cover. Typical wait: **TBD from M0 measurements (§7.1)**; it can be several minutes when the class servers are busy.
  - Vocal songs show their AI-written lyrics.
  - The new song appears in the library with its own cover. Add it to the queue to hear it, with a DJ intro.
- **Change the DJ's voice (optional)**
  - In **DJ voice**, upload a short **MP3 or WAV** recording of a voice. Length limits are shown on screen.
  - Later DJ intros use that voice. **Reset to default** switches back.

Songs you generate stay in the library **until you stop the app**. The 3 samples are always there.

#### 0.4.7 If something goes wrong (app users)

| What you see | What to do |
|---|---|
| Windows: "Smart App Control blocked a file that may be unsafe" when you start `run.bat` | Delete the app folder, unblock the ZIP (§0.4.3), and extract it again. Don't use **Run as administrator**, and don't turn Smart App Control off (it can't be turned back on without reinstalling Windows). |
| Windows: the black window flashes and disappears | Open Terminal in the app folder (§0.7), type `.\run.bat`, press Enter, and read the message. |
| "Python was not found" / `py` not recognized | Re-run the Python installer (Windows: tick **Add python.exe to PATH**), then open a **new** Terminal window. |
| The launcher says `.env` is missing or still has placeholders | Fill in `.env` as in §0.4.4 and save. On macOS, Finder hides files whose names start with a dot. Press **Cmd+Shift+.** to show them. |
| "The ... service rejected our credentials" | A value in `.env` is wrong. Re-copy it from `class-endpoints.txt` carefully (no extra spaces). |
| "... is unreachable" / "took too long" | The class servers may be busy, or your network may block them (a VPN was not needed from a home network, §14 Q7). Click **Retry**, or try again later. |
| Nothing happens for a long time after Generate | Check the status line; generation can take minutes. If it shows an error, use **Retry**. |
| No sound | Click anywhere on the page first (browsers block sound until you interact), and check your volume and output device. |
| Browser shows "can't connect" | The launcher window must still be open. Restart the launcher. |

---

### 0.5 Path 2: Teammate: set up and build your part

**Before you start, you need:**
- A GitHub account (free).
- **Access to Claude Code.** It needs a paid Claude plan (Pro or higher); the free plan doesn't include it. If you don't have one, tell A now (§14 Q8).
- The class credentials (`class-endpoints.txt`).

If you've never used a terminal, read §0.7 first. Then:

1. **Set up your computer:** §16.1, following the macOS or Windows column. You're done when `doctor.py` shows **0 FAILs**, and Claude Code shows the team skills and blocks `cat .env`.
2. **Learn the rules of the road (15 min read):**
   - §1 (what's graded)
   - §3 (who owns what)
   - §9 (GitHub workflow)
   - §16.2–16.6 (how every work session goes)
3. **Find your work:**
   - Your role letter is in §3.
   - You have **one lane issue** on GitHub: "Lane B: Song Generation", etc. Run `gh issue list --label lane --assignee @me`, or see §19.
   - Your lane issue holds your mission, the files you own, who's waiting on you, and a **checklist of tasks** (keys like `B4`), grouped by checkpoint date.
   - Work top to bottom. A task is ready when every task in its "Needs" line is ticked.
4. **Read the sections for your part:**

   | Lane | Read before your first task |
   |---|---|
   | A — Platform & Release | §5, §6, §7, §18 |
   | B — Song generation | §6, §7.2–7.3, §8.1 |
   | C — Cover art & samples | §6, §7.2–7.3, §8.2, §8.5, §11 |
   | D — AI DJ | §6, §7.2–7.3, §8.3, §16.8 (you own the launchers) |
   | E — Player, UX & QA | §6, §8.4, §12, §0.4 (you test it) |

5. **Do the work, one task per session, always on a new branch:**
   - **Essential: never change code on `main`.** Every task starts on its own new branch (§9). `/start-session` creates it, and Claude Code refuses to edit files on `main`.
   - Run through the §16.2 checklist, then `claude` → `/start-session <task key>` (e.g. `/start-session B4`).
   - Build in small steps and check by hand in the browser.
   - Finish with `/finish-session`.
6. **A task is done when** (its checkbox then ticks itself; close your lane issue when every box is ticked):
   - Its acceptance criteria are met with evidence.
   - CI is green.
   - Your reviewer approved.
   - You squash-merged the PR.
7. **Review a teammate's PR** when GitHub asks you to: `/review-pr <n>`, then test it yourself in the browser.
8. **Stuck?** Comment on your lane issue with the task key and what you're waiting for, tag the person, add the `blocked` label, and post in the team chat.

**Build order (critical path):**

```
A1 repo → C0 starter prompt → A2 config → A3 client base ─┬─ B3/B4 song clients → B5/B6 pipeline → B7 Generate tab ─┐
                                      ├─ C2/C3 cover → C4 cover service ──────────────────────────┤
spikes B1 B2 C1 D1 E1 start day 1 ────┼─ D2 TTS → D3 DJ → D4 voice upload ─────────────────────────┼─ A7 integration
                    E1 → E2 app shell ┴─ E3 queue → E4 player ─────────────────────────────────────┘      │
                                                     samples C5/C6, launchers D6, prefetch D5 ─── A8 rc1 ─ deploy tests E6
                                                                                                         → docs → A10 submit
```

**If you don't code:** you can still own real work. Claude Code writes the code; you decide what it should do, read its explanation of each change, test the result in the browser, and record evidence. The highest-value non-coding work is tied to tasks:
- Test runs (E6, E7, C8)
- Sample generation and its log (C5, C6)
- Screenshots and README sections (C7, B9, D7, E8)
- Docs verification (B10, D9)

Ask A to swap lanes or tasks if yours feel out of reach.

### 0.6 Path 3: Release lead (role A)

1. Do Path 2 step 1 (your own setup).
2. Follow **§18** in order: decisions → `team.json` → create the repo → invite → 5 lane issues → protect `main` → board → test PR → kickoff message.
3. Keep **§0.1 Project status** current, and run the daily check in §18 step 9.
4. At the end, follow the release steps in task A10 and §17 exactly, especially downloading the ZIP **for the exact submitted commit**.

### 0.7 Never used a terminal? (5-minute primer)

A **terminal** is a window where you type commands instead of clicking.

| | Windows | macOS |
|---|---|---|
| Open it | Start menu → type **Terminal** (or **PowerShell**) → Enter | Press **Cmd+Space** → type **Terminal** → Enter |
| Go to a folder | Type `cd ` (with a space), drag the folder from File Explorer into the window, press Enter | Type `cd ` (with a space), drag the folder from Finder into the window, press Enter |
| Paste a command | **Ctrl+V** (or right-click) | **Cmd+V** |
| Run it | **Enter** | **Enter** |
| Stop something running | **Ctrl+C** | **Ctrl+C** |
| Repeat a previous command | **Up arrow** | **Up arrow** |

**How to work in it:**
- Type or paste **one command at a time**, press Enter, and wait until the prompt comes back (the line ending in `>` or `%`) before the next one.
- **Read the last few lines** after each command. Words like `error`, `not found`, or `denied` mean the step failed: copy that text and ask for help. Never include your API key in what you paste.
- When this document shows a command in `code style`, type exactly that. Don't include surrounding quotes unless they're inside the code.
- When the prompt starts with **`(.venv)`**, the project's Python environment is active. Teammates need that before running `claude`.

### 0.8 Glossary

| Term | Meaning here |
|---|---|
| **Terminal / command line** | A text window for running commands (§0.7) |
| **Python** | The programming language the app is written in. You install it once. |
| **Virtual environment (`.venv`)** | A private folder of Python packages just for this project, so it doesn't clash with anything else on your computer. "Activate" it before working. |
| **Dependency / package** | A library the app needs. Listed in `requirements.txt`; installed automatically. |
| **Repository (repo)** | The project's folder of files, with full history, hosted on GitHub. |
| **Clone** | Download a repo to your computer with its history, so you can contribute. |
| **Git / GitHub** | Git tracks changes to files; GitHub hosts the shared copy, issues, and reviews. |
| **Issue** | A to-do item on GitHub. This team has **one issue per person**, called a **lane**. Bugs get their own issues. |
| **Lane** | One person's area of the project: their mission, the files they own, and a checklist of tasks. One GitHub issue each (§19). |
| **Task / task key** | One checklist item in a lane, like `B4`. One task = one work session (or a few) = one branch = one PR. Its box ticks itself when the PR merges. |
| **Checkpoint** | A deadline for a group of tasks (M0–M4, §10). The GitHub milestone is just one: "v1.0 submission". |
| **Branch** | Your own line of changes, kept apart from `main` until reviewed. Named `feat/<lane#>-<task>-<desc>`, like `feat/2-b4-acestep-client`. |
| **Commit** | A saved snapshot of changes with a message. Its **commit ID (SHA)** is a 40-character code that identifies it exactly. |
| **Push / pull** | Send your commits to GitHub / bring others' commits to your computer. |
| **Pull request (PR)** | A request to merge your branch into `main`. A teammate reviews it first. |
| **Review** | A teammate checks a PR (and tests it) before it's merged. Required for grading. |
| **Merge** | Combine an approved PR into `main`. |
| **CI** | Automatic checks GitHub runs on every PR (lint, secret scan, tests). |
| **Tag / release** | A name on one exact commit (e.g. `v1.0`); GitHub offers a ZIP of exactly that commit. |
| **`.env`** | Your private settings file holding the class credentials. Never shared, never committed. |
| **Credentials / API key** | The secret that lets the app use the class AI services. Lives only in `.env`. |
| **Endpoint / port** | The address of a class AI service. Each service has its own port (9001, 9006, 9007, 9008); port 9000 is forbidden. |
| **localhost / 127.0.0.1:7860** | "This computer". The app runs on your machine and you open it in your browser at that address. |
| **Gradio** | The Python toolkit that draws the app's web page. |
| **Claude Code** | The AI coding assistant the team uses in the terminal (`claude`). |
| **Skill / slash command** | A saved team routine you run in Claude Code, like `/start-session 14`. |
| **Hook / guardrail** | An automatic check that runs when Claude Code starts or runs a command; it blocks unsafe actions. |
| **Spike** | A short experiment to learn how something works before building it properly. |
| **Lint** | An automatic style and bug check on code (`ruff`). |

### 0.9 Map of this document

| § | What's there |
|---|---|
| 0 | Start here: status, paths, primer, glossary |
| 1 | Requirements checklist: every graded item → owner → test |
| 2 | Decision log (feeds the README's design-judgment section) |
| 3 | Team, roles, OS, review ring |
| 4–5 | Tech stack and repository layout |
| 6–7 | Data model, service integration, error model, configuration |
| 8 | Feature designs (songs, covers, DJ, player, samples) |
| 9 | GitHub workflow rules |
| 10 | Schedule and milestones |
| 11 | README outline (matches the assignment's documentation requirements) |
| 12 | Test plan and live test matrix |
| 13–14 | Risks; open questions |
| 15 | Starter prompt (verbatim) + team additions |
| 16 | Working with Claude Code: setup per OS, every-session routine, skills, guardrails, OS cheat sheet, troubleshooting |
| 17 | Definition of done |
| 18 | GitHub build-out guide (release lead) |
| 19 | The 5 lanes: who owns what, and every task |

---

## 1. Requirements checklist (from the assignment)

Every line here is graded or is a hard constraint. Each one maps to an owner and a test case.

### Hard constraints

| # | Constraint | Owner | Verified by |
|---|---|---|---|
| H1 | **All** text (titles, lyrics, cover prompts, DJ scripts) via **Qwen3.6-35B-A3B on port 9001**, and nothing else | B, C, D | `check_models.py`, TC-02, TC-05, TC-15 |
| H2 | Cover art **only** via **FLUX.2 klein 4B on port 9006** | C | `check_models.py`, TC-04, TC-15 |
| H3 | Music **only** via **ACE-Step 1.5 XL Turbo on port 9007** | B | `check_models.py`, TC-01, TC-02, TC-15 |
| H4 | DJ speech **only** via **Chatterbox Multilingual V3 on port 9008** | D | `check_models.py`, TC-05, TC-06, TC-15 |
| H5 | **Never** send app requests to port 9000 | A | `scripts/check_config.py` + code review |
| H6 | No paid services anywhere, including optional features | All | Code review |
| H7 | Core app works with class services + class credentials only | A | TC-10a/b (fresh deploy) |
| H8 | Credentials server-side only: not in GitHub, ZIP, browser code, logs, or docs | A | `scripts/scan_secrets.py`, TC-11 |
| H9 | No user uploads or voice-reference recordings in GitHub or the ZIP | D, A | `.gitignore` + TC-11 |
| H10 | No third-party music, lyrics, cover art, or voice samples bundled | C | Sample manifest review |
| H11 | Follow each service's documented request format | A | `scripts/check_endpoints.py` |
| H12 | **No AI model other than the four above, anywhere**, including other class endpoints, free or paid APIs, local models, browser speech, and fallbacks. No optional AI features. (Team rule, stricter than the assignment.) | All | `check_models.py` in CI, guard hook, review, TC-15 (§7.0) |
| H15 | **Each feature uses only its own model(s)**: songs = Qwen + ACE-Step, covers = Qwen + FLUX, DJ = Qwen + Chatterbox; player/UI call no models directly | B, C, D, E | `check_models.py` feature→client map (§7.0) |
| H13 | Starter prompt kept **verbatim**, critically reviewed, and additions written **before the build starts** | C (all review) | `docs/STARTER_PROMPT.md` diff vs. the assignment; C0 merged in M0 |
| H14 | Team checks the agent's work (not just accepts it) | All | Every PR has a human review, test evidence, and an "AI assistance" note (§9) |

### Core features

| # | Feature | Owner |
|---|---|---|
| F1 | Choose **style, mood, duration**; generate playable audio with ACE-Step; add to library | B |
| F1a | Support **instrumental** and **vocal** tracks | B |
| F1b | Vocal tracks get **AI-generated lyrics** (Qwen) | B |
| F2 | New **FLUX cover for every custom song**, shown with the correct track, reflecting the song's theme/style/mood | C |
| F3 | **Song-specific DJ commentary** written by Qwen, spoken by Chatterbox, **between queued songs** | D |
| F3a | Default DJ voice with no upload | D |
| F3b | Optional **MP3 or WAV** voice-reference upload customizes the DJ voice | D |

### App requirements

| # | Requirement | Owner |
|---|---|---|
| R1 | **3 ready-to-play sample songs** with titles and covers, pre-generated with class endpoints; any lyrics AI-generated | C |
| R2 | Newly generated songs join the playable library and **persist for the session** | A, B |
| R3 | **Play/pause** and **skip** controls | E |
| R4 | After playback starts, the queue **auto-advances**: DJ → song → DJ → song, **no overlap** | E |
| R5 | Visible **generation status** | B, C, D, E |
| R6 | **Understandable errors** and the ability to **recover** from failed requests | All (pattern owned by A) |
| R7 | **Usability** (graded): a first-time, non-technical user completes all 3 features from the README alone; the UI explains itself (labels, short help text, expected waits) | E, C |
| R8 | **Reliability** (graded): works across repeated use, including generating while music plays, several generations in a row, and service hiccups | D, E |

### Deliverables

IDs start with **DL** so they're never confused with the AI DJ issue keys (D1–D8).

| # | Deliverable | Owner |
|---|---|---|
| DL1 | `README.md` with setup & use, test results, design judgment, screenshots | A (editor), all contribute |
| DL2 | Explanation of how sample songs, lyrics, and covers were generated | C |
| DL3 | Shared GitHub repo (grader has access), commit ID, GitHub-downloaded ZIP of that commit | A |
| DL4 | Teammate installs from the extracted ZIP using only the docs and verifies all 3 features | E runs it, A fixes |
| DL5 | GitHub Issues + PRs; every member contributes meaningfully **and** reviews a teammate's PR | All |
| DL6 | Team verifies docs against the finished app and writes findings in its own words | All |
| DL7 | README "Setup and use" names each required item: **dependencies, additional software, endpoint configuration, how to supply credentials securely, launch instructions, how to exercise the three features, config examples without credentials** | A, D |
| DL8 | README test results: **inputs, expected, actual** for all 3 core features + **≥1 failure case**; **unresolved problems** listed; **completed tests clearly separated from unchecked claims** | E |
| DL9 | README design judgment: **one design choice justified with test evidence** + **one limitation/failure investigated and what we learned** | B, D |
| DL10 | Screenshots of the interface and each core feature, **showing no credentials** | C |
| DL11 | Canvas: repo link + **full 40-character commit ID** + **ZIP downloaded from GitHub for that exact commit** (tag `v1.0`, not the branch's latest) | A |
| DL12 | Repo **stays accessible through grading**: professor has access; no deleting, renaming or rewriting history until grades are posted. Making the repo private is allowed only at submission, once the professor (and any other grader) has been invited and can open it | A |
| DL13 | ZIP contains code, dependency info, config examples, docs, and the **actual sample audio + image files**, and **no** credentials, uploads, voice recordings, or files that exist only on a developer's machine | A, E |

---

## 2. Key decisions (decision log)

| Date | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 10/12 | **Gradio** (Blocks API) for the UI and server | All-Python, built-in audio/image/file components, server-side handlers keep credentials off the browser, generator functions give live status updates | Streamlit: full-script rerun on every interaction fights continuous playback. FastAPI+JS and Node+React: more code to write. |
| 10/12 | **Python venv + one launch script** for deployment | Fewest moving parts for the grader; no Docker requirement | Docker Compose |
| 10/12 | **Claude Code** as the team's coding agent | Team choice | Hermes. Confirmed acceptable 10/20 by the release lead (§14 Q1, A5). |
| 10/12 | **Split by feature**, 5 owners | Maps 1:1 to the graded features; clean PR boundaries | Split by layer |
| 10/12 | **No Git LFS** for sample assets | GitHub "Download ZIP" archives contain LFS *pointer files*, not the audio, unless a repo setting is enabled; that would silently break the grader's deploy | LFS |
| 10/12 | **Avoid an ffmpeg dependency** | One less system install for the grader; decode MP3/WAV with `soundfile` (wheels bundle libsndfile with MP3 support; verify in M0) | pydub/ffmpeg |
| 10/12 | **Shared Claude Code skills, hooks, and permissions committed in `.claude/`** | Everyone's agent follows the same session routine and the same guardrails; a guard hook blocks the most damaging mistakes (touching `.env`, pushing to main, port 9000) even when a human forgets | Each member configuring Claude Code individually |
| 10/12 | **Branch names carry the lane issue number and task key** (`feat/2-b4-acestep-client`) | Skills and the session hook find the lane and task automatically; PRs tie to the right checkbox | `feat/<area>-<desc>` |
| 10/12 | **One GitHub issue per person (5 "lanes")**, each holding that person's task checklist (49 tasks total), owned files, and hand-offs | Each person has one clear place to look and a lane nobody else works in; GitHub shows "3 of 10 tasks" progress per person; still one branch + one PR per task, so reviews stay small | 45 separate issues (too much to track); one issue per feature with shared ownership |
| 10/12 | **Task boxes tick automatically on merge** (`tick-task.yml` reads `Part of #N` + `Task: B4` from the PR) | Lane progress stays accurate without anyone remembering to update it | Manual ticking |
| 10/12 | **Backlog lives in `scripts/github/issues.json`** and is created by `bootstrap.py` | One reviewed source for lanes, tasks, and dependencies; re-runnable | Typing issues by hand |
| 10/12 | **Support macOS and native Windows equally** | The team (and probably the grader) uses both; anything that only works on one OS fails the independent-deploy test | Mac-only scripts; requiring WSL |
| 10/12 | **Windows uses PowerShell + Git for Windows; Claude Code runs commands in Git Bash** (its PowerShell tool is turned off in repo settings) | One set of commands, skills, and guardrails for everyone; Git Bash comes with Git, which everyone needs anyway | Separate PowerShell versions of every hook and skill |
| 10/12 | **People-run scripts are Python** (`setup_dev.py`, `doctor.py`, `bootstrap.py`, `scan_secrets.py`); only `run.sh`/`run.bat` are OS-specific | One script per job that behaves identically on both OSes and can be tested in CI | `.sh` + `.ps1` pairs (double the maintenance; PowerShell execution policy blocks downloaded `.ps1`) |
| 10/12 | **`.gitattributes` fixes line endings**; `.bat` gets CRLF, everything else LF | Prevents "works on Mac, breaks on Windows" from line endings. Verified that GitHub's ZIP applies the CRLF rule to `.bat`. | Per-person editor settings |
| 10/12 | **DJ speaks before every queued song, including the first** | Satisfies "commentary between queued songs" with a consistent pattern; the first intro opens the show. Each intro is specific to the song that follows it. | Commentary only after the first song |
| 10/12 | **Launchers create `.env` from the template on first run and open it in a plain-text editor** | Non-coders can't see dot-files in Finder, and Notepad can save `.env.txt`; this removes both traps (§0.4.4) | Telling users to copy the file themselves |
| 10/12 | **Generated songs live for the life of the server process** | Meets "remain available during the session"; simple and reliable; documented in README | Persisting to disk across restarts |
| 10/12 | **Hermes contingency** (not triggered: §14 Q1 was answered 10/20, Claude Code is acceptable): if the professor requires Hermes, use it with `docs/STARTER_PROMPT.md` to build the first version as the assignment describes. Commit its output through a PR, then keep the same issues, reviews, and tests; follow CLAUDE.md's rules by hand. | Keeps the plan valid either way | — |
| 10/12 | **Only the four class models, each locked to its feature, with no optional AI features and no fallback models** (§7.0), enforced by `model_policy.json` + `check_models.py` + guard hook + config port checks | The assignment grades use of the required class services; an AI agent will "helpfully" add an SDK or a browser-voice fallback unless something stops it | Allowing other class endpoints for optional features (permitted by the assignment, but adds risk for no grade) |
| 10/14 | **Player uses Option A:** one native `gr.Audio(autoplay=True)`. Its `.stop` event (end of media in Gradio 6.30.0) calls `advance()`, which returns the next file. **Skip** uses the same advance. A play token in the filename drops a late end event so Skip cannot double-advance. | E1 spike, Windows, Gradio **6.30.0** pinned in `requirements.txt`, `scripts/playback_spike.py` at http://127.0.0.1:7860. Adam heard three generated tones after one **Play queue** click. End event fired each time, autoplay continued after that click, Skip advanced once. On 2026-10-17, Chrome 155.0.8059.80 on Windows measured the browser gap from `ended` to the next `playing` as 148 ms and 125 ms. The status log for those same transitions, the end line to the next playing line, was 162 ms and 149 ms. The earlier 2.00 s figure was the clip length between successive end stamps. Skip while the next file is loading: untested; E4/E6 to cover. | Option B (custom HTML5 `<audio>` plus JS). The native end event was reliable, so the fallback was not built. |
| 10/18 | **`check_endpoints.py` compares model ids without their `org/` prefix** (`ACE-Step/x` matches `acestep/x`) | `class-endpoints.txt` spells the ACE-Step model `ACE-Step/acestep-v15-xl-turbo`, but the server lists `acestep/acestep-v15-xl-turbo`. Comparing the part after the last `/` accepts both spellings and still FAILs a port that serves a different model (A4, §7.1). | Exact string match (fails on the documented spelling); skipping the check for ACE-Step |
| 10/26 | **The custom DJ voice (D4) is one app-wide setting** (`dj.VOICE`), not per browser tab. Replacing or resetting it deletes the old recording from `runtime/uploads/`. Uploads are checked with **soundfile 0.14.0** (added to `requirements.txt` and `constraints.txt`): length from the header first, then a decode capped at 30 s. | The DJ clips the player reads (`dj_clips`) are already app-wide, and the app runs for one listener on one machine; keeping only the voice in use limits stored recordings (H9). The header-first check stops a long low-bitrate MP3 under 10 MB from being decoded in full. §8.3 asks for the soundfile check. | Per-session voice in `gr.State` (D5's prefetch would need each session's voice); keeping every upload; decoding the whole file. |

Add a row whenever the team makes a decision someone might later question. The README "Design judgment" section draws from this table.

---

## 3. Team & ownership

Fill in names, GitHub handles, and OS (macOS/Windows) at kickoff, here and in `.github/team.json`. Aim to have at least one Windows and one macOS person, so both deploy tests (TC-10a/b) can run.

| Role | Member | GitHub | OS | Owns | Reviews PRs from |
|---|---|---|---|---|---|
| **A — Platform & Release lead** | Michael Lippert | mlip3191 | macOS | Repo setup, config/credentials, shared HTTP client base and error model, library/job store, launch scripts, endpoint checks, secret scanning, README assembly, final ZIP & submission | E |
| **B — Song Generation** | Gunnar O'Connor | gunnaroc | TBD | F1, F1a, F1b: generation form, Qwen lyrics/title, ACE-Step client, song job pipeline | C |
| **C — Cover Art, Samples & Evidence** | Felipe | felcervino | TBD | F2: FLUX client, art-prompt builder, cover display & retry; R1/DL2: sample generation script, manifest, generation log; screenshots | D |
| **D — AI DJ & Launchers** | Dillon Smart | dilloncsmart | TBD | F3, F3a, F3b: Qwen commentary, Chatterbox client, voice upload validation, DJ prefetch | B |
| **E — Player, UX & QA** | Adam | afondale | TBD | R3, R4: queue, play/pause/skip, auto-advance; overall layout/UX; owns §12 test matrix and runs the independent ZIP deploy test (DL4) | A |

**Each role is one lane, and each lane is one GitHub issue.** The lane issue holds the mission, the files that person owns, the hand-offs others are waiting on, and the full task checklist. All five are summarized in §19. Stay in your lane: change another lane's files only with a small PR that tags its owner as a reviewer.

The review assignment is a ring (A→E→A, B→C→D→B), so each person reviews at least one teammate's PR. More reviews are fine; that is the minimum.

**Workload note:** A and E carry the cross-cutting load. If either falls behind, C (whose feature is the smallest) is the designated swing person.

---

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python **3.11+** (team installs 3.12) | Pin the exact minor version in README after the M0 spike |
| Developer OS | **macOS 13+** and **Windows 10/11** (native: PowerShell + Git for Windows) | Both are first-class; see §16.1 and §16.8 |
| UI + server | **Gradio** (Blocks) | Pin the exact version in `requirements.txt` (`gradio==X.Y.Z`). APIs differ across major versions. |
| HTTP client | `httpx` | Explicit timeouts on every call |
| Config | `python-dotenv` | Reads `.env` (gitignored) |
| Audio I/O | `soundfile`, `numpy` | Duration checks, voice-reference validation |
| Testing | `pytest`, `respx` (mock httpx) | Unit tests with mocked services; manual matrix for live tests |
| Lint/format | `ruff` | One config, run before PRs |
| Coding agent | Claude Code | Conventions in `CLAUDE.md` |

`requirements.txt` must pin **every** direct dependency to an exact version. The grader gets whatever the latest version is otherwise, and Gradio in particular changes between releases.

---

## 5. Repository layout

```
ai-jukebox/
├── app.py                      # Entry point: builds Gradio Blocks, launches on 127.0.0.1
├── jukebox/
│   ├── __init__.py
│   ├── config.py               # Loads/validates env vars; refuses port 9000; never logs secrets
│   ├── errors.py               # ServiceError + user-facing message mapping (§7.3)
│   ├── models.py               # Track, Job dataclasses (§6)
│   ├── library.py              # In-memory library; loads samples at startup
│   ├── jobs.py                 # Job tracking for long-running generations
│   ├── clients/
│   │   ├── base.py             # Shared httpx client: auth header, timeouts, retry policy, redacted logging
│   │   ├── qwen.py             # port 9001
│   │   ├── flux.py             # port 9006
│   │   ├── acestep.py          # port 9007
│   │   └── chatterbox.py       # port 9008
│   ├── services/
│   │   ├── songs.py            # Lyrics/title → music → save → trigger cover
│   │   ├── art.py              # Art prompt → FLUX → save → attach to track
│   │   ├── dj.py               # Commentary → TTS → cached clip per (track, voice)
│   │   └── player.py           # Queue state + "what plays next" logic
│   ├── prompts/
│   │   ├── lyrics.md           # System/user prompt templates (versioned, reviewed)
│   │   ├── title.md
│   │   ├── cover_art.md
│   │   └── dj.md
│   └── ui/
│       ├── generate_tab.py
│       ├── library_tab.py
│       ├── player_panel.py
│       └── dj_settings.py
├── samples/                    # COMMITTED: the 3 pre-generated songs
│   ├── audio/                  # sample_01.mp3 …
│   ├── covers/                 # sample_01.jpg …
│   ├── manifest.json           # Track records for the samples
│   └── GENERATION_LOG.md       # Exact prompts, lyrics, seeds, params, dates, who ran it
├── runtime/                    # GITIGNORED: created at startup
│   ├── generated/              # session songs, covers, DJ clips
│   └── uploads/                # voice references (never committed)
├── scripts/
│   ├── check_endpoints.py      # Hits all 4 services with tiny requests; prints PASS/FAIL per service
│   ├── check_config.py         # Validates .env (all vars set, no port 9000, URLs well-formed)
│   ├── generate_samples.py     # Produces samples/ using the app's own clients
│   ├── setup_dev.py            # One-time/after-pull setup: .venv, deps, .env template, doctor (macOS + Windows)
│   ├── doctor.py               # Machine health check with OS-specific fixes
│   ├── model_policy.json       # THE list of allowed models/ports and which feature may use which (§7.0)
│   ├── check_models.py         # Fails if anything could use a model other than the four class models
│   ├── scan_secrets.py         # Fails on key-like strings, .env, runtime/, stray audio, port 9000 (--zip for releases)
│   └── github/
│       ├── issues.json         # The backlog: 5 lanes, 49 tasks, owned files, hand-offs, dependencies
│       ├── lanes.py            # Renders lane issue bodies (used by the two scripts below)
│       ├── bootstrap.py        # Creates labels, the milestone, the 5 lane issues; invites team; protects main (§18)
│       ├── assignments.py      # Prints the §19 lane tables from issues.json + team.json
│       └── tick_task.py        # Ticks a task's box in its lane issue when its PR merges (run by CI)
├── tests/
│   ├── test_config.py
│   ├── test_clients.py         # respx-mocked: success, timeout, 401, 500, malformed body
│   ├── test_services.py
│   ├── test_player.py          # Queue ordering, skip, end-of-queue, DJ failure fallback
│   ├── test_guardrails.py      # Hook/guard tests; CI runs them on Ubuntu, Windows, and macOS
│   ├── test_lanes.py           # Backlog consistency (keys, dependencies, no cycles) and auto-tick parsing
│   └── test_check_models.py    # The model checker catches every kind of violation
├── docs/
│   ├── screenshots/
│   ├── STARTER_PROMPT.md       # Original prompt verbatim + team additions (§15)
│   └── TEST_EVIDENCE.md        # Live test results, written by /log-test
├── .claude/
│   ├── settings.json           # Team permissions + hooks (committed)
│   ├── hooks/
│   │   ├── run_py.sh           # Starts the hooks with a working Python (macOS python3; Windows python/py via Git Bash)
│   │   ├── session_start.py    # Prints the session check into Claude's context
│   │   └── pre_bash_guard.py   # Blocks .env access, pushes to main, force push, port 9000, PR merges
│   └── skills/                 # Team slash commands (§16.4)
│       ├── start-session/SKILL.md
│       ├── check/SKILL.md
│       ├── finish-session/SKILL.md
│       ├── review-pr/SKILL.md
│       └── log-test/SKILL.md
├── .github/
│   ├── team.json               # Role → name, GitHub handle, reviewer (fill in at kickoff)
│   ├── pull_request_template.md
│   ├── ISSUE_TEMPLATE/         # task.yml, bug.yml
│   └── workflows/
│       ├── ci.yml              # ruff + secret scan + pytest on every PR; Windows/macOS after merges
│       └── tick-task.yml       # On merge: tick the PR's task in its lane issue
├── .env.example                # Placeholders only
├── .gitattributes            # Line endings: LF everywhere, CRLF for .bat/.cmd/.ps1
├── .gitignore
├── CLAUDE.md                   # Conventions for Claude Code sessions
├── PROJECT.md                  # This file
├── README.md
├── pyproject.toml              # ruff + pytest config
├── requirements.txt            # App dependencies, exact pins
├── requirements-dev.txt        # pytest, respx, ruff
├── run.sh                      # macOS: `bash run.sh` creates .venv if missing, installs, checks .env, launches
└── run.bat                     # Windows: `.\run.bat` (PowerShell or cmd) does the same; no PowerShell scripts needed
```

### `.gitignore` must include

```
.env
.env.*
!.env.example
runtime/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.gradio/
*.log
```

---

## 6. Data model

All shared state flows through these shapes. Owner: **A**. Changes require a PR to this file.

### 6.1 Track

```python
@dataclass
class Track:
    id: str  # uuid4 hex; samples use "sample_01".."sample_03"
    title: str
    style: str  # genre/style tags, e.g. "lo-fi hip hop, jazzy keys"
    mood: str  # e.g. "mellow", "triumphant"
    theme: str | None  # optional user idea, e.g. "road trip"; feeds lyrics, cover, and DJ
    duration_s: int  # requested duration
    vocal: bool
    lyrics: str | None  # None for instrumentals
    audio_path: str  # path under samples/ or runtime/generated/
    cover_path: str | None  # None until cover succeeds → UI shows placeholder + retry
    cover_prompt: str | None  # the exact FLUX prompt used (for docs/evidence)
    source: Literal["sample", "generated"]
    seed: int | None
    created_at: str  # ISO 8601
```

### 6.2 Job

```python
@dataclass
class Job:
    id: str
    kind: Literal["song", "cover", "dj"]
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: str  # human-readable, e.g. "Writing lyrics…", "Composing music…"
    track_id: str | None
    error: str | None  # user-facing message (§7.3), never a raw traceback or secret
    started_at: str
    finished_at: str | None
```

### 6.3 Library rules

- Loaded at startup from `samples/manifest.json`, then extended with generated tracks.
- **Process-wide, in memory.** Generated files live in `runtime/generated/` for the life of the server. This satisfies "remain available during the session."
- Thread-safe (`threading.Lock`), because Gradio runs handlers concurrently.
- A track joins the library only when its **audio** succeeded. A missing cover does not block it (the UI shows a placeholder and a "Retry cover" button).
- **Stored paths** (`audio_path`, `cover_path`) are relative to the repo root and always use forward slashes (`Path.as_posix()`), whichever OS wrote them. The library converts Windows backslashes when a track is added, a cover is attached or the manifest is loaded, so samples generated on Windows still resolve on macOS. Use `Library.resolve(path)` to turn a stored path into the real file; don't build it yourself. No path may contain a `..` step. Generated tracks may use absolute paths; sample manifest entries must be relative.
- A sample in `samples/manifest.json` must have its audio file present when the manifest loads, and its cover file too if it lists a `cover_path` (a `null` cover is allowed and shows the placeholder), or loading fails (this catches a ZIP packaged without the images). A generated track only needs its audio; its cover can be attached later.

---

## 7. Service integration

### 7.0 The only AI models the app may use

The app uses **exactly four AI models, all class services, each for one job.** Nothing else generates or transforms content anywhere in the app, its scripts, or the sample generation. That includes paid APIs, free APIs, other class endpoints, local models, browser speech, and "temporary" fallbacks. This is a team rule, **stricter than the assignment** (which would allow other class endpoints for optional features): we have no optional AI features.

| Feature | Model (exact) | Port | Only client allowed | Used by (feature module) | URL / model settings |
|---|---|---|---|---|---|
| All text: song titles, lyrics, cover-art prompts, DJ scripts | **Qwen3.6-35B-A3B** | **9001** | `jukebox/clients/qwen.py` | `services/songs.py`, `services/art.py`, `services/dj.py` | `QWEN_BASE_URL`, `QWEN_MODEL` |
| Cover art images | **FLUX.2 klein 4B** | **9006** | `jukebox/clients/flux.py` | `services/art.py` | `FLUX_BASE_URL`, `FLUX_MODEL` |
| Music audio | **ACE-Step 1.5 XL Turbo** | **9007** | `jukebox/clients/acestep.py` | `services/songs.py` | `ACESTEP_BASE_URL`, `ACESTEP_MODEL` |
| DJ speech audio | **Chatterbox Multilingual V3** | **9008** | `jukebox/clients/chatterbox.py` | `services/dj.py` | `CHATTERBOX_BASE_URL`, `CHATTERBOX_MODEL` |

Which feature may call which model:

| Feature module | Qwen | FLUX | ACE-Step | Chatterbox |
|---|---|---|---|---|
| `services/songs.py` (F1) | ✅ title, lyrics | ❌ | ✅ music | ❌ |
| `services/art.py` (F2) | ✅ image prompt | ✅ image | ❌ | ❌ |
| `services/dj.py` (F3) | ✅ DJ script | ❌ | ❌ | ✅ speech |
| `services/player.py`, `jukebox/ui/*`, `app.py` | ❌ | ❌ | ❌ | ❌ (they call services, never clients) |

**Not allowed, ever** (enforced automatically, see below):
- **AI SDKs and hosted models:** OpenAI, Anthropic, Google, Hugging Face (including `gr.load`), Replicate, ElevenLabs, Groq, Together, Mistral, Cohere, OpenRouter, Azure/AWS AI, Ollama, LiteLLM, LangChain, and similar.
- **Local model libraries:** `transformers`, `torch`, `diffusers`, Whisper, Coqui TTS, Bark, a local Chatterbox package, and similar.
- **Other speech:** the browser's speech synthesis, `gTTS`, `pyttsx3`, `edge-tts`. The DJ voice comes only from Chatterbox.
- **Other class endpoints**, including port 9000 (§1 H5).
- **Fallbacks to anything else.** If a model fails, the app shows the §7.3 message and offers Retry:
  - Song failure: no song is made (no fake or synthesized audio).
  - Cover failure: the static, team-made placeholder image appears until Retry succeeds. The placeholder is drawn by the team, not generated by any model.
  - DJ failure: that DJ clip is skipped and the song plays. There is never a different voice.
  - Lyrics failure: the vocal song isn't made. There are no template or hand-written stand-in lyrics.

**How it's enforced:**

| Layer | What it does |
|---|---|
| `scripts/model_policy.json` | The single source of truth for the table above (models, ports, which feature may use which client, banned packages/imports/hosts). Changed only by a PR the whole team approves; Claude Code is blocked from editing it. |
| `scripts/check_models.py` | Runs in `/check` and CI on every PR, on Ubuntu, Windows, and macOS. Fails on:<br>- banned dependencies or imports<br>- other AI providers' URLs<br>- `gr.load` or browser speech<br>- network calls outside `jukebox/clients/`<br>- a client mentioning another service<br>- a feature importing a client it isn't allowed<br>- wrong or extra ports in URLs or `.env` |
| Claude Code guard hook | Blocks `pip install` / `uv add` of banned packages and any command contacting another AI provider |
| `config.py` (task A2) | Refuses to start unless each `*_BASE_URL` uses its own port (Qwen 9001, FLUX 9006, ACE-Step 9007, Chatterbox 9008), and never 9000 |
| `clients/base.py` (task A3) | Sends requests only to the four configured base URLs. Logs `service → host:port` (never headers) so a test run proves which models were called. |
| `scripts/check_endpoints.py` (task A4) | Confirms each port answers as the expected model, wherever the service reports its model name |
| Reviews | `/review-pr` and the PR template check "right model for the feature, no fallback model" on every PR |
| TC-15 | A full run whose request log shows only the class host on 9001/9006/9007/9008 |

(Claude Code is the team's *development* tool, not an app feature; this rule covers the app, its scripts, and the bundled samples. Whether Claude Code may be used at all was settled in §14 Q1: yes.)

### 7.1 Endpoint contracts

> Filled from `class-endpoints.txt` and the M0 spikes (B1, B2, C1, D1). Do not guess formats; H11 requires following each service's documented request format. If a service changes, update its row in a PR. Owner: **A**, with each feature owner verifying their service. Run `python scripts/check_endpoints.py` to confirm every port answers as its expected model (details under the table).

| Service | Port | Base URL env var | Method + path | Auth | Request body (key fields) | Response (key fields) | Typical latency | Timeout we set |
|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | 9001 | `QWEN_BASE_URL` | `POST /v1/chat/completions` (OpenAI-compatible, synchronous) | `Authorization: Bearer <key>` | `model` (`cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`), `messages`, `max_tokens`, `temperature`, **`chat_template_kwargs: {"enable_thinking": false}`** (thinking is on by default), optional `response_format` (JSON schema) | `choices[0].message.content`; reasoning arrives separately in `message.reasoning`; `content` is `null` if thinking used up `max_tokens` | ~1.5 s for ~200 tokens with thinking off; ~10 s with it on (B1, 10/15) | 90 s for now (`QWEN_TIMEOUT_S`); 30 s would be ample. See [docs/spikes/B1-qwen.md](docs/spikes/B1-qwen.md) |
| FLUX.2 klein 4B | 9006 | `FLUX_BASE_URL` | `POST /v1/images/generations` (OpenAI-style images API, synchronous) | `Authorization: Bearer <key>` | `prompt`, `model` (`black-forest-labs/FLUX.2-klein-4B`), `n` 1, `size` `"1024x1024"` (`WIDTHxHEIGHT`), `seed`, `response_format` `b64_json`, **`output_format` `jpeg`, `output_compression` 90** (the JPEG quality; about 0.15 to 0.3 MB per cover instead of 1.4 to 2 MB as compressed PNG; release lead's choice on #4, 10/20) | `data[0].b64_json`: base64 JPEG (starts `FF D8 FF`); `url` not implemented; prompt not rewritten (`revised_prompt` empty). Same seed gives the same image (checked for PNG) | ~2.2 to 2.5 s per 1024x1024 JPEG (C1 follow-up 10/16, C2 live call 10/19); single samples, empty queue | 120 s for now (`FLUX_TIMEOUT_S`). See [docs/spikes/C1-flux.md](docs/spikes/C1-flux.md) |
| ACE-Step 1.5 XL Turbo | 9007 | `ACESTEP_BASE_URL` | **Async job:** `POST /release_task` → poll `POST /query_result` `{"task_id_list": [id]}` → `GET /v1/audio?path=…` (the result's `file`) | `Authorization: Bearer <key>` | `prompt` (style tags), `lyrics` (`[verse]`/`[chorus]` tags; `"[Instrumental]"` or `""` for instrumental), `audio_duration` (docs: 10–600 s; 5 s was accepted), `audio_format` `mp3`, `inference_steps` 8, **`batch_size` 1** (default is 2), `seed` + `use_random_seed: false`; `model` is accepted, but any value still ran `acestep-v15-xl-turbo`, so check `dit_model` in the result instead. A fixed `seed` did **not** reproduce the same audio in the follow-up test | Submit: `data.task_id`. Poll: `data[0].status` integer 0 running / 1 done / 2 failed; `data[0].result` is a JSON **string** (parse again) with `file`, `metas.duration`, `seed_value`. Audio: MP3, 48 kHz, 128 kbps (~16 KB/s) | Server-reported 2–3 s for 30–60 s of audio; 4.8–7.2 s submit → file saved, empty queue (B2, 10/15) | 300 s for now (`ACESTEP_TIMEOUT_S`) until queueing under load is measured; needs a total-job deadline plus short per-poll timeouts. **Proposed:** never auto-retry the submit (conflicts with the §7.2 retry rule; raised for #9). See [docs/spikes/B2-acestep.md](docs/spikes/B2-acestep.md) |
| Chatterbox Multilingual V3 | 9008 | `CHATTERBOX_BASE_URL` | `POST /v1/audio/speech` (JSON, synchronous; returns one complete audio file). Never `POST /v1/voices` (it saves the voice on the shared server) | `Authorization: Bearer <key>` | `model` (`chatterbox-v3`), `input` (1–4,096 chars), `voice: "default"`, `language_id: "en"`, `response_format: "mp3"`; custom voice: add `ref_audio` (base64 WAV or MP3, ≤20 MB, ≤60 s, >0.5 s); delivery (optional, spec defaults 0.5): `exaggeration` (≥0; the client caps it at 2) and `cfg_weight` (0–1). The DJ sends 1.0 / 0.3, picked by ear in D3 | Audio bytes (`audio/mpeg`; WAV is 24 kHz mono 16-bit); errors are `{"error":{"message","type","param","code"}}` | ~40 words: 3.4–4.0 s default voice, 4.8–6.8 s custom voice → ~11.5 s of speech (D1, 10/16) | 120 s for now (`CHATTERBOX_TIMEOUT_S`); 60 s would be ample. See [docs/spikes/D1-chatterbox.md](docs/spikes/D1-chatterbox.md) |

**Base URLs and `/v1`.** `class-endpoints.txt` gives the Qwen and FLUX base URLs with a trailing `/v1` (seen when the author set up `.env` for the A4 live run, 10/19). `jukebox/config.py` removes that suffix (§7.4), so every `*_BASE_URL` is `scheme://host:port`, and the paths in the table are full paths that include `/v1` where the service needs it. `scripts/check_endpoints.py` relies on that: it always requests `/v1/models` from the stripped base.

**Exact model identifiers.** All four services take the one `CLASS_API_KEY`, sent as `Authorization: Bearer <key>` (§14 Q4).

| Service | `*_MODEL` value (set in `.env`) | What `GET /v1/models` lists | Which model actually ran |
|---|---|---|---|
| Qwen3.6-35B-A3B | `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` | the same | the `model` field of every response |
| FLUX.2 klein 4B | `black-forest-labs/FLUX.2-klein-4B` | the same | n/a (one model) |
| ACE-Step 1.5 XL Turbo | `ACE-Step/acestep-v15-xl-turbo` (as `class-endpoints.txt` spells it) | `acestep/acestep-v15-xl-turbo` (different prefix) | `dit_model` in each result: `acestep-v15-xl-turbo`. The request's `model` is ignored |
| Chatterbox Multilingual V3 | `chatterbox-v3` | the same | n/a (one model) |

`scripts/check_endpoints.py` sends `GET /v1/models` to each service (one small request each, one attempt with no retry, so a slow or failing service shows its true time; no generation) and prints PASS or FAIL with the latency. A service FAILs if it doesn't list its expected model, if a configured `*_MODEL` isn't one it offers (compared without the `org/` prefix, so the two ACE-Step spellings match), or if it errors. It assumes the OpenAI-style body `{"data": [{"id": ...}]}`. The author's live run on 10/19 (A4) passed all four services, so that shape is confirmed (about 160–230 ms each).

Questions to answer for each service in M0:

- Is the call synchronous, or does it return a job ID you have to poll?
- What is the max input size or duration (ACE-Step duration range, Chatterbox text length, voice reference length)?
- What error shape comes back on bad input versus overload?
- **Qwen specifically:** if it is an OpenAI-compatible server, check whether "thinking" output (`<think>…</think>`) appears in responses. If so, disable it per the server's docs and also strip it defensively in `qwen.py`. Thinking tokens will otherwise end up in lyrics and DJ scripts.

### 7.2 Client interface (stable regardless of wire format)

Each client exposes exactly one main function. Feature code only calls these, so a wire-format change touches one file.

```python
# jukebox/clients/qwen.py
def chat(messages: list[dict], *, max_tokens: int = 600, temperature: float = 0.8) -> str: ...


# jukebox/clients/flux.py
def generate_image(
    prompt: str, *, width: int = 1024, height: int = 1024, seed: int | None = None
) -> bytes: ...


# jukebox/clients/acestep.py
def generate_music(
    *, tags: str, lyrics: str | None, duration_s: int, seed: int | None = None
) -> tuple[bytes, str]:
    """Returns (audio_bytes, file_extension)."""


# jukebox/clients/chatterbox.py
def speak(
    text: str,
    *,
    voice_ref_path: str | None = None,
    language: str = "en",
    exaggeration: float | None = None,  # None = not sent (service default)
    cfg_weight: float | None = None,  # None = not sent (service default)
) -> tuple[bytes, str]: ...
```

Shared behavior in `clients/base.py` (owner A, built first):

- **Only the four configured base URLs** (`QWEN_BASE_URL`, `FLUX_BASE_URL`, `ACESTEP_BASE_URL`, `CHATTERBOX_BASE_URL`) can be called; any other URL raises `ServiceError(kind="config")`. Each client is bound to its own service and puts its `*_MODEL` value in the request when the service's format has a model field.
- Logs one line per request: `service → host:port, status, duration` (never headers or bodies). This log is TC-15's evidence.

- Auth header from config. **Never** logged; the key, `Authorization` and any key-like value are scrubbed from every record on any `jukebox.*` logger, so a plain `logging.getLogger(__name__)` in a client or service is safe.
- Explicit connect/read timeouts per service (read timeout for ACE-Step will be long; set it from M0 measurements plus margin). `request(..., timeout=...)` overrides the timeout for one request (for example short polls inside a long job).
- Retry **once** with backoff on timeouts, connection errors, and 502/503/504. No retry on 4xx. `request(..., retry=False)` makes exactly one attempt: use it for a call that starts work on the shared servers, where a timed-out request may already have been accepted (ACE-Step `/release_task` must never run twice).
- Converts every failure into `ServiceError(service, kind, detail)`. HTTP 404 maps to `config` (a wrong path or base URL, not something the user typed). A client where 404 can legitimately mean "not found" (a stale ACE-Step task or audio file, a missing Chatterbox voice reference) **should** catch the `config` error for that call and raise its own kind, so the user is not told to check the settings.

### 7.3 Error model (R6)

```python
class ServiceError(Exception):
    service: Literal["qwen", "flux", "acestep", "chatterbox"]
    kind: Literal["config", "auth", "timeout", "unavailable", "bad_request", "bad_response"]
    detail: str  # developer detail, for logs only (already redacted)
```

User-facing messages (in `errors.py`, owner A). The UI shows these, never raw exceptions:

| kind | Message pattern | Recovery offered |
|---|---|---|
| config | "The {service} endpoint isn't configured. Check `.env` against `.env.example`." | — (startup check catches a malformed URL or the wrong port; an HTTP 404 at run time also lands here: it means a wrong path or base URL, which the startup check cannot see) |
| auth | "The {service} service rejected our credentials. Check the API key in `.env`." | Fix and restart |
| timeout | "The {service} service took too long to respond. The class servers may be busy." | **Retry** button |
| unavailable | "The {service} service is unreachable right now." | **Retry** button |
| bad_request | "{service} couldn't process that request: {safe reason}." | Edit inputs and resubmit |
| bad_response | "{service} returned something unexpected." | **Retry** button |

Recovery rules:

- A failed generation never leaves the UI stuck. Buttons re-enable, the status shows the message, and the form keeps the user's inputs.
- Cover failure keeps the song; it shows a placeholder plus **Retry cover**.
- No failure ever switches to a different model or a non-AI stand-in (§7.0).
- DJ failure never stops music. The player skips the DJ clip, plays the song, and shows a non-blocking notice ("DJ unavailable for this track").

### 7.4 Configuration

`.env.example` (commit this; placeholders only):

```dotenv
# Copy to .env and fill in from class-endpoints.txt. Never commit .env.
# Variable names are final (PROJECT.md §7.1 is filled in).
#
# The app may use ONLY these four class models (PROJECT.md §7.0):
#   Qwen3.6-35B-A3B             port 9001  text: titles, lyrics, cover prompts, DJ scripts
#   FLUX.2 klein 4B             port 9006  cover art
#   ACE-Step 1.5 XL Turbo       port 9007  music
#   Chatterbox Multilingual V3  port 9008  DJ speech
# Each *_BASE_URL must use its own port. Port 9000 is never used.
# Enter only http://host:port. If class-endpoints.txt shows a trailing /v1, leave it out (it is removed if kept).
CLASS_API_KEY=your-class-api-key-here
QWEN_BASE_URL=http://CLASS_HOST:9001
FLUX_BASE_URL=http://CLASS_HOST:9006
ACESTEP_BASE_URL=http://CLASS_HOST:9007
CHATTERBOX_BASE_URL=http://CLASS_HOST:9008

# Model names exactly as class-endpoints.txt gives them (only needed if a service's request format has a model field)
# Qwen: the AWQ 4-bit build of Qwen3.6-35B-A3B, which is how the class server on 9001 names it (B1 spike).
QWEN_MODEL=cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit
FLUX_MODEL=black-forest-labs/FLUX.2-klein-4B
# ACE-Step: the spelling class-endpoints.txt uses. The server lists it as acestep/acestep-v15-xl-turbo; either works.
ACESTEP_MODEL=ACE-Step/acestep-v15-xl-turbo
CHATTERBOX_MODEL=chatterbox-v3

# Optional tuning
ACESTEP_TIMEOUT_S=300
FLUX_TIMEOUT_S=120
CHATTERBOX_TIMEOUT_S=120
QWEN_TIMEOUT_S=90
APP_HOST=127.0.0.1
APP_PORT=7860
```

(Adjust variable names once §7.1 shows whether the services share one key or use separate ones.)

`config.py` must, on startup:

- Fail fast with a clear message if any required variable is missing.
- **Refuse to start if any service URL uses port 9000** (H5), **or if any `*_BASE_URL` doesn't use its own port**: Qwen 9001, FLUX 9006, ACE-Step 9007, Chatterbox 9008 (H1–H4, §7.0).
- Refuse unknown `*_BASE_URL` variables (no fifth AI service).
- A `*_BASE_URL` is `scheme://host:port` only; each client appends its own request path to it. `class-endpoints.txt` lists some URLs with a trailing `/v1`: that one lowercase suffix is removed automatically (and `check_config.py` says so on that row), because the request paths already include `/v1` where a service needs it (it is not uniform: ACE-Step's `/release_task` has none). Any other path, a query or a fragment is `INVALID`. `str(config)` shows the host as `****` and keeps the port.
- Never print key values. Show `CLASS_API_KEY=****` (set) or `(missing)`.

---

## 8. Feature designs

### 8.1 F1 — Song generation (owner B)

**UI (Generate tab):**

- Style: dropdown of ~10 genres plus free-text "extra style tags."
- Mood: dropdown (e.g. upbeat, mellow, dark, triumphant, dreamy, melancholy).
- Duration: slider. Set min/max from the ACE-Step limits found in M0; default ~60 s to keep generation time and file size reasonable.
- Type: radio, **Instrumental / Vocal**.
- Optional: "Song idea / theme" text box (feeds lyrics and cover).
- **Generate** button, a status line, and the result card (title, cover, play-now / add-to-queue).

**Models:** Qwen (title, lyrics) + ACE-Step (audio). Nothing else.

**Pipeline** (a Gradio generator function that `yield`s status at each stage):

1. Validate inputs and build ACE-Step `tags` from style + mood.
2. Qwen → **title** (always) and **lyrics** (vocal only). Ask for JSON output (`{"title": ..., "lyrics": ...}`), parse it, and fall back to a regex/plain-text parse if the JSON is malformed.
3. ACE-Step → audio. Instrumental: use the instrumental mode or lyrics marker from the docs. Vocal: pass the lyrics in the structure ACE-Step expects (likely `[verse]` / `[chorus]` section tags; confirm in docs).
4. Save the audio to `runtime/generated/{track_id}.{ext}` and add the Track to the library.
5. Trigger the cover job (§8.2). The song is playable immediately; the cover appears when ready.

**Lyrics prompt rules** (in `prompts/lyrics.md`):

- Original lyrics only. Never quote or imitate existing songs, and never mention real artists.
- Match the requested mood, style, and theme.
- Length scaled to duration (roughly 2 sections per 30 s; tune in testing).
- Output only the requested JSON, no commentary.

**Input safeguard:** if the user types an artist name into style tags ("in the style of <artist>"), strip it or warn. The goal is to avoid producing anything that could be read as imitating real artists' work.

**Done when:** an instrumental and a vocal track each generate from the UI, play in the browser, appear in the library, and failures show §7.3 messages with inputs preserved.

### 8.2 F2 — Cover art (owner C)

**Pipeline:**

1. Qwen writes a **FLUX image prompt** from title + style + mood + theme (+ a lyrics summary if vocal). It describes visual subject, palette, composition, and art style.
2. Append fixed suffixes: square album cover, **no text, no letters, no logos, no real people**. (Image models render text badly, and this keeps the output clear of trademarks.)
3. FLUX → image (JPEG, quality 90; #4, 10/20), saved to `runtime/generated/{track_id}.jpg`. The track's `cover_path` and `cover_prompt` are updated.
4. The UI shows the cover in the library row, the now-playing panel, and the queue, always looked up by `track_id`, never by list position. This is how you guarantee "displayed with the correct track."

**Models:** Qwen (image prompt) + FLUX (image). Nothing else.

**Recovery:** a placeholder image (an original, team-made SVG/PNG, committed; drawn by a person, not generated by any model) plus a **Retry cover** button per track.

**Done when:** every new song gets a unique cover that visibly reflects its mood/style, and that cover stays attached to the right track after several generations and reorderings.

### 8.3 F3 — AI DJ (owner D)

**Models:** Qwen (script) + Chatterbox (speech). Nothing else: never the browser's speech synthesis or any other TTS, even as a fallback.

**When commentary plays:** before each song in the queue (the "intro" model). Example: the queue is [S1, S2, S3] → DJ(S1) → S1 → DJ(S2) → S2 → DJ(S3) → S3.

**Commentary content** (in `prompts/dj.md`):

- 2–3 sentences, ~30–50 words. This keeps TTS fast and the listener isn't waiting long.
- Must be **song-specific**: reference this track's title, style, mood, and theme, and optionally a smooth transition from the previous track.
- Radio-DJ persona, no invented facts about real artists, no lyrics quoted at length.
- Plain text only, no stage directions or emojis (TTS would read them aloud).

**Voice:**

- Default: Chatterbox's built-in voice, no upload needed (F3a).
- Custom: a `gr.File` or `gr.Audio` upload restricted to **.mp3/.wav** (F3b).
  - Validate the extension, check it decodes with `soundfile`, and enforce a max size (e.g. 10 MB) and a duration window (set from Chatterbox's docs, e.g. 5–30 s).
  - Store it in `runtime/uploads/` under a random filename. **Never** in the repo.
  - Show "Custom voice active" with a **Reset to default** option.
  - Rejected uploads show why ("Only MP3 or WAV files are supported"; "Clip must be between X and Y seconds").

**Latency strategy (critical for R4):** **prefetch.** When a song starts playing, immediately generate the DJ clip for the *next* queued song in the background. Cache clips by `(track_id, voice_id)`. Changing the voice invalidates the cache.

**Done when:** with 3+ tracks queued, each transition plays a distinct, track-specific spoken intro in the default voice; uploading a valid WAV/MP3 changes the voice on subsequent intros; an invalid upload is rejected clearly; a forced Chatterbox failure doesn't stop the music.

### 8.4 R3/R4 — Player & queue (owner E)

**Queue model** (`services/player.py`, pure Python, unit-tested without Gradio):

- `queue: list[track_id]` plus `current: PlayItem | None`, where `PlayItem = {kind: "dj" | "song", track_id, audio_path}`.
- `next_item()` returns DJ(next) if its clip is ready, otherwise the song directly (never block on DJ).
- Actions: `enqueue(track_id)`, `play_now(track_id)`, `skip()`, `clear()`.
- Skip during a DJ clip jumps to that clip's song. Skip during a song moves to the next DJ/song.
- At end of queue: stop and show "Queue finished" (optionally a "Loop library" toggle).

**Why no overlap is structurally guaranteed:** a single audio element plays exactly one source at a time. The DJ and the music are never separate simultaneous players.

**Playback spike — M0, decides Option A vs B:**

- **Option A (preferred): native Gradio.** One `gr.Audio(autoplay=True)` "now playing" component. Its end-of-playback event (`.stop` in recent Gradio versions; confirm against the pinned version's docs) calls `advance()`, which returns the next file. Play/pause come from the native controls; **Skip** is a `gr.Button` that calls `advance()`.
  - Spike must confirm: (1) the end event fires reliably; (2) autoplay works when the source changes after the user's first click; (3) skipping mid-load doesn't double-advance; (4) there is no noticeable gap.
- **Option B (fallback): custom HTML5 player.** A `gr.HTML` with an `<audio>` element and JS (injected via the Blocks `head`/`js` parameter) that listens for `ended` and fetches the next item from a hidden Gradio component or API. More code, but full control.
  - Audio files must be servable by Gradio. Check `allowed_paths` in `launch()` for `samples/` and `runtime/`.

The spike result is in §2 (10/14): **Option A**, Gradio 6.30.0. It is also a strong candidate for the README's "design choice justified by testing" section.

**Browser autoplay:** browsers block audio until the user interacts. The first play must come from a click on **Play queue**. Document this in the README.

**UI layout:**

- Left: Generate tab / Library tab.
- Right (always visible): now-playing (cover, title, "DJ speaking…" or "Now playing"), controls, up-next list with covers, DJ voice settings.
- Every long action shows a status line. Disable the button while running; re-enable on success or failure.

**Done when:** pressing Play with 3 samples queued plays DJ→S1→DJ→S2→DJ→S3 with no overlap and no manual clicks; pause/resume and skip work in both DJ and song segments; a DJ failure falls back to the song.

### 8.5 R1/DL2 — Sample songs (owner C)

- `scripts/generate_samples.py` uses the app's own clients and services (same code path as live generation), so the samples double as an end-to-end test.
- Three deliberately different samples to show range:
  1. Instrumental, e.g. lo-fi / mellow, ~60 s
  2. Vocal, e.g. upbeat pop / summery, ~60 s
  3. Vocal, e.g. cinematic or folk / melancholy, ~60 s
- Fixed seeds so the samples can be reproduced.
- Generated **only** through the app's own Qwen, FLUX, and ACE-Step clients. `GENERATION_LOG.md` records the model name and port for every call.
- Output: `samples/audio/`, `samples/covers/`, `samples/manifest.json`, and `samples/GENERATION_LOG.md`. The log records, for each sample, the date, who ran it, the exact inputs, the Qwen prompts, the generated lyrics in full, the FLUX prompt, seeds, model/port, and the generation time.
- Keep each audio file small (prefer MP3 if ACE-Step offers it, ≤ ~5 MB). The repo and the ZIP must stay manageable without LFS.
- Generate samples **only after** the clients and prompts are stable (target Mon 10/26). Regenerate if prompts change materially.

---

## 9. GitHub workflow

Setup is a one-time job for the release lead (A); the step-by-step guide is **§18**. This section is the day-to-day rules for everyone.

**Five lane issues, one per person.** Each lane issue (label `lane`) lists that person's tasks as checkboxes with keys like `B4`, grouped by checkpoint (M0–M4). Lanes are summarized in §19.

> **Essential rule, for everyone: start a new branch before you change any code or file.** Never work on `main`. Every task begins with a fresh branch off the latest `main` (`/start-session <task key>` creates it for you; without Claude: `git switch main`, `git pull`, `git switch -c <branch name>`). This is enforced: Claude Code refuses to edit files or commit while on `main`, and GitHub rejects direct pushes to `main`. Changes reach `main` only through a reviewed PR.

**Push your own code.** Every push is validated against the person who wrote it: the pre-push gate checks that each commit's author is the person pushing. Pushing a teammate's commits (e.g. after pairing) needs a validation step: you confirm in your terminal that they agreed. Keep your git identity set to the email on your GitHub account (§16.1 step 2), so your work counts as yours.

**One task → one branch → one PR.** Tasks are small on purpose, so each PR is reviewable in one sitting and every teammate ends up with several real PRs and reviews to show.

**Branch names** carry the lane issue number and the task key, so the skills and session hook can find both:
`<type>/<lane#>-<task>-<short-desc>`, with type `feat`, `fix`, `docs`, `test`, or `spike`. Example: `feat/2-b4-acestep-client`. `/start-session B4` creates it for you.

**PR title and body:**
- Title ends with the task key: `feat(songs): add ACE-Step client (B4)`.
- Body (the template asks for both) has:
  - `Part of #<lane#>`
  - `Task: B4`
- **Never write `Closes #<lane#>`.** That would close the whole lane.

**Ticking:** when the PR is merged, the `Tick lane task` workflow ticks `B4` in the lane issue automatically. When every box in a lane is ticked, the bot comments and the owner closes the lane issue. Run `python scripts/github/tick_task.py --issue <lane#> --task B4` if a box ever needs ticking by hand.

**Bugs** are separate issues (Bug template), labeled `bug` (+ `os:windows`/`os:macos` if OS-specific). Mention the task key and lane they belong to; assign them to that lane's owner.

**Labels:** `lane`, `platform`, `feature:songs`, `feature:cover`, `feature:dj`, `feature:player`, `spike`, `docs`, `test`, `bug`, `blocked`, `priority:high`, `os:windows`, `os:macos`.

**Commit messages:** `<type>(<area>): <summary> (<task>)`, e.g. `feat(dj): cache clips by track and voice (D5)`.

**PR rules:**

- Use the PR template (it loads automatically): `Part of #N`, `Task: KEY`, requirement IDs.
- Describe how it was tested: exact commands, manual browser steps (and OS), and what failed.
- Screenshots for any UI change. Save keepers to `docs/screenshots/` for the README; no credentials visible.
- CI must be green: `ruff check .`, `scripts/scan_secrets.py`, and `pytest` run on every PR.
- **One approving review** from your assigned reviewer (§3 ring; `/finish-session` requests them automatically). If you touched another lane's files, that lane's owner reviews too.
  - Reviewers use `/review-pr <n>` and **run the branch locally** for anything touching playback or a service call.
- **Someone else approves; the owner of the changed files merges.** Every PR needs an approval from a teammate other than the author (GitHub enforces this: the last person to push can't approve). Once it's approved and CI is green, **the owner of the files it changes merges it** (squash merge). Owners are listed in `.github/CODEOWNERS`, which matches each lane's "You own" list. Usually the owner is the author. If a PR changes another lane's files, that lane's owner may merge it too. Tests don't count toward ownership. Reviewers who don't own the files approve but never click Merge. GitHub can't restrict who merges, so the `Merged by owner` workflow labels and flags any PR merged by a non-owner. Claude Code is blocked from merging.
- Stuck more than ~2 hours? Comment on your lane issue with the task key, tag who you're waiting on, add `blocked`, and post in the team chat.

**Review turnaround:** within 12 hours. Check your queue at the start of every session (`/start-session` does this).

**Contribution evidence:** at the end, A writes a table in the README: member → PRs authored → PRs reviewed (`gh pr list --state merged --author <handle>`). Each lane issue's ticked checklist is a second, at-a-glance record.

---

## 10. Schedule & milestones (target: submit Fri 10/30)

The plan was written Mon 10/12. It aims to be **submission-ready Thu 10/29 evening**, leaving Friday as buffer. Every task below is a checkbox in one person's lane issue; see §19 for all five lanes.

### M0 — Foundations & spikes · Tue 10/20 – Wed 10/21

| Task | Owner |
|---|---|
| Kickoff call: confirm roles, fill §3, read this file together | All |
| Repo, branch protection, labels, the 5 lane issues, templates | A |
| Get `class-endpoints.txt`; fill §7.1; `.env.example`; `config.py`; `check_endpoints.py` | A |
| `clients/base.py` + `errors.py` (everyone depends on this; land first) | A |
| Qwen + ACE-Step: one successful raw call each, latency measured | B |
| FLUX: one successful raw call, latency measured | C |
| Chatterbox: one call with default voice + one with a WAV reference | D |
| **Playback spike** (Option A vs B), written up in §2 | E |
| Augmented starter prompt in `docs/STARTER_PROMPT.md` (§15), reviewed by all **before any app code** (assignment: add instructions before beginning the build). Do it in the kickoff call. | C + all |
| Answer the §14 open questions (release lead) | A |

**Exit criteria:** all 4 services answer from at least one teammate's machine via `check_endpoints.py`; the player approach is decided; the shared client base is merged.

### M1 — Vertical slices · Thu 10/22 – Sun 10/25

| Task | Owner |
|---|---|
| Library + job store + sample manifest loader | A |
| Generate tab: instrumental, then vocal with lyrics | B |
| Art prompt builder + FLUX + cover display + retry | C |
| DJ commentary + TTS + voice upload/validation | D |
| Queue logic + player panel + play/pause/skip with placeholder audio | E |
| Unit tests for own module (mocked clients) | Each owner |

**Exit criteria:** each feature works on its own branch against the live services; PRs open or merged.

### M2 — Integration & samples · Mon 10/26 – Tue 10/27

| Task | Owner |
|---|---|
| Merge all features; wire song → cover → library → queue → DJ prefetch | A + E |
| Generate the 3 sample songs; write `GENERATION_LOG.md` | C |
| Error/recovery pass: force each failure kind, check messages and recovery | E (drives), all fix |
| `run.sh` / `run.bat` tested on Mac **and** Windows | D |
| **Feature freeze Tue 10/27, 9 pm** — after this, only bug fixes and docs | All |

### M3 — Independent deploy test · Wed 10/28

| Task | Owner |
|---|---|
| Tag a release candidate (`rc1`); download the ZIP **from GitHub** | A |
| Install from the extracted ZIP using **only README.md** and class credentials, **once on Windows and once on macOS** (TC-10a/b). Use people who didn't write the setup code, and a clean machine or fresh folder. No help, no tribal knowledge. Log every friction point as an issue. | E + a teammate on the other OS |
| Fix everything found; repeat with `rc2` if anything changed | A + owners |
| Run the full §12 test matrix on the RC and record actual results | E (+ owners) |
| Non-technical usability run (TC-13) | C |
| Reliability pass (TC-12, TC-14) | D |

### M4 — Docs, evidence, submit · Thu 10/29 (Fri 10/30 buffer)

| Task | Owner |
|---|---|
| Screenshots of each core feature and an error state | C |
| README sections finalized (§11); each owner writes their feature's section in their own words | All, A edits |
| **Docs-vs-app verification:** two members who didn't write a section follow it literally and note mismatches | B + D |
| Final secret scan of the tagged commit **and** the ZIP contents | A |
| Tag `v1.0`; record the commit SHA; download the ZIP from GitHub; unzip and spot-check | A |
| Submit on Canvas: repo link + commit SHA + ZIP; confirm the professor has access | A |

---

## 11. README.md outline (DL1, DL7–DL10)

The README is **both the documentation and the report**, and it's graded directly. Build it alongside the code, not at the end. Headings below use the assignment's own words so the grader finds each required item. The setup part is §0.4 (Path 1) rewritten for the README; keep the two in sync.

1. **Overview**
   - What the app does, with a screenshot of the main screen.
   - One line on current status (version, tested OSes).
2. **Setup and use**
   1. **Dependencies and additional software**
      - Python 3.11+ (install links for Windows and macOS).
      - A modern browser.
      - Network access to the class servers (say whether campus network/VPN is needed, §14 Q7).
      - State explicitly that **nothing else** is needed: no ffmpeg, Docker, Node, or paid services.
      - Python packages install automatically from `requirements.txt` (pinned versions).
   2. **Endpoint configuration**
      - A table of every `.env` variable: what it's for, which class service/port, and an example value **with placeholders only**.
      - Note that port 9000 is never used.
   3. **How to supply credentials securely**
      - Fill `.env` (the launcher creates it on first run).
      - It is gitignored, never leaves the machine, and is never sent to the browser or logs.
      - What to do if a key leaks.
   4. **Launch instructions**
      - Two clearly separated sub-sections, **Windows** and **macOS**, each covering: install Python → extract the ZIP → first run creates `.env` → fill it → run again → browser opens at `http://127.0.0.1:7860`.
      - Include the manual equivalent commands and how to stop the app. Test both (TC-10a/b).
   5. **How to exercise the three core features**
      - Numbered click-by-click steps with screenshots: (a) generate instrumental and vocal songs, (b) see each cover with its track, (c) hear DJ commentary with the default voice, then with an uploaded MP3/WAV.
      - Also cover play/pause/skip and auto-advance.
      - Include **expected wait times** measured in testing, and the note that generated songs last until the app stops.
   6. **Troubleshooting**: the §0.4.7 table.
3. **Sample songs**
   - What's included.
   - **How the sample songs, lyrics, and covers were generated**: script, class services, inputs, seeds, who ran it and when.
   - Link to `samples/GENERATION_LOG.md`. State that all lyrics are AI-generated.
4. **Architecture**
   - Short diagram: Browser ↔ Gradio server ↔ 4 class services.
   - Why credentials never reach the browser; where files are stored.
5. **Test results**
   - From `docs/TEST_EVIDENCE.md`: **inputs, expected behavior, actual results** for all three core features and **at least one failure case**, with tester, OS, date, and commit.
   - **Completed tests and unchecked claims in clearly separate tables.**
6. **Unresolved problems / known issues**: an honest list, each with a workaround if any.
7. **Design judgment**
   - **One important design choice, justified with evidence from testing.** Candidates: DJ prefetch (measured gap with vs. without), single-player sequencing (overlap tests), song-before-cover (cover failure doesn't lose the song).
   - **One limitation or failure we investigated and what we learned.** Candidates: Qwen "thinking" text leaking into lyrics, ACE-Step latency vs. duration, browser autoplay policy, custom-voice quality vs. reference length.
8. **Documentation verification**
   - The team's own-words findings from checking this README against the finished app (tasks B10 and D9).
   - Which steps were followed, on which OS, what was wrong, and what was fixed.
9. **Safeguards**
   - Credentials, uploads, voice recordings, no third-party content, port 9000: how each is enforced (`.gitignore`, secret scan, guard hook, config check).
10. **How we used AI and checked its work**
    - Starter prompt + additions (link `docs/STARTER_PROMPT.md`).
    - The review process, and examples of agent mistakes we caught.
11. **Team & contributions**: member → role → PRs authored/reviewed.

Screenshots: store them in `docs/screenshots/`. **Before committing, check that no screenshot shows `.env`, a key, a terminal with secrets, or browser devtools with request headers.**

---

## 12. Test plan

### 12.1 Automated (pytest, mocked services; run in every PR)

- Config: missing vars → clear error; port 9000 → refuse to start; key never appears in `repr` or logs.
- Each client: success, timeout, 401, 500, malformed body → correct `ServiceError.kind`.
- Qwen parsing: valid JSON, malformed JSON, `<think>` content stripped.
- Player: queue order with DJ; skip during DJ; skip during song; DJ missing → song plays; end of queue.
- Upload validation: wav ok, mp3 ok, ogg rejected, oversize rejected, corrupt file rejected.
- Track model: `theme` flows from the form into lyrics, cover, and DJ prompts.
- Guardrails (`tests/test_guardrails.py`): guard blocks/allows the right commands, including PowerShell forms; session check runs; hook launcher works through bash.
- **Where they run:** Ubuntu on every PR (required check), and **Windows + macOS** after every merge to main (`cross-platform` CI job). A red Windows or macOS run is a bug for the PR's author.

### 12.2 Live test matrix (record in README)

Status values: **Pass / Fail / Not tested**. Fill "Actual" with what really happened, including timings.

| ID | Feature | Input / steps | Expected | Actual | Status | Tester | Date |
|---|---|---|---|---|---|---|---|
| TC-01 | F1 instrumental | Lo-fi, mellow, 45 s, Instrumental | Playable audio ~45 s, no vocals, added to library | | | | |
| TC-02 | F1 vocal + lyrics | Pop, upbeat, 60 s, Vocal, theme "road trip" | Qwen lyrics shown; audio has vocals; added to library | | | | |
| TC-03 | R2 session persistence | Generate 2 songs, switch tabs, play older one | Both remain in library and playable | | | | |
| TC-04 | F2 cover art | After TC-01/TC-02 | Distinct covers matching mood/style, shown with the correct track | | | | |
| TC-05 | F3 DJ default voice | Queue 3 samples, press Play | DJ intro before each song, mentions that song, no overlap | | | | |
| TC-06 | F3b custom voice | Upload a 10 s WAV the team recorded (not committed), queue 2 songs | Intros use the new voice | | | | |
| TC-07 | F3b MP3 upload | Same, with MP3 | Accepted, works | | | | |
| TC-08 | R3 controls | Pause/resume during DJ and during song; skip during each | Behaves per §8.4 | | | | |
| TC-09 | R4 auto-advance | Queue 3, press Play once, no further clicks | Plays to the end automatically | | | | |
| TC-10a | Fresh deploy, **Windows** | ZIP from GitHub → README Windows section only → `.\run.bat` | All 3 core features work | | | | |
| TC-10b | Fresh deploy, **macOS** | ZIP from GitHub → README macOS section only → `bash run.sh` | All 3 core features work | | | | |
| TC-11 | Safeguards | Inspect ZIP + repo + browser devtools network tab + logs + screenshots | No key anywhere; no uploads; no `.env`; no absolute paths to a developer's files (`grep -rn "C:\\Users\|/Users/" jukebox app.py scripts`) | | | | |
| TC-12 | Reliability: generate while playing | Start the queue, then generate a 60 s vocal song while music plays | Playback continues without stalls; the new song joins the library when done | | | | |
| TC-13 | Usability: non-technical first run | A teammate who didn't build the app follows only README/§0.4 on their own OS, without help, timed | Completes all 3 features; every point of confusion recorded and fixed or documented | | | | |
| TC-15 | Models used | Run `python scripts/check_models.py`; then generate one vocal song, play a 2-song queue with the DJ, and read the app's request log | Check passes; the log shows only the class host on 9001 (Qwen), 9006 (FLUX), 9007 (ACE-Step), 9008 (Chatterbox), each from the right feature; nothing else | | | | |
| TC-14 | Reliability: repeated use | Generate 5 songs in a row, queue all, let it play to the end; then restart the app | No errors or slowdowns; after restart the 3 samples remain and generated songs are gone (as documented) | | | | |
| **TC-F1** | Failure: bad credentials | Set an invalid key, generate a song | Clear auth message; app still usable after fixing | | | | |
| TC-F2 | Failure: service timeout/unreachable | Point one URL at a dead port (not 9000) | Clear message + Retry; UI not stuck | | | | |
| TC-F3 | Failure: bad upload | Upload .ogg / 0-byte / 5-min file | Rejected with reason; default voice still works | | | | |
| TC-F4 | Failure: DJ down mid-queue | Break Chatterbox URL, play queue | Songs still play; notice shown | | | | |
| TC-F5 | Failure: cover fails | Break FLUX URL, generate song | Song saved with placeholder; Retry cover works after fix | | | | |

---

## 13. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Class servers slow or overloaded near the deadline (everyone testing at once) | High | High | Measure latency in M0; generous timeouts; generate samples early (10/26); short default durations; Retry buttons | A |
| Gradio auto-advance unreliable | Medium | High | M0 spike with Option B fallback ready | E |
| Gaps or waits between songs because TTS is slow | Medium | Medium | DJ prefetch + cache; never block a song on the DJ | D, E |
| Grader deploy fails (missing file, unpinned dep, OS difference) | Medium | **Very high** | Pinned deps; run scripts for both OSes; M3 clean-machine test from the GitHub ZIP | A, E |
| Works on one OS, breaks on the other (paths, encodings, line endings, launchers) | Medium | **Very high** | pathlib + UTF-8 rules (§16.8), `.gitattributes`, Python-only scripts, cross-platform CI, TC-10a and TC-10b | A, D, E |
| A teammate has no Claude Code access (it needs a paid Claude plan) | Medium | High | Answered 10/20 (§14 Q8): four teammates use Claude Code and `afondale` uses Grok, so for that lane follow CLAUDE.md by hand and rely on the pre-push gate, CI, and review; pair or route to testing, docs, and samples work if anyone is blocked (§0.5) | A |
| Class servers need the campus network/VPN, and the grader or a teammate can't reach them | Medium | High | Tested from a home network with no VPN (§14 Q7, one network only); document it in README Setup; `check_endpoints.py` gives a clear message | A |
| Grader thinks the app froze during long generations | Medium | Medium | Staged status + elapsed time + "usually takes ~N s" hint in the UI; expected waits in README | B, E |
| ZIP on Canvas doesn't match the submitted commit | Low | **Very high** | Download the ZIP from the `v1.0` tag; verify the SHA; never push to the tag (A10) | A |
| The coding agent adds another model (an SDK, `gr.load`, browser speech) or a "fallback" model | Medium | **Very high** | §7.0 rule in CLAUDE.md and the starter prompt; `check_models.py` blocks merge in CI; guard hook blocks installs; Claude can't edit `model_policy.json`; reviewers check | A, all |
| Secret leaks into a commit | Low | **Very high** | `.gitignore`, `scan_secrets.py` in PR checklist, Claude Code denied `.env` reads, redacted logging; if it happens, rotate per class instructions and purge history | A |
| Qwen thinking tokens or chatter in lyrics/DJ scripts | Medium | Medium | Disable per docs, strip `<think>`, JSON output + parser, unit tests | B, D |
| Sample files too large for the repo/ZIP | Low | Medium | ~60 s samples, MP3 if possible, no LFS | C |
| Merge conflicts in `app.py` / UI | Medium | Low | UI split into `ui/*.py` modules; `app.py` stays thin; E owns `app.py`; file ownership per lane (§19) | E |
| Professor disallows Claude Code instead of Hermes | Low | High | Answered 10/20 (§14 Q1): Claude Code is acceptable. If that changes, activate the §2 Hermes contingency | A |

---

## 14. Open questions

| # | Question | Ask whom | Status |
|---|---|---|---|
| Q1 | Is building with Claude Code acceptable instead of (or alongside) Hermes? | Professor | Answered 10/20 (A5), by the release lead (not the professor): yes, Claude Code is acceptable. The Hermes contingency (§2) stays off. |
| Q2 | Actual due date? | Professor / Canvas | Answered 10/20 (A5), by the release lead: **Fri 10/30/2026**. Every schedule date in this file and in `scripts/github/issues.json` moved +7 days from the old 10/23 assumption. |
| Q3 | Contents of `class-endpoints.txt`: formats, auth, limits | Class materials | Answered 10/18 (A4): formats, auth and limits are in §7.1, from `class-endpoints.txt` and spikes B1, B2, C1, D1 |
| Q4 | Do all four services share one credential? | Class materials | Answered 10/18 (A4): yes, one `CLASS_API_KEY` as a bearer token works on all four (spikes B1, B2, C1, D1) |
| Q5 | Is a public repo okay, or should we add the professor as a collaborator? | Professor | Answered 10/21 (A5 follow-up), by the release lead (not the professor): the repo stays **public until we submit**. At submission the release lead makes it **private** and invites the professor as a collaborator (#42); the invite is confirmed before A10 and the access is kept until grades are posted (DL12). A private repo on a free personal account cannot enforce branch protection (§16), so the repo goes private only after the last merge. Any other grader also needs an invite. |
| Q6 | Python version and OS on the grader's machine? (affects run scripts) | Professor | Answered 10/20 (A5), by the release lead: support macOS and Windows with Python 3.11+. |
| Q7 | Do the class endpoints require the campus network or a VPN? | Professor / class materials | Answered 10/20 (A5), by the release lead: no, from one network. `scripts/check_endpoints.py` passed on all four ports from the release lead's home Wi-Fi, off campus with no VPN. A restrictive network could still differ. |
| Q8 | Does every teammate have Claude Code access (paid Claude plan)? If not, who pairs with whom? | Team, at kickoff | Answered 10/20 (A5): four teammates use paid Claude Code. `afondale` (Lane E) uses paid Grok. Claude Code's hooks, skills and `CLAUDE.md` rules do not apply to Grok; the pre-push gate, CI and review still do. |
| Q9 | Can we resubmit before the deadline? (The assignment says the version in the final submission is graded.) | Professor | Answered 10/20 (A5), by the release lead: yes. |

---

## 15. Starter prompt (verbatim) + team additions

The assignment says to keep all existing starter-prompt language and encourages adding to it **before beginning the build**. The final version lives in `docs/STARTER_PROMPT.md` and is merged (task C0) before any app-code task starts. CLAUDE.md tells Claude Code to read it at the start of every session, which is our equivalent of pasting it into Hermes.

### 15.1 Original (do not edit)

```
# Overarching Task: Build an AI Jukebox
Build an app that (1) generates customizable songs, (2) generates
matching cover art, and (3) plays a song collection with AI-generated
spoken DJ commentary between tracks.
# Required Class Services
- Qwen3.6-35B-A3B on port 9001 for text generation.
- FLUX.2 klein 4B on port 9006 for cover art.
- ACE-Step 1.5 XL Turbo on port 9007 for music.
- Chatterbox Multilingual V3 on port 9008 for DJ speech.
Use the supplied class-endpoints.txt for connection details, or ask our
team if it is unavailable. Follow each service's documented request
format. Use these class services for the required features. You may use
other class endpoints for optional features, but the core app must work
with class services and credentials alone. Do not use paid services for
any app features, including optional features. Do not use port 9000 for
app requests.
# Safeguards
- Keep credentials server-side and out of GitHub, submission archives,
browser code, logs, and documentation. Use placeholders in configuration
examples.
- Never commit user uploads or voice-reference recordings to GitHub or
include them in submission archives.
- Do not bundle third-party music, lyrics, cover art, or voice samples
with the app.
```

### 15.2 Team additions (draft; review in M0)

```
# Team Additions
## Stack and deployment
- Python 3.11+ with Gradio (Blocks API). Pin every dependency to an exact
  version in requirements.txt.
- The grader deploys from a GitHub-downloaded ZIP with a Python venv:
  copy .env.example to .env, then run run.sh (macOS/Linux) or run.bat
  (Windows). No Docker, no ffmpeg, no Git LFS.
- Bind to 127.0.0.1. Never enable Gradio public sharing links.
- The app, scripts, and docs must work on both macOS and Windows: pathlib for
  paths, UTF-8 for text files, no shell-outs or OS-specific commands in app
  code; run.sh is started with `bash run.sh`, run.bat with `.\run.bat`.

## Architecture
- Follow PROJECT.md for repository layout, data model (Track, Job),
  client interfaces, and the error model.
- All calls to class services go through jukebox/clients/*. UI code never
  builds HTTP requests and never sees credentials.
- Refuse to start if any configured service URL uses port 9000.

## Behavior requirements
- Song generation: style, mood, duration, instrumental or vocal. Vocal
  tracks get original lyrics written by Qwen. Show staged progress
  ("Writing lyrics…", "Composing music…", "Painting cover…").
- Every generated song gets its own FLUX cover reflecting its theme,
  style, and mood. Image prompts must request no text, logos, or real
  people. A failed cover never discards the song; offer "Retry cover".
- DJ: before each queued song, play 2–3 sentences (~30–50 words) of
  commentary specific to that song, written by Qwen and spoken by
  Chatterbox. Prefetch the next DJ clip while the current item plays.
  A DJ failure skips the DJ clip and the song still plays.
- Voice upload accepts only MP3 or WAV, validated for decodability, size,
  and duration; stored outside the repo in runtime/uploads/.
- Exactly one audio source plays at a time. The queue auto-advances
  DJ → song → DJ → song after the user presses Play once. Provide
  play/pause and skip.
- Every service failure becomes a plain-language message with a recovery
  path (retry, fix input, or fix config). The UI never stays stuck in a
  loading state.

## Content safeguards
- Lyrics, DJ scripts, and cover prompts must be original. Never reproduce
  or imitate existing songs or lyrics, and never reference real artists.
- If Qwen emits reasoning or "thinking" text, disable it per the service
  docs and strip it before use.

## Models
- Use ONLY these four models, each for its own job: Qwen3.6-35B-A3B (port
  9001) for all text; FLUX.2 klein 4B (9006) for cover art; ACE-Step 1.5 XL
  Turbo (9007) for music; Chatterbox Multilingual V3 (9008) for DJ speech.
- No other model, SDK, hosted service, local model, browser speech
  synthesis, other class endpoint, or fallback model, ever. On failure, show
  the error and offer Retry.

## Quality
- Include pytest tests with mocked services for clients, parsing, upload
  validation, and queue logic.
- Never log credentials or request headers.
```

---

## 16. Working with Claude Code

Everything in this section is enforced or automated by files committed in the repo, so every teammate's Claude Code behaves the same way:

| File | What it does |
|---|---|
| `CLAUDE.md` | Rules Claude reads at the start of every session (hard rules, conventions) |
| `.claude/settings.json` | Team permissions (what Claude may run without asking, what it may never do) and hooks |
| `.claude/hooks/session_start.py` | Runs automatically when a session starts, resumes, clears, or compacts; tells Claude your branch, lane issue, task, and any problems |
| `.claude/hooks/pre_bash_guard.py` | Runs before every shell command Claude tries; blocks the dangerous ones |
| `.claude/hooks/run_py.sh` | Starts the two hooks with whatever Python works on your machine (macOS `python3`; Windows venv `python` or `py`) |
| `scripts/setup_dev.py`, `scripts/doctor.py` | One-time setup and a health check, same on macOS and Windows (§16.1) |
| `.gitattributes` | Keeps line endings consistent between macOS and Windows (§16.8) |
| `.claude/skills/*` | The team's shared slash commands (§16.4) |

### 16.1 One-time setup (each teammate, ~30 minutes, by Wed 10/21)

The team works on **macOS and Windows**. Every tool, script, hook, and skill in the repo runs on both. Only the commands you type to install things and to activate the virtual environment differ. Follow the column for your machine; §16.8 has the side-by-side cheat sheet.

> **Windows teammates: use native Windows with PowerShell** (the default in Windows Terminal). WSL also works, but then follow the macOS column inside your Linux shell and keep the clone in the Linux file system (`~/dev`), not under `/mnt/c`. Don't mix the two: a `.venv` made in one won't run in the other.

#### Step 1: Install the tools

| Tool | macOS (Terminal) | Windows (PowerShell) |
|---|---|---|
| Package manager | Homebrew, from brew.sh | `winget` (built into Windows 10/11) |
| Git | `xcode-select --install` (or `brew install git`) | `winget install Git.Git`. **Required**: it also installs **Git Bash**, which Claude Code uses to run commands and the team hooks. |
| Python 3.12 (3.11+ works) | `brew install python@3.12` | `winget install Python.Python.3.12`. Installs the `py` launcher. |
| GitHub CLI | `brew install gh` | `winget install GitHub.cli` |
| Claude Code (needs a paid Claude plan, Pro or higher; tell A if you don't have one) | `curl -fsSL https://claude.ai/install.sh \| bash` (or `brew install --cask claude-code`) | `irm https://claude.ai/install.ps1 \| iex` (or `winget install Anthropic.ClaudeCode`) |
| Editor (optional) | `brew install --cask visual-studio-code` | `winget install Microsoft.VisualStudioCode` |

**Close and reopen your terminal** after installing, so the new commands are on your PATH. Then check:

| Check | macOS | Windows |
|---|---|---|
| Python | `python3 --version` → 3.11 or newer | `py --version` → 3.11 or newer |
| Git | `git --version` | `git --version` |
| GitHub CLI | `gh --version` | `gh --version` |
| Claude Code | `claude --version` | `claude --version` |

**Windows only, two more settings:**

1. **Turn off the Microsoft Store Python aliases.** They intercept `python`/`python3` and open the Store instead of running Python. Go to Settings → Apps → Advanced app settings → App execution aliases, and switch off `python.exe` and `python3.exe`.
2. **Allow PowerShell to run the venv activation script.** Run this once:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```
   If you'd rather not change it, use Command Prompt and `.venv\Scripts\activate.bat` instead.

#### Step 2: Git identity and GitHub login (same on both)

Use the email on your GitHub account, so your commits count as your contribution:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
gh auth login
```

For `gh auth login`, choose GitHub.com → HTTPS → "Login with a web browser". Check it worked with `gh auth status`.

Then **accept the repo invitation** in the email GitHub sends you (the release lead sends it in §18 step 3).

#### Step 3: Clone into a short, non-synced folder

Don't clone into OneDrive (Windows) or iCloud Desktop/Documents (macOS). Sync tools lock files inside `.venv` and `.git`. On Windows, long paths also break some pip installs.

| macOS | Windows |
|---|---|
| `mkdir -p ~/dev && cd ~/dev` | `mkdir C:\dev; cd C:\dev` |
| `gh repo clone OWNER/ai-jukebox` | `gh repo clone OWNER/ai-jukebox` |
| `cd ai-jukebox` | `cd ai-jukebox` |

#### Step 4: Run the setup script

One Python script for both systems. It creates `.venv`, installs the dev tools (and `requirements.txt` once it exists), creates `.env` from the template if you don't have one, and runs the doctor (Step 6):

| macOS | Windows |
|---|---|
| `python3 scripts/setup_dev.py` | `py scripts\setup_dev.py` |

Re-run it whenever `requirements.txt` changes (the session check will tell you).

#### Step 5: Fill in `.env` (by hand; Claude is blocked from touching it)

| macOS | Windows |
|---|---|
| `open -e .env` (or open it in VS Code) | `notepad .env` (or open it in VS Code) |

- Fill in the values from `class-endpoints.txt`.
- Keep `class-endpoints.txt` **outside** the repo folder.
- Never paste the key into Claude, an issue, a PR, or the team chat.

#### Step 6: Activate the venv and run the doctor

| macOS | Windows (PowerShell) | Windows (Command Prompt) |
|---|---|---|
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` | `.venv\Scripts\activate.bat` |
| `python scripts/doctor.py` | `python scripts\doctor.py` | `python scripts\doctor.py` |

Your prompt now starts with `(.venv)`. Inside the venv, the command is `python` on both systems.

The doctor checks:
- Python, the venv, git and your git identity
- `gh` login and Claude Code
- **Bash for the hooks**: on Windows it finds Git Bash
- The hooks themselves: it runs the session check and confirms the guard blocks `cat .env`
- `.env`, and your folder location
- **Windows only:** the Store aliases and the PowerShell execution policy

Every FAIL comes with the fix for *your* OS. Get to zero FAILs. WARNs are advice.

#### Step 7: Start Claude Code and verify the team setup

From the repo root, with the venv active, run `claude`.

1. Trust the folder when asked. If Claude Code asks you to approve the project's hooks, review them with `/hooks` and approve.
2. Type `/`. You should see `start-session`, `check`, `finish-session`, `review-pr`, and `log-test`.
3. Ask Claude: *"What did the session check say?"* It should show `OS: macOS` or `OS: Windows`, your branch, and any warnings.
4. Ask Claude: *"Run `cat .env`."* It must be **blocked** by the team guardrail. If it isn't, stop and tell A.

#### Step 8: Add yourself to the roster

Add your name, GitHub handle, and OS (`"macos"` or `"windows"`) to `.github/team.json`, if A hasn't already. The OS field decides who runs the Windows and macOS deploy tests.

### 16.2 Before you start a session: pre-flight checklist (2 minutes, you, not Claude)

Do this *before* typing `claude`. If any box fails, fix it first.

- [ ] **I know my task.** It's the next unticked task in my lane issue whose "Needs" are ticked (`gh issue list --label lane --assignee @me`, or §19). Nothing ready → ask A; don't freelance outside your lane.
- [ ] **Its dependencies are merged**, or I've agreed with the owner to work against a mock/stub for now.
- [ ] **No reviews are waiting on me:** `gh pr list --search "review-requested:@me"`. Reviews come first; they unblock teammates.
- [ ] **I checked the team chat** for announcements: main broken, endpoint changes, big merges that touch my files.
- [ ] **Last session's work is pushed.** Nothing important lives only on my laptop.
- [ ] **My venv is active** in this terminal: the prompt shows `(.venv)`. If not: macOS `source .venv/bin/activate`, Windows `.venv\Scripts\Activate.ps1`.
- [ ] **`.env` is in place and current.** Run `python scripts/check_endpoints.py`: if a class service is down, plan to work with mocked tests instead of waiting.
- [ ] **I have one focused goal** that fits in this sitting: one task, or one clear slice of it.
- [ ] **I've saved 15 minutes at the end** for `/finish-session`. If I don't have that time, I do a review instead.

Never start a session on `main`, without a task, or on two tasks at once.

### 16.3 Every session, step by step

1. **Open a terminal in the repo root, activate `.venv`, run `claude`.** The activation command differs by OS (§16.8). Everything after this point is the same on macOS and Windows.
2. **Read the session check.** Claude shows it automatically: branch, lane issue and task, ahead/behind, and warnings.
   - **On main:** don't change anything yet. Step 3 creates your new branch. Every task needs its own branch (§9).
   - **`.env` missing:** create it yourself (§16.1 step 5).
   - **venv not active:** quit Claude Code (`/exit`), activate (§16.8), start `claude` again.
   - **Behind main:** `/start-session` offers to pull main in.
   - **`STOP`:** something that must never be committed is tracked by git. Tell A immediately.
3. **Run `/start-session <task key>`** (e.g. `/start-session B4`; with no key it suggests your next ready task). It does the following, in order:
   - Fetches from GitHub.
   - Finds your lane issue and the task, and checks that the tasks it needs are ticked.
   - Creates or switches to `feat/<lane#>-<task>-<desc>`.
   - Reads CLAUDE.md and only the PROJECT.md sections your lane and task need.
   - Checks your review queue.
   - Gives you a **session brief**: goal, acceptance criteria, files, test plan, and risks.
   - Proposes a plan of up to 8 steps, then **waits for you**.
4. **Challenge the plan before approving it.** Typical pushback:
   - "Tests first."
   - "That's out of scope for this task."
   - "That file belongs to another lane; keep the change minimal and tag its owner."
   - "§7.1 doesn't document that field; don't guess."
   - "Smaller steps."
5. **Build in small steps.**
   - After each step, ask Claude to run the tests and show you the diff. **Read every diff.** If you can't explain a change to your reviewer, don't keep it.
   - For bigger changes, switch Claude Code into plan mode so it proposes before it edits.
6. **Verify by hand what Claude can't.**
   - Claude can't hear audio or judge a cover image.
   - Run the app and check the feature in the browser yourself. Until the launchers exist, run `python app.py`; after that use `bash run.sh` (macOS) or `.\run.bat` (Windows).
   - Take screenshots now while it's fresh; save them to `docs/screenshots/`.
7. **Keep the context clean.**
   - Long session or new topic: `/compact`.
   - Switching to a different task: finish first, then `/clear`.
   - The session check re-runs after either.
8. **Capture what you learn.**
   - A real endpoint format, limit, or latency → PROJECT.md §7.1.
   - A choice someone might question → §2.
   - A changed prompt → note why in the PR.
   - These feed the graded "design judgment" section.
9. **Run `/check` whenever you like.** It runs ruff, pytest, the secret scan, and the config check.
10. **End with `/finish-session`.** It:
    - Runs the gate.
    - Checks each acceptance criterion with evidence.
    - Proposes doc updates.
    - Commits with the team message format and pushes your branch.
    - Opens a PR (`Part of #<lane>`, `Task: <key>`) with your assigned reviewer, or posts a progress note on your lane issue if you're not done. The task's box ticks itself when the PR merges.
    - It asks before every GitHub action.
11. **Tell the team:** post the PR link (or "blocked on X") in the team chat.

When you're the reviewer: `/review-pr <n>`. It checks out the branch, runs the gate, reviews against the task's done criteria and PROJECT.md, and drafts comments plus manual test steps. **You** run those steps in the browser and make the approve/request-changes call in GitHub.

### 16.4 Team skills (shared slash commands)

These live in `.claude/skills/` and update for everyone when merged to main. Propose changes by PR like any other code.

| Command | When to run it | What it does | Changes anything? |
|---|---|---|---|
| `/start-session <task key>` | First thing, every session | Session check → find lane + task (or suggest the next ready one) → check its Needs → sync → branch → load PROJECT.md sections → review queue → brief → plan, then waits for approval | Creates/switches branch; may pull main (asks first) |
| `/check` | Anytime; before commit/PR/review | ruff, ruff format check, pytest, secret scan, config check; reports a table; flags stray `.env`/`runtime/`/audio | No (suggests fixes, applies only if you agree) |
| `/finish-session` | Last thing, every session | Gate → criteria check with evidence → doc updates → commit → agent review of the diff → your approval → push (git re-runs the gate) → PR with reviewer, or progress comment | Commits, pushes branch, opens PR/comment (asks before each) |
| `/review-pr <pr#>` | When you're requested as reviewer | Checks out PR, runs gate, reviews vs. task criteria/§6/§7/lane ownership/hard rules, drafts Blocking/Should-fix/Nits/Questions + manual test steps | Posts a comment only if you say so; never approves or merges |
| `/log-test <TC-ID>` | After you actually run a §12.2 test | Records your observed result in `docs/TEST_EVIDENCE.md` with tester, date, commit; offers to file a bug on failure | Edits `docs/TEST_EVIDENCE.md`; may open a bug issue (asks first) |

Built-in commands worth knowing:
- `/compact` shrinks a long conversation.
- `/clear` starts fresh.
- `/hooks` shows the hooks that are active.

### 16.5 Guardrails (automatic)

| Guardrail | Where | Effect |
|---|---|---|
| Session check | SessionStart hook | Warns about: working on main, missing `.env`, `.env` or `runtime/` tracked by git, stale fetch, behind main, missing or stale `.venv`, stray audio outside `samples/` |
| No `.env` access | Permissions deny + Bash guard | Claude can't read, edit, `cat`, `source`, copy, or `git add` `.env`. `.env.example` is fine. |
| New branch before any change | Guard hook on Edit/Write + Bash guard + GitHub branch protection | On `main`, Claude can't edit repo files or commit; it's told to run `/start-session` to create a branch. GitHub rejects direct pushes to `main` from anyone. |
| No pushes to main / force pushes / commits on main | Bash guard + permissions | Blocked; Claude is told to use the feature branch |
| Every commit is summarized and approved | CLAUDE.md + `/finish-session` + Bash guard + permissions | Before any commit, Claude summarizes the changes, lists every file being committed, and waits for your yes; the guard stops every `git commit` for approval |
| Every push is checked and approved | `/finish-session` + Bash guard + permissions + git pre-push hook | Before any push: `/check` passes, a review agent checks the diff, and you approve. Then git runs `scripts/prepush.py` (same checks as `/check`) on **every** push, from Claude or your own terminal, and blocks it on any failure. `setup_dev.py` turns this on and makes sure the hook file is executable; `doctor.py` FAILs if it's off, or if git would skip the hook because it isn't executable (committed as mode `100644`; git for Windows ignores the bit, so doctor reads the mode from the git index). Claude can't use `--no-verify` or change `core.hooksPath`. |
| No `git add` of `runtime/` or `-f` adds | Bash guard | Blocked |
| No port 9000 | Bash guard + `scan_secrets.py` + config check | Blocked in commands; fails the scan in app code |
| Only the four class models | `check_models.py` (`/check`, CI) + Bash guard + Claude can't edit `model_policy.json` | Banned AI packages can't be installed by Claude; any other model, provider, browser speech, or wrong feature→model wiring fails CI |
| No PR merges by Claude | Bash guard + permissions | Humans merge after review |
| Every push is checked against who wrote the code | Pre-push gate (`scripts/check_authors.py`) | Each commit being pushed must be authored by the pusher (`git config user.email`). If any were written by someone else, the push stops and lists them; the pusher must validate in their own terminal that the author agreed (type `yes`). With no person to answer, e.g. when Claude runs the push, it's blocked. |
| Someone else approves, the owner merges | GitHub branch protection + `.github/CODEOWNERS` + `Merged by owner` workflow | Authors can't approve their own PR; a PR merged by anyone who doesn't own its changed files is labeled `merged-by-non-owner` and flagged to A |
| Secret scan | `/check`, CI, release | Key-like strings, your actual `.env` values, forbidden files, port 9000 |
| CI | GitHub Actions on every PR | Lint, secret scan, tests must pass before merge (with branch protection) |

Guardrails are a safety net, not permission to stop paying attention.
- They need bash (built into macOS; Git Bash on Windows) and Python. `scripts/doctor.py` checks both.
- If the guard can't find Python, it **fails closed**: every command is blocked until you fix it (§16.9). It never silently stops protecting you.
- The pre-push gate runs the test suite the way CI does: plain `pytest -q`, with the repo root **not** on `sys.path` (the gate uses `python -P -m pytest`). A test that only works under `python -m pytest` therefore fails in the gate, not just later in CI. Run plain `pytest -q` yourself while you work.
- On Windows, the repo turns off Claude Code's separate PowerShell tool so all commands go through Git Bash, exactly as on macOS. If someone turns it back on, the guard covers PowerShell commands too (`Get-Content .env` is blocked like `cat .env`).
- **Don't** switch on modes that skip permission prompts for git or GitHub actions.
- **Don't** edit `.claude/settings.json` locally to get around a block. Personal tweaks go in `.claude/settings.local.json` (gitignored), and never to weaken a team rule.

### 16.6 Golden rules for working with the agent

0. **New task, new branch. Always.** Before you or Claude change anything, you're on a fresh branch for that task, never `main` (§9).
1. **You own every line Claude writes.** The assignment grades the team's ability to check the agent's work. Reviewers ask "how did you verify this?" on every PR.
2. **Never paste a credential** into Claude, an issue, a PR, a commit, or chat.
3. **Only the four class models, each for its own job (§7.0).** If Claude suggests an SDK, a local model, browser speech, or a "fallback" model, say no.
4. **Never let Claude guess an API format.** If §7.1 says TBD, stop and fill it from the docs first.
5. **Small diffs, tests first, one task per session, stay in your lane.**
6. **Claude can't hear or see the output.** Audio quality, cover art, DJ voice, and overlap all need a human check in the browser.
7. **Record evidence as you go** with `/log-test` and screenshots. Don't reconstruct it the night before.
8. **Be honest in the PR's "AI assistance" line.** For example: "Written with Claude Code; I reviewed every change and ran the tests above."

### 16.7 Prompts that work well

- *"Implement the done criteria of task D3 per PROJECT.md §8.3. Write failing tests first, then the code. Stop when tests pass and show me the diff."*
- *"Before writing code: does our §7.1 table give you everything you need for this request? List anything missing instead of assuming."*
- *"What's the riskiest way this could fail for the grader? Write a test for it."*
- *"Explain this diff as if to my reviewer, including what you did NOT test."*
- *"Compare this client to §7.2's signature and §7.3's error kinds and list every mismatch."*

### 16.8 macOS vs Windows quick reference

Inside Claude Code, nothing differs. Claude runs commands in bash on both systems (Git Bash on Windows; the repo's settings turn off Claude Code's separate PowerShell tool so everyone gets the same behavior), and `git`, `gh`, `python`, `pytest`, `ruff`, and the team skills are identical. The differences are only in **your own terminal**:

| Task | macOS (Terminal, zsh) | Windows (PowerShell) |
|---|---|---|
| Python outside the venv | `python3` | `py` |
| First-time / after-pull setup | `python3 scripts/setup_dev.py` | `py scripts\setup_dev.py` |
| Activate the venv | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` (cmd: `.venv\Scripts\activate.bat`) |
| Deactivate | `deactivate` | `deactivate` |
| Python inside the venv | `python` | `python` |
| Check your machine | `python scripts/doctor.py` | `python scripts\doctor.py` |
| Copy the env template | `cp .env.example .env` | `copy .env.example .env` |
| Edit `.env` | `open -e .env` | `notepad .env` |
| Run the app (once it exists) | `bash run.sh` | `.\run.bat` |
| Start Claude Code | `claude` | `claude` |
| Path separator in commands you type | `/` | `\` (forward `/` also works in PowerShell for most commands) |
| Unzip a release ZIP | `unzip file.zip` or double-click | `Expand-Archive file.zip -DestinationPath .` or right-click → Extract All |
| Where the class key lives | `.env` only | `.env` only |

Rules for code that has to work on both (also in CLAUDE.md):

- Use `pathlib.Path` for every file path. Never build paths with `"/"` or `"\\"` strings.
- Open text files with `encoding="utf-8"`, and audio and images in binary mode.
- Don't shell out from app code (`os.system`, `subprocess` with shell commands), and don't depend on `ffmpeg`, `open`, `start`, or `xdg-open`. To open the browser use `webbrowser.open`, or Gradio's `inbrowser=True`.
- Scripts that people run go in Python (`scripts/*.py`), plus exactly two launchers: `run.sh` (macOS) and `run.bat` (Windows).
- Line endings are handled by `.gitattributes`: LF everywhere, CRLF only for `.bat`/`.cmd`/`.ps1`. Don't fight it with editor settings.
- `run.sh` is started with `bash run.sh`, so it works even if the executable bit was lost (Windows commits and ZIPs can drop it).

### 16.9 Troubleshooting by OS

| Symptom | macOS fix | Windows fix |
|---|---|---|
| `claude` / `gh` / `py` "not found" right after installing | Open a new terminal window | Open a new terminal window (PATH only updates in new windows) |
| `python` opens the Microsoft Store or prints nothing | — | Turn off the App execution aliases (§16.1 step 1) and use `py` outside the venv |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | — | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, or use `.venv\Scripts\activate.bat` in Command Prompt |
| Session check never appears / guard doesn't block `cat .env` | Run `python scripts/doctor.py` and fix FAILs; make sure `python3 --version` works | Run `python scripts\doctor.py`. Usually Git for Windows is missing (`winget install Git.Git`) or Git Bash is in an unusual place: set `CLAUDE_CODE_GIT_BASH_PATH` to its `bin\bash.exe` under `"env"` in `.claude/settings.local.json`. Restart Claude Code. |
| "Team guardrail could not run: no working Python 3 on PATH" on every command | Activate the venv before starting `claude` | Activate the venv before starting `claude`; check `py --version` works |
| `bash: ...run_py.sh: $'\r': command not found` | — | The file got Windows line endings. Delete `.claude/hooks/run_py.sh`, then `git checkout -- .claude/hooks/run_py.sh` |
| `pip install` fails with "path too long" | — | Move the clone to `C:\dev\ai-jukebox`; or run `git config --global core.longpaths true` |
| `.venv` broken after copying the folder between machines/OSes | Delete `.venv`, re-run `python3 scripts/setup_dev.py` | Delete `.venv`, re-run `py scripts\setup_dev.py` |
| Gradio page won't load | Check the URL is `http://127.0.0.1:7860`; another app may own the port, so change `APP_PORT` in `.env` | Same; also allow Python through Windows Defender Firewall if prompted (local only) |
| No sound in the browser | Click the page once (browsers block autoplay until you interact); check output device | Same |

---

## 17. Definition of done (whole project)

- [ ] All §1 rows checked off, with a passing test case or code-review evidence
- [ ] §12.2 matrix filled in with real results; failures and untested items labeled honestly
- [ ] Fresh-machine install from the GitHub ZIP passed (TC-10) on the final commit
- [ ] Secret scan clean on the final commit and on the ZIP contents
- [ ] README complete per §11, with screenshots, verified by two non-authors
- [ ] Every member has ≥1 meaningful merged PR and ≥1 review
- [ ] Professor has repo access; Canvas has the repo link, commit SHA, and ZIP of that exact commit
- [ ] All 5 lane issues closed with every task ticked (or unfinished tasks explicitly moved to Known issues in the README)
- [ ] TC-13 passed: a non-technical teammate ran the app from the README alone
- [ ] Every README heading required by the assignment is present (§11 / DL7–DL10), and screenshots show no credentials
- [ ] Canvas ZIP was downloaded from the `v1.0` tag, its folder name/contents match the submitted full commit ID, and it passes `scan_secrets.py --zip`
- [ ] `check_models.py` passes on the release commit and TC-15 passed: only Qwen 9001, FLUX 9006, ACE-Step 9007, and Chatterbox 9008 are used
- [ ] Nobody deletes, renames, or force-pushes the repo or the `v1.0` tag until grades are posted. The repo goes private only at submission, once the professor and any other grader are invited (DL12)

---

## 18. GitHub build-out guide (release lead A, ~45 minutes, Tue 10/20)

This turns the starter scaffold into the team repo with the 5 lane issues created and assigned. Everything is scripted and safe to re-run.

### Step 0: Prerequisites and two decisions

You can do this from either macOS or Windows. The only OS-specific commands are in Step 2.

- `gh auth status` shows you logged in. You must be an admin of the repo you're about to create.
- **Who owns the repo?** Your personal account is simplest. An organization also works.
- **Public or private?**
  - Private repos on a **free personal account can't enforce branch protection**.
  - Options:
    - Make the repo public.
    - Use GitHub Pro (free with the GitHub Student Developer Pack; CU students qualify).
    - Accept "protection by team rule + the Claude Code guard hook."
  - Either way, add the professor before submitting (§14 Q5).

### Step 1: Fill in `.github/team.json`

Collect each teammate's name and GitHub handle in the kickoff call. Assign roles A–E, and add the professor's handle if known. The `reviewer` letters already encode the §3 review ring; leave them.

### Step 2: Create the repo from the scaffold

First finish your own §16.1 setup steps 1–2 (tools, git identity, `gh auth login`). Then extract the scaffold into your short dev folder and enter it:

| macOS (Terminal) | Windows (PowerShell) |
|---|---|
| `cd ~/dev` | `cd C:\dev` |
| `unzip ~/Downloads/ai-jukebox-scaffold.zip` | `Expand-Archive $HOME\Downloads\ai-jukebox-scaffold.zip -DestinationPath .` |
| `cd ai-jukebox` | `cd ai-jukebox` |
| `python3 scripts/setup_dev.py` | `py scripts\setup_dev.py` |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |

From here on, every command in this guide is **identical on macOS and Windows** (the venv's `python`, `git`, and `gh` behave the same).

**Run this step in your own terminal, not inside Claude Code.** The team guardrail deliberately blocks commits on `main`, and this first commit has to go there. Every later change goes through a branch and a PR.

```bash
git init -b main
git add .
git status                          # confirm: no .env, no runtime/, no audio
python scripts/scan_secrets.py      # must pass
git commit -m "chore: project plan, scaffold, team skills and guardrails"
gh repo create OWNER/ai-jukebox --private --source . --remote origin --push
```

Then set merge rules: squash merges only, and auto-delete branches after merge.

```bash
gh repo edit --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false --delete-branch-on-merge
```

### Step 3: Invite the team

```bash
python scripts/github/bootstrap.py --invite --skip-issues
```

Everyone must **accept the email invite** before GitHub lets you assign their lane issue to them. Nudge people in chat.

### Step 4: Create the labels, the milestone, and the 5 lane issues

Preview first, then run it for real:

```bash
python scripts/github/bootstrap.py --dry-run
python scripts/github/bootstrap.py --dry-run --preview B
python scripts/github/bootstrap.py
```

The first command lists what it would do. The second prints exactly what lane B's issue will say. The third does it:

- **Labels:** 14, colored by area (including `lane`, plus `os:windows` / `os:macos` for OS-specific bugs).
- **Milestone:** one, "v1.0 submission" (due 10/29). The M0–M4 checkpoints are headings inside each lane issue.
- **Lane issues:** five, one per person, each assigned to its owner from `team.json`. Each contains:
  - the owner's mission
  - the files they own ("stay in your lane")
  - who's waiting on them and who they're waiting on
  - how to work (one task per session/branch/PR)
  - their task checklist grouped by checkpoint. Each task has a goal, "Needs" (linked to the other lane's issue), refs, requirement IDs, and "Done when" criteria.
- After creating all five, the script links them to each other: dependencies point to the right lane issue numbers, plus a lane directory at the bottom.

If someone hadn't accepted their invite yet, their lane is created unassigned and the script tells you. Assign it later with:

```bash
gh issue edit <number> --add-assignee <handle>
```

If handles aren't known yet, run with `--no-assign` and assign later.

**Changing the backlog later:** edit `scripts/github/issues.json`, then run `python scripts/github/bootstrap.py --refresh`. It re-renders the lane issues and keeps ticked boxes ticked. Then regenerate §19 with `python scripts/github/assignments.py`.

### Step 5: Protect `main`

```bash
python scripts/github/bootstrap.py --protect --skip-issues
```

This requires a PR, 1 approving review, and the CI `checks` job before merging to main. New commits cancel an earlier approval, the last person to push can't be the approver, and force pushes and deleting main are blocked. **These rules apply to admins too: no one can push to main without an approved PR.** If GitHub refuses (free private repo), the script says so. Record that in §2 and rely on the team rule plus the guard hook.

### Step 6: Project board (optional, recommended)

On GitHub: **Projects → New project → Board**.

- Add a workflow to **auto-add items** from the repo.
- Columns: Todo / In progress / In review / Done.
- Group by **Milestone**, filter by **Assignee** for each person's view.

This gives the team (and you, as release lead) one screen showing who's doing what.

### Step 7: Verify the setup with a real PR

1. Create a branch `docs/1-team-roster` and fill in anything missing in `team.json` or PROJECT.md §3.
2. Push it and open a PR.
3. Check that CI runs and goes green, and that the PR template appears.
   - After the merge, open **Actions → CI** and confirm the `cross-platform` job passed on **windows-latest** and **macos-latest**.
4. Have your reviewer (E) approve, then squash-merge.
5. Check each person has their lane: `gh issue list --label lane`. Each lane issue shows "0 of N tasks" progress in the issue list.

### Step 8: Kickoff message to the team (copy and edit)

> Repo is live: <link>. Do this today:
> 1. Accept the GitHub invite.
> 2. Do PROJECT.md §16.1 (one-time setup, ~30 min). There's a macOS column and a Windows column; follow yours. `scripts/doctor.py` must show 0 FAILs, and `cat .env` must be blocked in Claude Code. Tell me if either isn't true.
> 3. Add your OS (macos/windows) to `.github/team.json`. We need at least one of each for the deploy tests.
> 4. Your lane is one GitHub issue assigned to you (`gh issue list --label lane --assignee @me`); all five are summarized in PROJECT.md §19. Your M0 tasks are due Wed 10/21.
> 5. Every session: §16.2 checklist, then `/start-session <task key>` (e.g. `/start-session B1`) and end with `/finish-session`.
> 6. Never paste the class key anywhere but your own `.env`.

### Step 9: Running the project day to day (A)

- **Update §0.1 Project status** whenever the phase, release, due date, or blockers change. AI assistants read it first to decide what to tell people.

- **Daily check (5 min):**
  - `gh issue list --label lane`: the progress count ("4 of 10 tasks") on each lane shows who's ahead or behind the current checkpoint
  - `gh pr list --state open`
  - Chase PRs waiting more than 12 h for review, and any `blocked` labels.
- **Async standup in team chat** each day. Each person posts: done / next / blocked + task keys.
- **New work:** add a task (with a new key, e.g. `B11`) to that lane in `scripts/github/issues.json`, run `python scripts/github/bootstrap.py --refresh`, then regenerate §19 with `python scripts/github/assignments.py`.
- **Due date announced or changed:**
  1. Edit the checkpoint and milestone dates in `issues.json` and §10, then `bootstrap.py --refresh`.
  2. Update GitHub with `gh api -X PATCH repos/OWNER/ai-jukebox/milestones/<number> -f due_on=YYYY-MM-DDT23:59:59Z`.
  3. Tell the team.
- **Bugs** found in testing are filed with the Bug template (or `/log-test` offers it) and assigned to the owning role.

---

## 19. The five lanes

Each person owns one lane, and each lane is **one GitHub issue** (label `lane`) holding the full task checklist; the issue body also lists every task's "Done when" criteria. Generated from `scripts/github/issues.json` + `.github/team.json`; regenerate with `python scripts/github/assignments.py` after changing either. "Needs" shows the tasks that must be done first, with the other lane's letter in brackets. Start with tasks that need nothing, or whose needs are ticked.

| Lane | Owner | OS | Tasks | Reviewer of their PRs | Mission (short) |
|---|---|---|---|---|---|
| **A: Platform & Release** | TBD | TBD | 13 | E | Make it possible for everyone else to build, and make sure what we submit installs, passes, and arrives on Canvas correctly. |
| **B: Song Generation** | TBD | TBD | 10 | D | Turn a user's style, mood, duration, and theme into a playable song in the library: instrumental, or vocal with original AI-written lyrics. |
| **C: Cover Art, Samples & Evidence** | TBD | TBD | 9 | B | Give every song its own matching FLUX cover, produce the three bundled sample songs and their generation log, and own the evidence the grader sees: starter prompt, screenshots, and the non-technical usability run. |
| **D: AI DJ & Launchers** | TBD | TBD | 9 | C | Make the DJ talk: a short, song-specific intro written by Qwen and spoken by Chatterbox before each queued song, with an optional uploaded MP3/WAV voice. |
| **E: Player, UX & QA** | TBD | TBD | 8 | A | Own the listening experience and the app's look: the app shell, library view, and a queue that plays DJ → song → DJ → song by itself with play/pause/skip. |

### Lane A: Platform & Release

**Mission:** Make it possible for everyone else to build, and make sure what we submit installs, passes, and arrives on Canvas correctly. You own the foundation (config, shared HTTP client, error model, data model, library), integration on main, and the release.

**Owns:** `.github/` (others may edit their own row in `team.json`); `scripts/` except `generate_samples.py`; `jukebox/config.py`, `errors.py`, `models.py`, `library.py`, `jobs.py`; `jukebox/clients/base.py`; `.env.example`; PROJECT.md §0.1 status and §7 endpoint table; README.md assembly; Tags, releases, and the Canvas submission

**Others are waiting on this lane for:** Config + ServiceError + shared client base to B, C, D (by Wed 10/21; everyone is blocked on this); Track/Job models + library to B, C, D, E (early M1); Filled-in §7.1 endpoint table to everyone; Integrated main branch (A7) and release candidates

| Task | Checkpoint | Title | Needs |
|---|---|---|---|
| A1 | M0 (Wed 10/21) | Set up repo: scaffold, labels, milestone, the 5 lane issues, templates, CI | — |
| A2 | M0 (Wed 10/21) | Config loader, .env.example, and scripts/check_config.py | A1, C0 (C) |
| A3 | M0 (Wed 10/21) | Shared HTTP client base + ServiceError and user-facing error messages | A2 |
| A4 | M0 (Wed 10/21) | Fill §7.1 endpoint contracts from class-endpoints.txt + scripts/check_endpoints.py | A2 |
| A5 | M0 (Wed 10/21) | Answer the section 14 open questions (Hermes, due date, repo access, network, Claude access) | — |
| A6 | M1 (Sun 10/25) | Track/Job models, thread-safe library, sample manifest loader, job store | A2 |
| A11 | M1 (Sun 10/25) | Make the pre-push hook executable in git and have doctor catch it | — |
| A12 | M2 (Tue 10/27) | Make the pre-push gate run the tests the way CI does | — |
| A13 | M2 (Tue 10/27) | Pin the developer tools in requirements-dev.txt | — |
| A7 | M2 (Tue 10/27) | Integration: song → cover → library → queue → DJ prefetch | B7 (B), C4 (C), D3 (D), E4 (E) |
| A8 | M3 (Wed 10/28) | Tag release candidate rc1 and fix deploy findings | A7, C6 (C), D6 (D) |
| A9 | M4 (Thu 10/29) | README assembly: setup, architecture, safeguards, contributions | E7 (E) |
| A10 | M4 (Thu 10/29) | Final release: secret scan, tag v1.0, ZIP, submit on Canvas | B10 (B), D9 (D) |

### Lane B: Song Generation

**Mission:** Turn a user's style, mood, duration, and theme into a playable song in the library: instrumental, or vocal with original AI-written lyrics. You also own the Qwen client that C and D depend on.

**Owns:** `jukebox/clients/qwen.py`, `jukebox/clients/acestep.py`; `jukebox/services/songs.py`; `jukebox/prompts/title.md`, `lyrics.md`; `jukebox/ui/generate_tab.py`; Tests for the above

**Others are waiting on this lane for:** Qwen client chat() to C (cover prompts) and D (DJ scripts): **highest priority in M1**; Song pipeline that adds tracks to the library and triggers the cover job (C); The README's design-choice write-up

| Task | Checkpoint | Title | Needs |
|---|---|---|---|
| B1 | M0 (Wed 10/21) | Spike: Qwen (port 9001) live call, thinking-mode check, latency | — |
| B2 | M0 (Wed 10/21) | Spike: ACE-Step (port 9007) instrumental + vocal calls, limits, latency | — |
| B3 | M1 (Sun 10/25) | Qwen client: chat(), think-stripping, JSON helper | A3 (A), B1 |
| B4 | M1 (Sun 10/25) | ACE-Step client: generate_music() | A3 (A), B2 |
| B5 | M1 (Sun 10/25) | Lyrics and title prompts (jukebox/prompts/) with parser | B3 |
| B6 | M1 (Sun 10/25) | Song generation service pipeline with staged status | A6 (A), B4, B5 |
| B7 | M1 (Sun 10/25) | Generate tab UI: style, mood, duration, instrumental/vocal, theme | B6, E2 (E) |
| B8 | M2 (Tue 10/27) | Input safeguard: strip/warn on real artist names in style tags | B6 |
| B9 | M4 (Thu 10/29) | README: song generation walkthrough + design-choice write-up | E7 (E) |
| B10 | M4 (Thu 10/29) | Docs-vs-app verification (on your OS): follow the README sections you didn't write | A9 (A), B9, C7 (C), D7 (D), E8 (E) |

### Lane C: Cover Art, Samples & Evidence

**Mission:** Give every song its own matching FLUX cover, produce the three bundled sample songs and their generation log, and own the evidence the grader sees: starter prompt, screenshots, and the non-technical usability run.

**Owns:** `jukebox/clients/flux.py`; `jukebox/services/art.py`; `jukebox/prompts/cover_art.md`; The placeholder cover image (team-made); `scripts/generate_samples.py` and everything in `samples/` (audio, covers, manifest, `GENERATION_LOG.md`); `docs/STARTER_PROMPT.md`; `docs/screenshots/`

**Others are waiting on this lane for:** Cover service by track_id to B and E; 3 sample songs to D and E for testing (by Mon 10/26); Starter prompt (before the build starts) and screenshots for the README

| Task | Checkpoint | Title | Needs |
|---|---|---|---|
| C1 | M0 (Wed 10/21) | Spike: FLUX (port 9006) live call, output format, latency | — |
| C0 | M0 (Wed 10/21) | Write docs/STARTER_PROMPT.md (verbatim prompt + team additions) and get team review BEFORE any app code | — |
| C2 | M1 (Sun 10/25) | FLUX client: generate_image() | A3 (A), C1 |
| C3 | M1 (Sun 10/25) | Cover-art prompt builder (Qwen → FLUX prompt) with safety suffixes | B3 (B) |
| C4 | M1 (Sun 10/25) | Cover service, display by track_id, placeholder, and Retry cover | A6 (A), C2, C3 |
| C5 | M2 (Tue 10/27) | scripts/generate_samples.py using the app's own services | B6 (B), C4 |
| C6 | M2 (Tue 10/27) | Generate and commit the 3 sample songs | C5 |
| C8 | M3 (Wed 10/28) | Non-technical usability run of the app from the README alone (TC-13) | A8 (A) |
| C7 | M4 (Thu 10/29) | Screenshots + README sample-songs section | C6 |

### Lane D: AI DJ & Launchers

**Mission:** Make the DJ talk: a short, song-specific intro written by Qwen and spoken by Chatterbox before each queued song, with an optional uploaded MP3/WAV voice. You also own the one-click launchers the grader uses and the reliability pass.

**Owns:** `jukebox/clients/chatterbox.py`; `jukebox/services/dj.py`; `jukebox/prompts/dj.md`; `jukebox/ui/dj_settings.py` (voice upload); `run.sh`, `run.bat`, `requirements.txt` (pins)

**Others are waiting on this lane for:** DJ clip for any track, prefetchable, to E (player); Launchers that match PROJECT.md §0.4 to everyone and the grader; The README's limitation write-up

| Task | Checkpoint | Title | Needs |
|---|---|---|---|
| D1 | M0 (Wed 10/21) | Spike: Chatterbox (port 9008) default voice + WAV and MP3 reference voices | — |
| D2 | M1 (Sun 10/25) | Chatterbox client: speak() | A3 (A), D1 |
| D3 | M1 (Sun 10/25) | DJ commentary prompt + service (song-specific, 30–50 words) | B3 (B), D2 |
| D4 | M1 (Sun 10/25) | Voice reference upload: validation, storage, reset to default | D2, E2 (E) |
| D5 | M2 (Tue 10/27) | DJ prefetch, cache by (track_id, voice_id), and failure fallback | D3, E4 (E) |
| D6 | M2 (Tue 10/27) | Pinned requirements.txt + run.sh (macOS) / run.bat (Windows), tested on both | E2 (E) |
| D8 | M3 (Wed 10/28) | Reliability pass: generate while playing, repeated use, restart (TC-12, TC-14) | A8 (A) |
| D7 | M4 (Thu 10/29) | README: DJ walkthrough + limitation/failure investigated | E7 (E) |
| D9 | M4 (Thu 10/29) | Docs-vs-app verification (on your OS): follow the README sections you didn't write | A9 (A), B9 (B), C7 (C), D7, E8 (E) |

### Lane E: Player, UX & QA

**Mission:** Own the listening experience and the app's look: the app shell, library view, and a queue that plays DJ → song → DJ → song by itself with play/pause/skip. You also own testing: the live test matrix and the Windows/macOS deploy tests.

**Owns:** `app.py`; `jukebox/ui/` layout, `player_panel.py`, `library_tab.py`; `jukebox/services/player.py`; `docs/TEST_EVIDENCE.md` and the §12 test matrix

**Others are waiting on this lane for:** App shell to B and D (by Wed 10/21) so their UI has a place to live; Queue/player that plays DJ clips (D) and covers (C); Test results and deploy-test findings for the README

| Task | Checkpoint | Title | Needs |
|---|---|---|---|
| E1 | M0 (Wed 10/21) | Spike: Gradio playback approach (Option A native gr.Audio vs Option B custom HTML5) | — |
| E2 | M0 (Wed 10/21) | Gradio app shell: thin app.py, layout skeleton, placeholder panels | E1, C0 (C) |
| E3 | M1 (Sun 10/25) | Queue model (services/player.py) with unit tests | A6 (A) |
| E4 | M1 (Sun 10/25) | Player panel: play/pause, skip, now playing, up-next with covers, auto-advance | E2, E3 |
| E5 | M2 (Tue 10/27) | Error and recovery pass (TC-F1 to TC-F5) | A7 (A) |
| E6 | M3 (Wed 10/28) | Independent deploy test from the GitHub ZIP on Windows AND macOS (TC-10a, TC-10b) | A8 (A) |
| E7 | M3 (Wed 10/28) | Run the full live test matrix on the release candidate | A8 (A) |
| E8 | M4 (Thu 10/29) | README: test results section | E7 |

### Load per checkpoint

| Checkpoint | A | B | C | D | E | Tasks |
|---|---|---|---|---|---|---|
| M0 Foundations & spikes (due Wed 10/21) | 5 | 2 | 2 | 1 | 2 | 12 |
| M1 Vertical slices (due Sun 10/25) | 2 | 5 | 3 | 3 | 2 | 15 |
| M2 Integration & samples (due Tue 10/27) | 3 | 1 | 2 | 2 | 1 | 9 |
| M3 Independent deploy test (due Wed 10/28) | 1 | 0 | 1 | 1 | 2 | 5 |
| M4 Docs, evidence, submit (due Thu 10/29) | 2 | 2 | 1 | 2 | 1 | 8 |
