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
Open the **Generate** tab. Each choice has a one-line hint under its name.

> **TODO (B9, on rc1):** screenshot of the Generate tab with the form filled in (`docs/screenshots/`, no credentials visible).

**An instrumental**
1. **Style:** pick a genre, for example **lo-fi hip hop**. You can add your own words under **Extra style tags** (instruments, an era, a feel), separated by commas.
2. **Mood:** pick how it should feel, for example **mellow**.
3. **Length (seconds):** drag the slider or type a number from **10 to 120**. The default is 60.
4. **Vocal or instrumental:** choose **Instrumental**.
5. **Song idea (optional):** what the song is about, for example *a rainy evening*. It shapes the title and the cover.
6. Click **Generate**. The button greys out, and the status line shows **Queued**, then names each stage and counts the seconds, for example "**Composing music…** · 4 s · usually about 10 s, longer when the class servers are busy". When it says **Added to your library**, the result card shows the title, and the cover a few seconds later.

**A vocal song**

Same steps, but choose **Vocal** in step 4. The first stage after **Queued** is **Writing lyrics…** instead of **Naming your track…**, and the result card also shows the lyrics, which the text model (Qwen) writes for each song. Vocal songs sound best at 30 seconds or more.

> **TODO (B9, on rc1):** screenshots of an instrumental and a vocal result card, each with its cover.

