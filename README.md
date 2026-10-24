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
_TODO (D/A): Python version, tested OSes, network access to the class host, browser autoplay note._

## Setup
### macOS
_TODO (D): install Python → extract ZIP → `cp .env.example .env` and fill in → `bash run.sh` → open http://127.0.0.1:7860_

### Windows
_TODO (D): install Python (`py`) → extract ZIP → `copy .env.example .env` and fill in → `.\run.bat` → open http://127.0.0.1:7860_

## Using the app
_TODO: cover art (C), DJ (D), playback controls (E)._

### Generate a song
Open the **Generate** tab. Every control has a one-line hint under its name.

> **TODO (B9, on rc1):** screenshot of the Generate tab with the form filled in (`docs/screenshots/`, no credentials visible).

**An instrumental**
1. **Style:** pick a genre, for example **lo-fi hip hop**. You can add your own words under **Extra style tags** (instruments, an era, a feel), separated by commas.
2. **Mood:** pick how it should feel, for example **mellow**.
3. **Length (seconds):** drag the slider or type a number from **10 to 120**. The default is 60.
4. **Vocal or instrumental:** choose **Instrumental**.
5. **Song idea (optional):** what the song is about, for example *a rainy evening*. It shapes the title and the cover.
6. Click **Generate**. The button greys out, and the status line names each stage and counts the seconds, for example "**Composing music…** · 4 s · usually about 10 s". When it says **Added to your library**, the result card shows the title and the cover.

**A vocal song**

Same steps, but choose **Vocal** in step 4. The status line adds **Writing lyrics…**, and the result card also shows the lyrics, which Qwen writes for each song. Vocal songs sound best at 30 seconds or more.

> **TODO (B9, on rc1):** screenshots of an instrumental and a vocal result card, each with its cover.

**What to expect**
- **Wait:** about 6 to 8 seconds per song with a quiet class queue (Qwen 0.4–1.5 s, then ACE-Step about 5 s). It can be longer when the class servers are busy, and the status line keeps counting so you can see it hasn't frozen.
- **The cover** is painted after the song is saved, usually 2 to 3 s later. The card shows a placeholder and "Painting cover…" until it arrives. If the cover fails, the song is kept, and a **Retry cover** button appears.
- **Real artist names are removed.** Typing "in the style of …", "featuring …" or "…'s voice" with an artist's name shows a note under the box ("Removed …"), and the song is generated without it. Songs are original and never imitate real artists.
- **If something fails,** the status line says what went wrong in plain words, your choices stay filled in, and **Retry** appears when trying again can help (a slow or unreachable class server). If your settings are wrong, it says to fix them and restart.
- **Play now / Add to queue** on the result card send the new song to the player.

  > **TODO (B9, after A7):** confirm these two steps once the integration connects them, and add a screenshot.
- Generated songs stay in the library until you stop the app.

> **TODO (B9, on rc1):** link the measured runs in [Test results](#test-results) (TC-01 instrumental, TC-02 vocal, TC-03 failure).

## Sample songs
_TODO (C): what's included and how they were generated; link samples/GENERATION_LOG.md._

## Architecture
_TODO (A)._

## Test results
_TODO (E): from docs/TEST_EVIDENCE.md. Separate completed tests from unchecked claims._

## Known issues
_TODO: other lanes' entries._

**Song generation (B)**
- **The default singing voice can sound like a famous singer.** In testing, one indie-pop song with no artist named anywhere sounded very like a well-known pop singer. That's ACE-Step's own default voice; a style tag can't reliably steer it away from one person. The app prevents the part it controls: artist names typed by the user (next item).
- **The artist screen only catches explicit forms.** Removed: "in the style of / sounds like / inspired by / à la *Name*", "featuring / feat. / ft. / sung by / vocals by / cover of *Name*", "*Name*-style", "*Name*'s voice" and "like *Name*". Not caught:
  - a bare name ("Taylor Swift pop");
  - a lowercase name ("in the style of adele");
  - "*Name* vibe", "*Name* type beat", "*Name*-ish", "a song by *Name*";
  - a band name with a comma ("Earth, Wind & Fire style" leaves "Earth");
  - a name that starts with two "$" ("$$uicideboy$$").

  It's pattern-based on purpose: a list of artist names could never be complete, and looser patterns kept removing everyday styles ("Golden Hour vibes", "Workout type beat"). The lyrics and title prompts also tell Qwen never to name or imitate a real artist.
- **ACE-Step sometimes drops the last section.** At 60 s, a few songs left out the 2-line outro (see [Design judgment](#design-judgment)).
- **One song at a time.** The Generate button runs one request at a time. A second browser tab's request waits silently until the first finishes. The app is meant for one person on their own computer.

## Design judgment
_TODO (D, task D7): one limitation or failure we investigated and what we learned._

### Design choice: lyrics sized to what ACE-Step will sing (B)
**The choice.** The lyrics prompt asks Qwen for only as many lines as ACE-Step actually sings at the requested length (`plan_sections` in `jukebox/services/songs.py`):

| Length | Lyrics asked for |
|---|---|
| under 20 s | a 2-line verse |
| 20–29 s | 2-line verse and 2-line chorus |
| 30–39 s | 4-line verse and 4-line chorus |
| 40–74 s | verse, chorus and a 2-line outro (10 lines) |
| 75 s and up | verse, chorus, verse, chorus, outro (18 lines) |

**Why.** Our first plan scaled lyrics with length, "about 2 sections per 30 s", so a 45–60 s song got 18 lines. ACE-Step doesn't speed up to fit more words: it sings about one verse and one chorus, then **skips whole sections from the middle**, so the song loses its story. Every vocal test song was generated on the class servers and listened to by a person, counting the lines actually sung against the lyrics sent:

| Song (test) | Length | Lines sent | Lines sung | What happened |
|---|---|---|---|---|
| Freedom Unlocked (B6) | 45 s | 18 | about 10 | second verse and chorus skipped |
| Neon Highways (B6) | 50 s | 18 | 8 | verse, half a chorus, outro |
| Chasing Sunsets (B6) | 60 s | 18 | 8 | verse, half a chorus, outro |
| sample_02 spec (C5 review) | 60 s | 18 | all but lines 6–9 | the chorus cut after one line, then a jump into verse 2 |
| Freedom Bell (B6) | 45 s | **10** | **10** | all sung |
| Open Road (B6) | 60 s | **10** | 8 | verse and chorus sung; the 2-line outro dropped |

With 10 lines, the whole verse and chorus are always sung. At worst the short outro is left out at the end, which a listener hardly notices, rather than a gap in the middle. Because of the sample_02 result, we asked lane C to generate the shipped samples only after this fix, so the lyrics in their generation log match what is sung.

> **TODO (B9, on rc1):** confirm the committed samples (C6) were generated with this fix.

**Trade-off.** Songs under 75 s have one verse and one chorus, not two. Songs of 75 s and up still get 18 lines, and the 120 s maximum hasn't been listened to line by line yet.

> **TODO (B9, on rc1):** add the TC-02 vocal run (lines sent vs. sung) from [Test results](#test-results).

## Safeguards
_TODO (A)._

## Team & contributions
_TODO (A): member → role → PRs authored / reviewed._
