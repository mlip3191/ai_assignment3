# B2 spike: ACE-Step on port 9007

Task B2 (lane #3). Run by @gunnaroc on Windows 11, 2026-10-15, against the class server, with only our own jobs in the queue (every job was at queue position 1). The numbers are a snapshot of a quiet server, not a guarantee for deadline week.

The request format comes from ACE-Step 1.5's official API docs (`docs/en/API.md` in the ace-step/ACE-Step-1.5 GitHub repo). The class server's `/openapi.json` lists the paths but doesn't describe request bodies, and class-endpoints.txt has no entry for port 9007. Every field below was then confirmed against the class server.

## How the service is called

It's an **asynchronous job API** in three steps:

| Step | Request | Response |
|---|---|---|
| 1. Submit | `POST {ACESTEP_BASE_URL}/release_task`, JSON body (fields below) | `{"data": {"task_id": "...", "status": "queued", "queue_position": 1}, "code": 200, "error": null, ...}` |
| 2. Poll | `POST /query_result`, body `{"task_id_list": ["<task_id>"]}` | `{"data": [{"task_id", "status", "result", "progress_text"}]}`. `status` is an **integer**: `0` queued/running, `1` succeeded, `2` failed. `result` is a **JSON string** that must be parsed again into a list of results |
| 3. Download | `GET /v1/audio?path=...`, using the `file` value from the result as-is | MP3 bytes, `content-type: audio/mpeg` |

- **Auth:** `Authorization: Bearer <CLASS_API_KEY>`, the same as Qwen. Sent on all three steps.
- **Model:** `/v1/models` reports `acestep/acestep-v15-xl-turbo`. Every result also reports `dit_model: "acestep-v15-xl-turbo"` and `lm_model: "acestep-5Hz-lm-4B"` (ACE-Step's own internal planner; it is part of the same service).

### Submit fields we used

| Field | Value we sent | Notes |
|---|---|---|
| `prompt` | style tags, e.g. `"upbeat pop, summery, bright synths, catchy, female vocals"` | Alias `caption` |
| `lyrics` | lyrics with `[verse]` / `[chorus]` tags, or `""` / `"[Instrumental]"` | |
| `audio_duration` | 5, 30, 60 | Docs say 10–600 s |
| `audio_format` | `"mp3"` | Default; `wav` and `flac` also documented |
| `inference_steps` | `8` | Recommended for Turbo (docs: 1–20) |
| `batch_size` | `1` | **Docs default is 2.** Always send 1, or the shared server makes two songs per request |
| `seed`, `use_random_seed` | `42`, `false` | Result echoes `seed_value: "42"` |
| `thinking` | `false` | Default |
| `vocal_language` | `"en"` | Default |

Not sent, so the server chose them: `bpm` (it picked 86–125) and `key_scale` (G major, F# minor, ...). These can be set if we want control.

## Results

| Job | Lyrics sent | Requested → reported duration | Server generation time | Total wait (submit → file saved) | File |
|---|---|---|---|---|---|
| Limit test | `""` | 5 → **5.0 s** | 2.16 s | 5.0 s | 83 KB |
| Instrumental | `""` | 30 → 30.0 s | 2.65 s | 5.2 s | 481 KB |
| Instrumental | `"[Instrumental]"` | 60 → 60.0 s | 2.51 s | 5.2 s | 961 KB |
| Vocal | road-trip lyrics | 30 → 30.0 s | 2.61 s | 4.8 s | 481 KB |
| Vocal | road-trip lyrics | 60 → 60.0 s | 3.05 s | 7.2 s | 961 KB |

- "Server generation time" is the server's own figure, from the result's `generation_info`. "Total wait" is what our script saw. Most of the gap is our 2 s polling interval plus the 0.4–0.9 s download.
- The output is MP3, 48 kHz, 128 kbps: about 16 KB per second, so about 0.5 MB per 30 s and 1 MB per 60 s.
- The vocal lyrics were the AI-written (Qwen, B1) road-trip lyrics "Windows Down, World Up", so no third-party lyrics were used.

## Listening check (@gunnaroc, by ear)

- **Instrumental:** both instrumental tracks had **no vocals**, with empty lyrics and with `[Instrumental]` alike.
- **Vocal:** both vocal tracks **sang the lyrics**. The 30 s and 60 s versions differed in style, but both sounded "summery and poppy" as asked.
- **Voice:** the singing sounds **unnaturally high-pitched**, like heavy autotune.
- **Length:** correct for both 30 s and 60 s. But the **60 s vocal track stops abruptly at about 58 s** instead of ending naturally.
- **Quality:** good enough overall. The instrumentals sound **rougher than expected for generic lo-fi or EDM, almost scratchy or robotic**.

## Findings

1. **Generation is fast:** 2–3 s of server time for 30–60 s of audio, when the queue is empty. The plan's `ACESTEP_TIMEOUT_S=300` and the "grader may think it froze" risk assume something much slower. The real risk is **queueing** when the whole class uses the server at once, which we didn't test.
2. **Instrumental needs no special flag.** Empty `lyrics` and `"[Instrumental]"` both produced instrumental audio (one sample each).
3. **The 10 s minimum in the docs is not enforced.** A 5 s request returned 5.0 s of audio. The upper limit (600 s per the docs) was **not tested** on purpose, to avoid tying up the shared GPU.
4. **The lyric format is `[verse]` / `[chorus]` section tags on their own lines**, which is what Qwen already produces (B1). The server echoes the lyrics back unchanged in the result.
5. **The server leaks internal paths.** `progress_text` and the `file` value contain the class machine's file paths (including a username). Never show these to users or put them in the UI or README.

## Recommendations for B4 (ACE-Step client) and B5/B6

1. **Use the submit → poll → download flow**, polling every **1 s**, with a total time limit for the whole job (e.g. 120 s, configurable) and short per-request timeouts. Status `2` or an unparseable `result` → `ServiceError(kind="bad_response")`. Running out of time → `kind="timeout"`.
2. **Never retry `POST /release_task` automatically.** A retried submit can create a duplicate job on the shared GPU. Retrying `/query_result` and the download is safe. This needs a way to turn retries off per request in the shared client (#9).
3. **Always send `batch_size: 1`.**
4. **Send `"[Instrumental]"` as the lyrics for instrumental tracks.** Both methods worked, but the explicit marker makes the intent visible in logs and results.
5. **Ideas for B5/B6, all untested:**
   - **High-pitched voice:** try voice tags in `prompt` such as `"warm female vocals"`, `"male vocals"` or `"natural voice"`.
   - **Abrupt ending:** try adding an `[outro]` section to the lyrics, or make the lyrics length fit the duration.
   - **Rough instrumentals:** try higher `inference_steps` (up to 20) or `thinking: true`.

   Each should be compared by ear before we commit to it.
6. **Duration slider (B7):** set the minimum at 10 s (the documented limit). For the maximum, around 120 s keeps sample files small; we haven't tested longer songs. The hint text can honestly say "usually takes a few seconds" until queueing is measured.

## Not checked

- Queueing and latency when several teammates or the whole class generate at once.
- Durations above 60 s, and the 600 s upper limit.
- Error responses: bad fields, missing auth, overload, and what a status `2` (failed) result looks like.
- Whether `seed` gives the same audio twice (it matters for reproducing the sample songs, C5).
- `wav` / `flac` output, `bpm` / `key_scale` control, `thinking: true`, and higher `inference_steps`.
- Listening was one person on one set of speakers or headphones, with one sample per setting.

## How it was run

A throwaway script read the key from the local `.env` (never printed), submitted 5 jobs one after another (a 5 s limit test, instrumental 30 s and 60 s, vocal 30 s and 60 s), polled every 2 s, and downloaded each MP3 to the gitignored `runtime/tmp/`. Neither the script nor the audio is committed.
