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
_TODO: DJ (D), playback controls (E)._

### Generate a song
Open the **Generate** tab. Each choice has a one-line hint under its name.

![The Generate tab filled in for a vocal song (pop, upbeat, 60 s, song idea "road trip") and its result: title, cover, lyrics, Play now and Add to queue](docs/screenshots/generate-vocal-song.png)

*The Generate tab after a vocal song (pop, upbeat, 60 s, idea "road trip"): the form, the status line, and the result card with its cover and lyrics.*

**An instrumental**
1. **Style:** pick a genre, for example **lo-fi hip hop**. You can add your own words under **Extra style tags** (instruments, an era, a feel), separated by commas.
2. **Mood:** pick how it should feel, for example **mellow**.
3. **Length (seconds):** drag the slider or type a number from **10 to 120**. The default is 60.
4. **Vocal or instrumental:** choose **Instrumental**.
5. **Song idea (optional):** what the song is about, for example *a rainy evening*. It shapes the title and the cover.
6. Click **Generate**. The button greys out, and the status line shows **Queued**, then names each stage and counts the seconds, for example "**Composing music…** · 4 s · usually about 10 s, longer when the class servers are busy". When it says **Added to your library**, the result card shows the title, and the cover a few seconds later.
7. **Play it.** When the song is ready, **Play now** and **Add to queue** on the result card turn on. **Play now** plays the song at once in the player on the right. **Add to queue** puts it at the end of the queue, without interrupting the song that's playing. If nothing is playing, press **Play queue** to start it.

**A vocal song**

Same steps, but choose **Vocal** in step 4. The first stage after **Queued** is **Writing lyrics…** instead of **Naming your track…**, and the result card also shows the lyrics, which the text model (Qwen) writes for each song. Vocal songs sound best at 30 seconds or more.

**Not sure what to make?** Click **Surprise me**, next to **Generate**. It fills the form with a random style, mood, length (30 to 90 seconds), vocal or instrumental, and song idea, and clears **Extra style tags**. Nothing is made yet: change anything you like, then click **Generate**. It's greyed out while a song is being made.

