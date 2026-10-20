# Starter prompt (verbatim) + team additions

The first block is the assignment's starter prompt, copied word for word. Do not edit it.
The second block is our team's additions. Change it through a PR.

## Original starter prompt

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

## Team additions

```
# Team Additions
Everything needed to build the app is in this prompt and PROJECT.md, so
the build does not depend on any one coding agent. An agent that cannot
read the repository (for example Hermes) gets both files attached.

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
- The duration slider runs from 10 s (ACE-Step's documented minimum) to
  about 120 s (longer songs are untested and make large files), default
  about 60 s. See PROJECT.md §7.1 and docs/spikes/B2-acestep.md.
- Newly generated songs join the playable library and stay available for
  the whole session.
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

## Sample songs
- Ship three ready-to-play sample songs (1 instrumental, 2 vocal) in
  samples/, each with a title and cover, generated in advance through the
  app's own Qwen, FLUX, and ACE-Step clients. All sample lyrics are
  written by Qwen. samples/GENERATION_LOG.md records how each one was made.

## Documentation and submission
- README.md follows the PROJECT.md §11 outline: setup and use (how to
  supply credentials securely and configure endpoints, placeholders
  only), test results (inputs, expected, actual) for the three core
  features and at least one failure, unresolved problems, completed tests
  kept separate from unchecked claims, one design choice with evidence,
  one limitation investigated, how the samples were generated, and
  screenshots.
- The ZIP includes code, requirements, .env.example, docs, and the sample
  audio and image files. It never includes .env, user uploads, or voice
  recordings.

## Content safeguards
- Lyrics, DJ scripts, and cover prompts must be original. Never reproduce
  or imitate existing songs or lyrics, and never reference real artists.
- If Qwen emits reasoning or "thinking" text, disable it per the service
  docs and strip it before use.

## Service findings from the spikes
- Qwen: send chat_template_kwargs {"enable_thinking": false} (B1).
- ACE-Step: async job API (submit, poll, download); always send
  batch_size 1. Still send a fixed seed with use_random_seed false and
  record it in samples/GENERATION_LOG.md (PROJECT.md §8.5), but don't
  rely on it to reproduce the audio (not yet cleanly tested); commit the
  generated sample files instead (B2). Never auto-retry the
  /release_task submit (send it with retry=False): a retried submit can
  start a second job on the shared GPU. Polling and the download may
  retry.
- FLUX: POST /v1/images/generations returns the image as base64 in
  data[0].b64_json; the prompt is not rewritten, and a fixed seed
  reproduces the same cover, so sample covers are repeatable (C1).
- Chatterbox: POST /v1/audio/speech with model, language_id, and
  response_format sent explicitly; a custom voice sends the recording as
  base64 ref_audio on each request. Never POST /v1/voices (it saves the
  voice on the shared class server). No auto-retry on speech timeouts
  (D1).
- Request details live in PROJECT.md §7.1.

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
- The coding agent never reads, prints, or asks for .env contents or
  credential values. The app loads them at runtime only through
  jukebox/config.py, and never logs them.
```
