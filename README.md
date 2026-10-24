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
- **The class credentials** in `class-endpoints.txt`, from the course materials.
- **A browser.** Browsers block sound until you click on the page, so start playback with **Play queue**.

## Setup
The launcher does the technical work: on the first start it creates your settings file and opens it for
you; on the next start it installs what the app needs, checks the class servers, and opens the app in your
browser at **http://127.0.0.1:7860**.

### Windows
1. **Install Python** from **python.org/downloads** (3.12 recommended). On the installer's first screen,
   tick **Add python.exe to PATH**, then click **Install Now**.
2. **Unblock the ZIP before you extract it.** Right-click the downloaded ZIP, choose **Properties**, tick
   **Unblock** at the bottom, and click **OK**. Without this, Windows' Smart App Control blocks `run.bat`
   ("Smart App Control blocked a file that may be unsafe"), with no option to run it anyway.
3. **Extract the ZIP:** right-click it, choose **Extract All…**, set the destination to `C:\jukebox`, and
   click **Extract**. Don't put the folder inside OneDrive, and don't run anything from inside the ZIP.
4. **First start:** in the extracted folder, double-click **`run.bat`**. If Windows shows "Windows protected
   your PC", click **More info**, then **Run anyway**. The launcher creates a settings file called `.env`,
   opens it in Notepad, and stops.
5. **Fill in the settings:** change only the first 5 settings, `CLASS_API_KEY` and the four lines ending in
   `_BASE_URL`, using the values from `class-endpoints.txt`. Put each value right after the `=`, with no
   spaces or quotes. Leave the other lines as they are. Save, close Notepad, and keep the name `.env`. This
   file stays on your computer: never email it or upload it.
6. **Start the app:** double-click **`run.bat`** again. The first time, it installs what the app needs,
   which takes a few minutes. Then it checks the class servers and opens the app in your browser. Keep the
   black launcher window open while you use the app; **close that window to stop the app**.

### macOS
1. **Install Python** from **python.org/downloads** (3.12 recommended, the `.pkg` installer).
2. **Extract the ZIP:** double-click it in Downloads, then drag the folder it creates into your home folder
   (Finder > Go > Home). Don't put it inside iCloud Drive.
3. **First start:** open **Terminal**, type `bash ` (with a space after it), drag **`run.sh`** from the
   folder into the Terminal window, and press **Enter**. The launcher creates a settings file called `.env`,
   opens it in TextEdit, and stops.
4. **Fill in the settings:** change only the first 5 settings, `CLASS_API_KEY` and the four lines ending in
   `_BASE_URL`, using the values from `class-endpoints.txt`. Put each value right after the `=`, with no
   spaces or quotes. Leave the other lines as they are. Save and keep the name `.env`. Finder hides files
   whose names begin with a dot: press **Cmd+Shift+.** to see it. This file stays on your computer: never
   email it or upload it.
5. **Start the app:** run `bash run.sh` again the same way. The first time, it installs what the app needs,
   which takes a few minutes. Then it checks the class servers and opens the app in your browser. Keep the
   Terminal window open while you use the app; close it or press **Ctrl+C** to stop the app.

### If something goes wrong
| What you see | What to do |
|---|---|
| "Smart App Control blocked a file that may be unsafe" (Windows) | Delete the extracted folder, unblock the ZIP (Windows step 2), and extract it again. |
| "Python 3.11 or newer was not found" | Re-run the Python installer (Windows: tick **Add python.exe to PATH**), then open a new window and start the launcher again. |
| The launcher lists settings that still need fixing | Open `.env` (the launcher opens it for you), fix the named settings, save, and start the launcher again. |
| "The app is already running in another window" | It is: the launcher opens the running app in your browser instead of starting a second copy. |
| A service "is unreachable right now" or "took too long" | The class servers may be busy, or your network may block them. Try again later. |
| No sound | Click on the page first, then check your volume and output device. |

## Using the app
_TODO: song generation (B), cover art (C), DJ (D), playback controls (E)._

## Sample songs
_TODO (C): what's included and how they were generated; link samples/GENERATION_LOG.md._

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
