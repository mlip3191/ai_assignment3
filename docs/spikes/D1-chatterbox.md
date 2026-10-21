# D1 spike: Chatterbox on port 9008

Task D1 (lane #5). Run by @dilloncsmart on Windows 11, 2026-10-16, against the class server. All numbers below are from that one session; the class server's load varies, so treat them as a snapshot, not a guarantee.

## How the service is called

| | |
|---|---|
| Method + path | `POST {CHATTERBOX_BASE_URL}/v1/audio/speech` (JSON, OpenAI-style speech endpoint). Also `POST /v1/audio/speech/upload` (multipart) for a reference file. Spec at `/openapi.json`, docs at `/docs` |
| Auth | `Authorization: Bearer <CLASS_API_KEY>`. Without it: HTTP 401 `{"error":{"message":"Missing or invalid API key.","type":"authentication_error","code":"invalid_api_key",...}}`. `/health` and `/openapi.json` answered without a key; the spec says the docs pages are public too |
| Model name | `chatterbox-v3` (the request's `model` field; this is also what `/v1/models` and `/info` report) |
| Call style | Synchronous; one request, one complete audio file back. No job ID, polling, or streaming (`/info` says `"streaming": false`) |
| Request fields we use | `model`, `input` (the text), `voice` (`"default"`), `language_id` (`"en"`), `response_format`, and `ref_audio` (base64) for a custom voice |
| Response | The audio bytes, with `Content-Type: audio/mpeg` for MP3 or `audio/wav` for WAV. Every response, including errors, has an `x-request-id` header |

## Findings

### 1. It is Chatterbox Multilingual V3, using its own default voice

- The spec's title is "Chatterbox Multilingual V3 API". `/v1/models` lists one model, `chatterbox-v3`, owned by `ResembleAI`. `/info` reports the checkpoint `t3_mtl23ls_v3.safetensors` (the multilingual V3 weights), 23 languages, running on a GPU.
- `/v1/voices` lists exactly one voice: `default`, "Bundled voice". That is the service's own voice, so F3a needs no upload and no other TTS.

### 2. Default voice works (F3a)

- The ~40-word DJ intro (230 characters) worked on all 4 calls, 3 as MP3 and 1 as WAV.
- **Output:** MP3 by default (about 175–190 KB for this intro). WAV output is 24 kHz, mono, 16-bit, and this intro came out as **11.5 s of speech**. Plan on roughly 3.5 words per second.

### 3. A custom voice works with WAV and MP3 references (F3b)

There are two ways to send a reference recording, and both worked with both formats:

| Way | WAV reference | MP3 reference |
|---|---|---|
| JSON: `voice: "default"` + `ref_audio: "<base64>"` on `/v1/audio/speech` | 200, 6.84 s | 200, 4.77 s |
| Multipart: `file` + `request` (the JSON as a string) on `/v1/audio/speech/upload` | 200, 6.31 s | 200, 4.79 s |

- References used: a team member's own recording, about 11.6 s long (the WAV was 44.1 kHz stereo, 2.0 MB; the MP3 was 0.2 MB). Neither is committed; both stay in `runtime/uploads/`.
- `ref_audio` also accepts a data URI (`data:audio/wav;base64,...`).
- **Listening check (human, @dilloncsmart):** the default voice is clear and usable, but flatter than a real radio DJ. The custom-voice clips did **not** sound much like the speaker and came out muffled. The reference was recorded on a laptop microphone, and voice cloning copies the recording's quality, so a cleaner reference should help. Follow-ups: D3 tunes delivery (`exaggeration`, `cfg_weight`); D4 re-tests with a clean phone recording and adds recording tips to the upload help text.

### 4. Limits (from `/info`, plus what we observed)

| Limit | Value |
|---|---|
| Text (`input`) | 1–4,096 characters. Empty or longer text gets HTTP 400 |
| Reference file size | 20 MB (`reference_bytes`); whole request body 32 MB |
| Reference length | At most 60 s (`reference_seconds`). A 60 s test tone was accepted; a 0.5 s one was rejected. The exact minimum was not found |
| Reference formats | WAV and MP3 decoded fine. A fake `.ogg`, a corrupt WAV, and an empty file were all rejected (below) |
| Output formats | `mp3` (default), `wav`, `opus`, `aac`, `flac`, `pcm` |
| Server-side timeout | 300 s per request |
| Queue | Capacity 8, shared by the whole class (`/ready` shows `capacity`, `in_flight`, `active`). Whether that is 8 waiting or 8 running at once wasn't tested |

### 5. Latency

| Request | Runs | Seconds |
|---|---|---|
| ~40 words, default voice, MP3 | 3 | 3.37–3.97 (median **3.8**) |
| ~40 words, default voice, WAV | 1 | 8.10 (one run only; probably load, not the format) |
| ~40 words, custom voice (WAV or MP3 reference) | 4 | 4.77–6.84 |
| Health, ready, info, models, voices, and every error | 13 | under 0.2 |

So one DJ clip takes about 4–7 s to make and lasts about 11 s. With prefetch (D5), the next clip is ready long before the current song ends.

### 6. Error shapes

Every error is JSON in the same shape: `{"error": {"message", "type", "param", "code"}}`.

| Case | HTTP | `code` | `message` |
|---|---|---|---|
| No API key | 401 | `invalid_api_key` | Missing or invalid API key. |
| Empty `input` | 400 | `invalid_value` | String should have at least 1 character |
| `input` over 4,096 characters | 400 | `invalid_value` | String should have at most 4096 characters |
| Unknown `voice` ID | 404 | `voice_not_found` | Voice was not found. |
| Fake `.ogg`, corrupt WAV, or 0.5 s reference | 400 | `invalid_reference` | Reference audio could not be decoded or violates the configured duration/audio limits. |
| Empty reference file | 400 | `invalid_reference` | Reference file is empty. |

The spec also lists 413, 429, 500, 503 and 504; none of those were seen.

## Recommendations for D2 (client) and D4 (voice upload)

1. **One endpoint for both voices:** `POST /v1/audio/speech` with JSON. Send `voice: "default"`, and add `ref_audio` (base64) only when a custom voice is set. That gives one code path and simple `respx` tests. Base64 adds a third to the size, which is well under the 32 MB body limit with D4's 10 MB cap.
2. **Never call `POST /v1/voices`.** It saves the voice on the shared class server, where anyone listing voices can see it. Send the reference with each request instead. The server also keeps a small in-memory cache of recent references (`voice_cache_size: 4`).
3. Always send `model: "chatterbox-v3"`, `language_id: "en"` and `response_format: "mp3"` explicitly, rather than relying on defaults.
4. **D4 limits:** keep §8.3's 10 MB and a 5–30 s window. Both are inside the server's limits (20 MB, at most 60 s, and more than 0.5 s). Still validate on our side first, so users get our plain-language message instead of the server's generic one.
5. **Error mapping:** 400 `invalid_reference` → `bad_request`, with a friendly reason ("The voice clip couldn't be used. Try a clear 5–30 s MP3 or WAV."). 404 means our voice setting is wrong (`bad_request`). The A3 base client (PR #9, not merged yet) already pulls `error.message` out of this body shape.
6. **Timeout:** clips took under 10 s, so `CHATTERBOX_TIMEOUT_S=120` is generous; 60 s would still leave a wide margin. Not changed here; it's a team setting. Because speech is expensive and the queue is shared, a read timeout should not be retried automatically (see the review of #9).

## Not checked

- Behavior when the shared queue is full (429/503), or under heavy class load.
- The exact minimum reference length (somewhere between 0.5 s and 11.6 s).
- Non-English `language_id` values.
- `seed` repeatability, `speed`, `exaggeration` and the other tuning fields. These were all left at their defaults. Chatterbox's own guidance for more expressive speech is a higher `exaggeration` (~0.7) with a lower `cfg_weight` (~0.3); D3 will try that.
  - **Follow-up (D3, 2026-10-19):** per `/openapi.json`, `exaggeration` defaults to 0.5 with a minimum of 0 and no maximum, and `cfg_weight` defaults to 0.5 in the range 0–1. The client caps `exaggeration` at 2 as our own limit. The same intro was spoken live at 0.5/0.5, 0.7/0.3 and 1.0/0.3; all three succeeded, and by ear 1.0/0.3 sounded most like a radio DJ, so the DJ uses that.
- How much a cleaner reference recording improves the likeness.
- Long inputs near 4,096 characters, and the `chunk_size` option.

## How it was run

First, `/openapi.json` was fetched without a key. It gave the spec's title, the request schemas and the listed error codes. Then a throwaway script (not committed) ran on the team member's machine. It read the key from the local `.env` and never printed it, and it read the reference recordings from `runtime/uploads/`. It made 23 requests: health, ready, info, models and the voice list; 4 default-voice calls; 5 custom-voice calls (WAV and MP3, each as JSON and as an upload, plus one data URI); and 9 limit and error cases. It saved the results and clips to `runtime/tmp/` (gitignored). It never called `POST /v1/voices`, so no voice was saved on the server.
