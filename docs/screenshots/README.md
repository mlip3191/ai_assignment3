# Screenshots (C7)

Taken by @felcervino with Claude Code on Windows 11, running `python app.py` against the class services, in a
headless Microsoft Edge at 1280 px wide, light theme. Most are from the `rc1` tag (`a1a8846`, 2026-10-26).
The DJ shots, `main-screen.png` and `player-now-playing-dj.png` were taken on 2026-10-29 from `main` at
`690b406`, the commit `rc2` will be tagged from, because `rc1` had no DJ.
Each was checked for credentials before it was committed: none shows `.env`, a key, a server address, a
terminal, or browser devtools (DL10).

| File | Shows | For |
|---|---|---|
| `main-screen.png` | The whole app: How to use, the Generate tab, and the player playing a sample song with two more under Up next | README Overview (not written yet, A9) |
| `generate-vocal-song.png` | The Generate tab after a vocal song (pop, upbeat, 60 s, idea "road trip"): status, title, cover, lyrics, Play now and Add to queue | Using the app: Generate a song |
| `cover-instrumental-result.png` | The result card of an instrumental song (lo-fi hip hop, mellow, 45 s) with its cover | Using the app: Cover art |
| `library-song-cover.png` | The Library with the vocal song picked: its cover and details | Using the app: Cover art, Library |
| `library-midnight-coffee-steam.png` | The Library with the second instrumental song ("Midnight Coffee Steam") picked: its own cover and details | TC-04 evidence |
| `player-now-playing.png` | On `rc1`: the player, Now playing with the song's cover, the audio player, and Up next with the next song's cover (it also shows rc1's "DJ unavailable for this track") | TC-04 evidence |
| `player-now-playing-dj.png` | The player: Now playing a vocal sample ("Windows Down") with its cover, the audio player, and Up next with the next song's cover; the DJ voice box below shows a custom voice | Using the app: Generate a song (playback) |
| `dj-default-voice.png` | The DJ speaking before the first sample, in the default voice: "DJ speaking…", Up next, and the DJ voice box saying "Default DJ voice" | Using the app: DJ (not written yet, D7) |
| `dj-custom-voice.png` | The DJ speaking in a custom voice uploaded through the DJ voice box: "Custom voice active" and **Reset to default** | Using the app: DJ (not written yet, D7) |
| `error-cover-failed-retry.png` | Error state: FLUX unreachable, so the song keeps the placeholder cover, with the note and Retry cover | Using the app: Cover art; error state |

Notes:
- The error state was made by starting the app with the environment variable
  `FLUX_BASE_URL=http://127.0.0.1:9006` (nothing listens there on our machines; the port must stay 9006 or
  the config check refuses it), so the cover call failed. No settings file was changed.
- The custom voice is @felcervino's own recording, uploaded through the app's **DJ voice** box. The app
  keeps it in `runtime/uploads/` (gitignored); the recording isn't committed, and its file name doesn't show.
- A screenshot can't show sound. @felcervino listened in the same app run on 2026-10-29: the DJ intros
  played in the default voice with the default set, and in the uploaded voice with the recording active.
