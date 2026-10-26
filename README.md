# AI Jukebox

> **AI assistants and newcomers:** start at [PROJECT.md §0](PROJECT.md#0-start-here). It has step-by-step paths for running the app with no coding, setting up to build it, and creating the repo.

> Work in progress for MBAX 6418 Assignment 3. The team plan lives in [PROJECT.md](PROJECT.md). This README becomes the graded documentation; its outline is PROJECT.md §11.

An app that generates custom songs (ACE-Step), matching cover art (FLUX), and plays a queue with AI DJ commentary (Qwen + Chatterbox) between tracks, using only the class services.

## For teammates: getting started
Full instructions with a macOS and a Windows column: PROJECT.md §16.1. Short version:

| | macOS (Terminal) | Windows (PowerShell) |
|---|---|---|
| 1. Setup | `python3 scripts/setup_dev.py` | `py scripts\setup_dev.py` |
| 2. Fill in `.env` | `open -e .env` | `notepad .env` |
| 3. Activate | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| 4. Check | `python scripts/doctor.py` | `python scripts\doctor.py` |
| 5. Work | `claude` → `/start-session <task key>` | `claude` → `/start-session <task key>` |

Never commit `.env`.

## Overview
_TODO (A): what the app does + main screenshot._

## Requirements
- **A computer:** Windows 10 or 11, or macOS 13 or newer.
- **Python 3.11 or newer** (3.12 recommended). The steps below show how to install it.
- **Network access to the class servers.** A VPN or the campus network was not needed when tested from a
  home network.
- **The class credentials** in `class-endpoints.txt`, from the course materials (ask the instructors if you
  don't have it).
- **The app ZIP:** from the Canvas submission, or from the repository's **Releases** page on GitHub
  (**Source code (zip)**).
- **A browser.** Browsers block sound until you click on the page, so start playback with **Play queue**.

## Setup
The launcher does the technical work: on the first start it creates your settings file and opens it for
you; on the next start it installs what the app needs, checks the class servers, and opens the app in your
browser, usually at **http://127.0.0.1:7860** (if that port is busy, the launcher shows the address it used).

### Windows
1. **Install Python** from **python.org/downloads** (3.12 recommended). On the installer's first screen,
   tick **Add python.exe to PATH**, then click **Install Now**.
2. **Unblock the ZIP before you extract it.** Right-click the downloaded ZIP, choose **Properties**, and at
   the bottom of the General tab tick **Unblock**, then click **OK** (no Unblock box means it's already
   unblocked). Without this, Windows' Smart App Control blocks `run.bat` ("Smart App Control blocked a file
   that may be unsafe"), with no option to run it anyway.
3. **Extract the ZIP:** right-click it, choose **Extract All…**, set the destination to `C:\jukebox`, and
   click **Extract**. Open the extracted folder until you see `run.bat` and `README.md`: that's the **app
   folder**. Don't put it inside OneDrive, and don't run anything from inside the ZIP.
4. **First start:** in the app folder, double-click **`run.bat`**. If Windows shows "Windows protected your
   PC", click **More info**, then **Run anyway**. The launcher creates a settings file called `.env`, opens
   it in Notepad, and waits: press any key or close its window.
5. **Fill in the settings:** change only the first 5 settings, `CLASS_API_KEY` and the four lines ending in
   `_BASE_URL`. For each one, replace the placeholder text after the `=` with the value from
   `class-endpoints.txt`, with no spaces or quotes. Leave the other lines as they are. Save, close Notepad,
   and keep the name `.env`. This file stays on your computer: never email it or upload it.
6. **Start the app:** double-click **`run.bat`** again. The first time, it installs what the app needs,
   which takes a few minutes. Then it checks the class servers and opens the app in your browser. Keep the
   black launcher window open while you use the app; **close that window to stop the app**.

### macOS
1. **Install Python** from **python.org/downloads** (3.12 recommended, the `.pkg` installer).
2. **Extract the ZIP:** double-click it in Downloads, then drag the folder it creates into your home folder
   (Finder > Go > Home). Open the folder until you see `run.sh` and `README.md`: that's the **app folder**.
   Don't put it inside iCloud Drive.
3. **First start:** open **Terminal**, type `bash ` (with a space after it), drag **`run.sh`** from the
   folder into the Terminal window, and press **Enter**. The launcher creates a settings file called `.env`,
   opens it in TextEdit, and stops.
4. **Fill in the settings:** change only the first 5 settings, `CLASS_API_KEY` and the four lines ending in
   `_BASE_URL`. For each one, replace the placeholder text after the `=` with the value from
   `class-endpoints.txt`, with no spaces or quotes. Leave the other lines as they are. Save and keep the
   name `.env`. Finder hides files
   whose names begin with a dot: press **Cmd+Shift+.** to see it. This file stays on your computer: never
   email it or upload it.
5. **Start the app:** run `bash run.sh` again the same way. The first time, it installs what the app needs,
   which takes a few minutes. Then it checks the class servers and opens the app in your browser. Keep the
   Terminal window open while you use the app; close it or press **Ctrl+C** to stop the app.

### If something goes wrong
| What you see | What to do |
|---|---|
| "Smart App Control blocked a file that may be unsafe" (Windows) | Delete the extracted folder, unblock the ZIP (Windows step 2), and extract it again. Don't use **Run as administrator**, and don't turn Smart App Control off: it can't be turned back on without reinstalling Windows. |
| "An Application Control policy has blocked this file" (Windows, while the app starts) | Delete the `.venv` folder in the app folder and start the launcher again; it reinstalls the tested versions. |
| "Python 3.11 or newer was not found" | Re-run the Python installer (Windows: tick **Add python.exe to PATH**), then open a new window and start the launcher again. |
| The launcher lists settings that still need fixing | Open `.env` (the launcher opens it for you), fix the named settings, save, and start the launcher again. |
| "The app is already running in another window" | It is: the launcher opens the running app in your browser instead of starting a second copy. |
| A service "rejected our credentials" | A value in `.env` is wrong. Copy it again from `class-endpoints.txt`, with no extra spaces, then restart the launcher. |
| A service "is unreachable right now" or "took too long" | The class servers may be busy, or your network may block them. Use **Retry** in the app, or try again later. |
| The browser says it "can't connect" | The launcher window must stay open while you use the app. Start the launcher again. |
| No sound | Click on the page first, then check your volume and output device. |

## Using the app
_TODO: song generation (B), cover art (C), DJ (D), playback controls (E)._

## Sample songs

The app ships with three ready-to-play sample songs, so the player has something to play the moment the
app starts: press **Play queue**. Each has a title and its own cover.

| # | Title | Kind | Style | Mood | Length |
|---|---|---|---|---|---|
| 1 | Midnight Notes Fade | Instrumental | lo-fi hip hop, jazzy keys, vinyl crackle, soft drums | mellow | 60 s |
| 2 | Windows Down | Vocal | upbeat pop, summery, bright synths, catchy chorus, warm natural female vocals | joyful | 60 s |
| 3 | Dust on the Gate | Vocal | cinematic folk, acoustic guitar, strings, warm natural male vocals | melancholy | 60 s |

The files are in `samples/`: audio in `samples/audio/`, covers in `samples/covers/`, and the track details
in `samples/manifest.json`, which the app loads at startup.

### How the sample songs, lyrics, and covers were generated

- **Everything is AI-generated with the class services, through the app's own code.** One script,
  `scripts/generate_samples.py`, runs each sample through the same pipeline as the Generate tab:
  1. **Qwen3.6-35B-A3B** (port 9001) writes the title and, for the vocal songs, the lyrics.
  2. **ACE-Step 1.5 XL Turbo** (port 9007) makes the music from the style tags and lyrics.
  3. **Qwen** writes an image prompt from the song's title, style, mood, theme and lyrics, and
     **FLUX.2 klein 4B** (port 9006) paints the cover from it.
- **All lyrics and titles are written by Qwen.** No lyric, title, cover, or sound was written, drawn, or
  edited by a person. If a lyric had needed changing, the sample would have been regenerated, not edited.
- **Inputs:** the three style, mood and theme combinations in the table above (themes: late-night study
  session, road trip with friends, leaving a hometown), chosen by the team beforehand to show range (one
  instrumental, two vocal songs). The style tags name no artists or songs.
- **Seeds:** each sample's music and cover were sent a fixed seed (101, 202, 303), which is recorded in the
  log. In the team's early spike tests, the same seed and image prompt repeated the same cover, but the same
  seed did not reliably repeat the same audio, and Qwen gets no seed, so its words can differ each run. So
  the committed files are the record of what was generated, not something to regenerate.
- **Who and when:** generated by @felcervino on 2026-10-24, from commit `d7783d1` on the C6 branch: the
  code on `main` at `e925d7d` plus three small fixes to the script's messages and log formatting (the
  song and cover pipeline was unchanged). #51 later squash-merged those fixes together with the samples.
- **Human checks:** every song was listened to the end and every cover looked at, for fit with its style
  and mood and for text, logos, or faces. All passed. Sample 1's cover shows small unreadable
  handwriting-like marks on an open book; the people on the covers of samples 2 and 3 are seen only from
  behind.
- **Originality spot check:** for each vocal song, two distinctive lines were searched as exact phrases on
  the web: no match was found for any of the four. This is a limited check, not proof.
- **Full record:** [`samples/GENERATION_LOG.md`](samples/GENERATION_LOG.md) has, for each sample, the
  inputs, every service call with its model, port and timing, the Qwen title/lyrics prompt and the
  ACE-Step style tags exactly as the pipeline sent them, the full lyrics as generated, the exact FLUX
  prompt, and the human listening, cover and originality checks.

## Architecture
_TODO (A)._

## Test results
_TODO (E): from docs/TEST_EVIDENCE.md. Separate completed tests from unchecked claims._

## Known issues
_TODO._

## Design judgment
_TODO (B, D): one design choice justified by testing; one limitation investigated._

## Safeguards
_TODO (A)._

## Team & contributions
_TODO (A): member → role → PRs authored / reviewed._
