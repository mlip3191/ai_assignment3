# Screenshots (C7)

Taken by @felcervino with Claude Code on 2026-10-26, Windows 11, from the `rc1` tag (`a1a8846`), running
`python app.py` against the class services, in a headless Microsoft Edge at 1280 px wide, light theme.
Each was checked for credentials before it was committed: none shows `.env`, a key, a server address, a
terminal, or browser devtools (DL10).

| File | Shows | For |
|---|---|---|
| `main-screen.png` | The whole app: How to use, the Generate tab, and the player playing a generated song | README Overview |
| `generate-vocal-song.png` | The Generate tab after a vocal song (pop, upbeat, 60 s, idea "road trip"): status, title, cover, lyrics, Play now and Add to queue | Using the app: Generate a song |
| `cover-instrumental-result.png` | The result card of an instrumental song (lo-fi hip hop, mellow, 45 s) with its cover | Using the app: Cover art |
| `library-song-cover.png` | The Library with the vocal song picked: its cover and details | Using the app: Cover art, Library |
| `player-now-playing.png` | The player: Now playing with the song's cover, the audio player, and Up next with the next song's cover | Using the app: playback |
| `error-cover-failed-retry.png` | Error state: FLUX unreachable, so the song keeps the placeholder cover, with the note and Retry cover | Using the app: Cover art; error state |

Notes:
- The error state was made by starting the app with the environment variable
  `FLUX_BASE_URL=http://127.0.0.1:9006` (nothing listens there on our machines; the port must stay 9006 or
  the config check refuses it), so the cover call failed. No settings file was changed.
- `rc1` has no DJ voice yet ("DJ unavailable for this track"), so the DJ screenshots wait for the next
  release candidate.
