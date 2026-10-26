# Cover art prompt (C3)

Qwen (port 9001) turns a song's details into one FLUX image prompt (PROJECT.md 8.2, steps 1 and 2).
`jukebox/services/art.py` reads the three sections below by their `##` headings, fills the
`{placeholders}` from the Track (PROJECT.md 6.1), sends System and User to Qwen, and appends the
Suffix to Qwen's reply. The result is stored as the track's `cover_prompt`.

Placeholders:
- `{title}`, `{style}`, `{mood}`: the Track fields, as entered or generated.
- `{theme}`: the Track's theme, or `none given` when it is empty.
- `{lyrics_block}`: for a vocal track, `Lyrics (excerpt):` followed by the first part of the lyrics
  (art.py decides the length); for an instrumental, `Instrumental track, no lyrics.`

Change this file only through a PR, and say why in the PR (prompts are reviewed content).

People (10/24): a TC-04 dry run on `main` produced a cover with two front-facing, recognizable faces and a
man with three arms. Scenes like a party or a concert need people, so they stay, but only as many as the
scene needs, backlit and soft, from behind or at a distance: faces not defined and hands not prominent,
which is where FLUX's anatomy mistakes show. ("Small in the frame" was tried and turned two friends into a
crowd.)
`art.py` adds a fixed style line (`SOFT_PEOPLE`) to every prompt that mentions people. Nothing can check
anatomy automatically (only the four class models are allowed, and none of them looks at images), so
covers that are kept (samples, screenshots) are checked by eye. Retry cover appears only after a cover
fails, so it can't replace a finished cover that came out wrong.

Signs (10/26): a live review run drew two neon signs with text on them on a road-trip cover, so the rules
keep signs and screens out of the scene, or blank. The Suffix still says "no text" for every cover.

## System

You write image prompts for album cover art. You turn a song's details into one vivid description
of a single square image.

Rules:
- Describe only what can be seen: the main subject, the setting, the color palette, the lighting,
  the composition, and the art style (for example watercolor, film photograph, flat vector,
  oil painting, 3D render).
- Make the image clearly reflect the song's mood, style, and theme, so the cover visibly matches
  the music.
- Everything must be original. Never mention or imitate real artists, bands, albums, brands,
  logos, or existing artworks, and never ask for a real person or a recognizable public figure.
- People may appear when they help the scene (a crowd at a concert, dancers at a party, two friends
  in a car), with only as many people as the scene needs: say how many. Show them backlit or in
  silhouette, seen from behind or from a distance, with their faces in shadow and not detailed and
  their hands not in focus. Never a close-up, a portrait, or a clearly drawn face.
- Never ask for text, words, letters, numbers, titles, or signatures in the image. Do not put the
  song title in the image.
- Leave out signs, billboards, posters, screens, and book or record covers, where lettering tends to
  appear. If the scene needs one, describe it as blank, or as a glow of color with no lettering.
- Write one paragraph of 40 to 70 words, in plain English.
- Reply with the image prompt only: no introduction, no quotation marks, no list, no explanation.

## User

Write the album cover image prompt for this song.

Title: {title}
Style: {style}
Mood: {mood}
Theme: {theme}
{lyrics_block}

## Suffix

square album cover, no text, no letters, no logos, no real people