**What to expect**
- **Wait:** about 5 to 10 seconds per song when the class servers are quiet. We measured 4.8 to 9.5 s in B5 (#32), 5.5 to 7 s in B6 (#36), and a reviewer saw 7 s. Most of it is the music model (ACE-Step, 4.4 to 8.4 s); the text model (Qwen) takes 0.4 to 1.5 s. The page says "usually about 10 s". It can take longer when many people use the class servers, and the status line keeps counting so you can see it hasn't frozen.
- **The cover** is painted after the song is saved, usually 2 to 3 s later. The card shows a placeholder and "Painting cover…" until it arrives. If the cover fails, the song is kept, and a **Retry cover** button appears.
- **Phrases that point at a real artist are removed** when the name starts with a capital letter. In **Extra style tags**, phrases like "in the style of …", "featuring …" or "…'s voice" with an artist's name show a note under the box ("Removed …"), and the song is generated without them. **Song idea** only removes "in the style of …" (or "in the vein / spirit / manner of …"), "sounds like …" and "à la …", because a song idea is a subject and may name a person. The app asks the models for original songs; see [Known issues](#known-issues) for what it can't prevent.
- **If something fails,** the status line says what went wrong in plain words, your choices stay filled in, and **Retry** appears when trying again can help (a slow or unreachable class server). If your settings are wrong, it says to fix them and restart.
- **Play now / Add to queue** on the result card are greyed out for now, with the note "Play now and Add to queue work once the player is connected."

  > **TODO (B9, after A7, #55):** replace this with the steps once the player is connected, and add a screenshot.
- Generated songs stay in the library until you stop the app.

> **TODO (B9, on rc1):** link the measured runs in [Test results](#test-results) (TC-01 instrumental, TC-02 vocal, TC-03 songs kept across tabs, TC-F1 bad credentials, TC-F2 a class server not answering).

## Sample songs
_TODO (C): what's included and how they were generated; link samples/GENERATION_LOG.md._

## Architecture
_TODO (A)._

## Test results
_TODO (E): from docs/TEST_EVIDENCE.md. Separate completed tests from unchecked claims._

## Known issues
_TODO: other lanes' entries._

**Song generation (B)**
- **The default singing voice can sound like a famous singer.** In testing, one indie-pop song with no artist named anywhere sounded very like a well-known pop singer. That's ACE-Step's own default voice; a style tag can't reliably steer it away from one person. The app screens the part it controls: phrases naming an artist that the user types (next item).
- **The artist screen only catches explicit forms.** In Extra style tags it removes "in the style (vein, spirit, manner) of / sounds like / à la *Name*", "inspired by / influenced by / similar to *Name*", "featuring / feat. / ft. / sung by / vocals by / cover of *Name*", "*Name*-style", "*Name*'s voice" and "like *Name*". Song idea removes only "in the style (vein, spirit, manner) of / sounds like / à la *Name*", so "inspired by *Name*", "featuring *Name*" or "*Name*'s voice" typed there stays. Not caught anywhere:
  - a bare name ("*Name* pop");
  - a name that doesn't start with a capital letter ("in the style of *name*", or a name that starts with a digit). Lowercase was left out on purpose: catching it also removed descriptions like "inspired by the sea";
  - a band named after a place or a genre: "pop in the style of Chicago" drops "in the style of" but keeps "Chicago", with no note;
  - "*Name* vibe", "*Name* type beat", "*Name*-ish", "*Name*-like", "a song by *Name*";
  - a band name with a comma ("Earth, Wind & Fire style" leaves "Earth");
  - a name that starts with two `$`: `pop, $$uicideboy$$ style` leaves a stray `$`.

  The last two keep the real names because the problem is in how those names are spelled.

  It can also remove a capitalized phrase that isn't an artist ("sounds like Heaven"), so the note says the removed text *may* point at an artist.

  It's pattern-based on purpose: a list of artist names could never be complete, and looser patterns kept removing everyday styles ("Golden Hour vibes", "Workout type beat"). The lyrics and title prompts also tell Qwen never to name or imitate a real artist.
- **The music model doesn't always sing every word.** Even with lyrics sized to the length, 60 s songs have dropped their 2-line outro, a few words, or one line of the chorus (see [Design judgment](#design-judgment)). The lyrics on the result card are what was sent, not a transcript.
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

**Why.** Our first plan scaled lyrics with length, "roughly 2 sections per 30 s" (PROJECT.md §8.1), so a 45–60 s song got 18 lines. ACE-Step doesn't speed up to fit more words: it sings about one verse and one chorus, then **skips whole sections from the middle**, so the song loses its story. In the B6 listening tests, one check during the C3 review, and the shipped samples (C6), each song was generated on the class servers and a teammate counted the lines actually sung against the lyrics sent:

| Song (test) | Length | Lines sent | Lines sung | What happened |
|---|---|---|---|---|
| Freedom Unlocked (B6) | 45 s | 18 | about 10 | second verse and chorus skipped |
| Neon Highways (B6) | 50 s | 18 | 8 | verse, half a chorus, outro |
| Chasing Sunsets (B6) | 60 s | 18 | 8 | verse, half a chorus, outro |
| sample_02 spec (C3 review, #33) | 60 s | 18 | all but lines 6–9 | the chorus cut after one line, then a jump into verse 2 |
| Freedom Bell (B6) | 45 s | **10** | **10** | all sung |
| Open Road (B6) | 60 s | **10** | 8 | verse and chorus sung; the 2-line outro dropped |
| Windows Down (sample_02, C6) | 60 s | **10** | 10 | every line sung, but "Together now" dropped from the chorus and the outro slurred |
| Dust on the Gate (sample_03, C6) | 60 s | **10** | 9 | one chorus line skipped |

With 18 lines, three of the four songs lost about 8 lines or more, and the fourth lost 4 lines from the middle. With 10 lines, no song lost more than 2 lines or a whole section from the middle: one was sung in full, one dropped its 2-line outro, one dropped a few words and slurred its outro, and one skipped a single chorus line (the two C6 rows were counted by @gunnaroc against the lyrics while reviewing #51). So the fix greatly reduces what's lost, but doesn't make ACE-Step sing every word. Two songs weren't counted line by line: an earlier 60 s song with 18 lines (B5, *Static on the Road*) sounded clean to the listener, and a 10-line punk song (B6, *Debt Degree*) ran cleanly. Too few lines may have its own problem: in B2, a 60 s song with only a verse and a chorus stopped abruptly at about 58 s. The spike's likely cause was too few lyrics for the length (not tested on its own), so the 40–74 s plan adds a short outro. Because of the sample_02 spec result, we asked lane C to generate the shipped samples only after this fix; their generation log (`samples/GENERATION_LOG.md`) shows both vocal samples were sent the 10-line plan.

**Trade-off.** Songs under 75 s have one verse and one chorus, not two. Songs of 75 s and up still get 18 lines, and the 120 s maximum hasn't been listened to line by line yet.

> **TODO (B9, on rc1):** add the TC-02 vocal run (lines sent vs. sung) from [Test results](#test-results).

## Safeguards
_TODO (A)._

## Team & contributions
_TODO (A): member → role → PRs authored / reviewed._