The vocal result card is in the screenshot above, and an instrumental one is under [Cover art](#cover-art).

![The player: Now playing with the song's title and cover, the audio player, and Up next with the next song's cover](docs/screenshots/player-now-playing-dj.png)

*The player playing a vocal sample song, with the next song under **Up next**.*

**What to expect**
- **Wait:** about 5 to 10 seconds per song when the class servers are quiet. We measured 4.8 to 9.5 s in B5 (#32), 5.5 to 7 s in B6 (#36), and a reviewer saw 7 s. Most of it is the music model (ACE-Step, 4.4 to 8.4 s); the text model (Qwen) takes 0.4 to 1.5 s. The page says "usually about 10 s". It can take longer when many people use the class servers, and the status line keeps counting so you can see it hasn't frozen.
- **The cover** is painted after the song is saved, usually 2 to 3 s later. The card shows a placeholder and "Painting cover…" until it arrives. If the cover fails, the song is kept, and a **Retry cover** button appears.
- **Phrases that point at a real artist are removed** when the name starts with a capital letter. In **Extra style tags**, phrases like "in the style of …", "featuring …" or "…'s voice" with an artist's name show a note under the box ("Removed …"), and the song is generated without them. **Song idea** only removes "in the style of …" (or "in the vein / spirit / manner of …"), "sounds like …" and "à la …", because a song idea is a subject and may name a person. The app asks the models for original songs; see [Known issues](#known-issues) for what it can't prevent.
- **If something fails,** the status line says what went wrong in plain words, your choices stay filled in, and **Retry** appears when trying again can help (a slow or unreachable class server). If your settings are wrong, it says to fix them and restart.
- **Every song, samples included, is also listed in the Library tab.** Pick one to see its cover and details, then use the same **Play now** and **Add to queue** buttons. Generated songs stay there until you stop the app.
- **To make a song like one you have,** pick it in the Library and click **More like this**. It opens the **Generate** tab with the form filled in from that song (style, extra style tags, mood, length, vocal or instrumental, and song idea), and the status line names the song. Change anything you like, then click **Generate**. If the song's style or mood isn't in the lists, that choice stays as it was, and the status line says so. While a song is being made, it only shows a short notice and changes nothing.

**Tested on `rc1`** (Windows 11, 2026-10-27; full rows in [`docs/TEST_EVIDENCE.md`](docs/TEST_EVIDENCE.md)):

| Test | What we did | Result |
|---|---|---|
| TC-01 instrumental | lo-fi hip hop, mellow, 45 s | **Pass.** Added in 7 s, 0:45 long, no vocals |
| TC-02 vocal | pop, upbeat, 60 s, idea "road trip" | **Pass.** Added in 6 s, 10 lines of lyrics shown, all 10 sung |
| TC-03 songs kept across tabs | Both songs, then Library → Generate → Library, then play the older one | **Partial.** Both stayed in the Library and played. But after the queue had finished, **Play now** didn't play the song until the page was reloaded (bug #72) |
| TC-F1 bad credentials | A wrong API key for one run | **Pass.** "The Qwen service rejected our credentials…", choices kept, no Retry; works again after restarting with the right key |
| TC-F2 a class server not answering | ACE-Step pointed at a port nothing listens on | **Pass.** "The ACE-Step service is unreachable right now…", **Retry** shown, choices kept |

### Cover art
- **Every song gets its own cover.** After a song is saved, Qwen writes an image prompt from the song's
  title, style, mood, theme and lyrics, and FLUX paints a square cover from it. The song is playable right
  away; the cover follows a few seconds later.
- **While it paints,** the result card shows the placeholder (a hand-drawn picture, not AI-generated) and
  **Painting cover…**, and swaps in the cover by itself when it's ready, without reloading the page.
- **If the cover fails** (for example a class server is busy), the card says what happened and adds
  "Your song is safe; it plays with a placeholder cover.", plus a **Retry cover** button. Retry paints a new
  cover for the same song. If no cover has started 60 seconds after the song, the card treats it as failed
  and offers Retry cover too.
- **In the player and the Library,** the cover shows next to **Now playing**, in **Up next**, and when you
  pick a song in the Library. The player reads the cover when a song starts, so a song you send to the
  player with **Play now** before its cover is ready keeps the placeholder there while it plays.
- **Covers stay with their song.** Each cover is stored and looked up by the song's id, never by its
  position in a list, so generating more songs or adding songs to the queue can't swap them.
- **What a cover is asked not to show:** every image prompt ends with "no text, no letters, no logos, no
  real people", and Qwen is told to show figures, if any, only from behind or far away. Nothing checks the
  finished image, so FLUX can still add small unreadable marks, for example on a book's pages; the sample
  covers were checked by eye (see [Sample songs](#sample-songs)).

Screenshots from `rc1` (Windows 11):

![A finished song's result card with its cover](docs/screenshots/cover-instrumental-result.png)

*A finished song's result card with its own cover.*

![The Library with a vocal song picked, showing its cover and details](docs/screenshots/library-song-cover.png)

*A song's cover in the Library when you pick it.*

![A failed cover: the placeholder, the note that the FLUX service is unreachable, and Retry cover](docs/screenshots/error-cover-failed-retry.png)

*A failed cover (here FLUX was unreachable): the song keeps the placeholder, with the note and **Retry cover**.*

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

**AI DJ (D)**
- **An intro can name the wrong song before it.** Each intro is written while the song before it plays, and the script may add a short transition from that song. If you press **Play now** on a different song first, the intro that comes next can still refer to the song that was playing when it was written.
- **A new DJ voice starts with the next intro.** A new voice applies only to intros made after the change. The intro already made for the next song was in the old voice and is dropped, so that song plays without an intro, and your voice speaks from the song after it.
- **A song can start before its intro is ready.** Intros are made in the background, and one takes about 4 to 5 seconds when the class servers are idle (measured: 3.75 to 4.94 s). If you press **Play queue** right after the page opens, or skip quickly, the song plays without an intro. If that intro then fails, nothing tells you.

**Player (E)**
- **Play now may do nothing once the queue has finished.** Seen on Windows 11 on `rc1` and on `main` (`3fb136a`): after the player says "Queue finished", pressing **Play now** on a song briefly shows "Now playing … 0:00 / 0:00" and then goes back to "Queue finished", with no sound. On `rc1`, **Add to queue** then **Play queue** also started a song at its end (0:45 of 0:45), so it ended at once. **Workaround:** reload the page. Your songs stay in the Library, and **Play now** then plays from 0:00. A reload also clears the Play queue case. We could not reproduce this on macOS on current `main` with the DJ on (10/28). (#72)

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

**Why.** Our first plan scaled lyrics with length, "roughly 2 sections per 30 s" (PROJECT.md §8.1), so a 45–60 s song got 18 lines. ACE-Step doesn't speed up to fit more words: it sings about one verse and one chorus, then **skips whole sections from the middle**, so the song loses its story. In the B6 listening tests, one check during the C3 review, the shipped samples (C6) and the release-candidate test (TC-02 on `rc1`), each song was generated on the class servers and a teammate counted the lines actually sung against the lyrics sent:

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
| Miles of Sun (TC-02 on `rc1`) | 60 s | **10** | **10** | all sung |

With 18 lines, three of the four songs lost about 8 lines or more, and the fourth lost 4 lines from the middle. With 10 lines, no song lost more than 2 lines or a whole section from the middle: two were sung in full, one dropped its 2-line outro, one dropped a few words and slurred its outro, and one skipped a single chorus line (@gunnaroc counted the two C6 rows against the lyrics while reviewing #51, and the TC-02 row during the `rc1` test). So the fix greatly reduces what's lost, but doesn't make ACE-Step sing every word. Two songs weren't counted line by line: an earlier 60 s song with 18 lines (B5, *Static on the Road*) sounded clean to the listener, and a 10-line punk song (B6, *Debt Degree*) ran cleanly. Too few lines may have its own problem: in B2, a 60 s song with only a verse and a chorus stopped abruptly at about 58 s. The spike's likely cause was too few lyrics for the length (not tested on its own), so the 40–74 s plan adds a short outro. Because of the sample_02 spec result, we asked lane C to generate the shipped samples only after this fix; their generation log (`samples/GENERATION_LOG.md`) shows both vocal samples were sent the 10-line plan.

**Trade-off.** Songs under 75 s have one verse and one chorus, not two. Songs of 75 s and up still get 18 lines, and the 120 s maximum hasn't been listened to line by line yet.

## Safeguards
_TODO (A)._

## Team & contributions
_TODO (A): member → role → PRs authored / reviewed._
