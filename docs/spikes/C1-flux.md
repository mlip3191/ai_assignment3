# C1 spike: FLUX on port 9006

Task C1 (lane #4). Run by @felcervino with Claude Code on Windows 11, 2026-10-15, against the class server. Two image generations in total; the class server's load varies, so treat the numbers as a snapshot, not a guarantee.

## How the service is called

| | |
|---|---|
| Method + path | `POST {FLUX_BASE_URL}/v1/images/generations` (OpenAI-style images API; the server's spec is at `/openapi.json`, which needed no key on 10/15; an observation, not a documented guarantee) |
| Auth | `Authorization: Bearer <CLASS_API_KEY>`. Without it, `GET /v1/models` returned HTTP 401 `{"error":"Unauthorized"}` |
| Model name | `black-forest-labs/FLUX.2-klein-4B`, as given in class-endpoints.txt and as the server reports in `/v1/models` |
| Call style | Synchronous; one request, one reply. No job ID or polling |
| Request fields we use | `prompt`, `model`, `n` (1), `size` (`"1024x1024"`), `seed`, `response_format` (`b64_json`), `output_format` (`png`), `output_compression` |
| Reply image | `data[0].b64_json`: a base64-encoded PNG |

Other documented request fields (not used yet): `negative_prompt`, `num_inference_steps` (1 to 200), `guidance_scale` (0 to 20). `n` accepts 1 to 10. `size` is `WIDTHxHEIGHT`; the model default applies if it is left out. `response_format` also lists `url` and `file`; the spec marks the response's `url` field "not implemented".

## Findings

### 1. Output is a PNG, so no conversion is needed

- `output_format` defaults to `png`, and the reply carries it as base64 in `data[0].b64_json`. Decoding gives a valid 1024 x 1024 PNG.
- `data[0].url` and `data[0].revised_prompt` came back empty: the server does not rewrite the prompt.
- The reply also has `created`, `output_format`, `size`, `cot_output` and `metrics` (server timings).
- For C2, `generate_image()` can return the decoded bytes directly. No image library (such as Pillow) is needed.

### 2. A fixed seed reproduces the same image

- The two calls used the same prompt and `seed: 42`. The PNG files differ in size (finding 3), but the **decoded pixel data was identical**.
- This makes sample **covers** repeatable for C5, tests, and evidence. Song **audio** can't rely on seeds: a fixed ACE-Step `seed` did not reproduce the audio (see #12).

### 3. Use `output_compression: 1` to halve the file size

| Call | `output_compression` | End to end | Server generation | PNG size |
|---|---|---|---|---|
| 1 | default (100: fastest, least compressed) | 2.30 s | 0.95 s | 3.1 MB |
| 2 | 1 (strongest PNG compression) | 2.92 s | 0.96 s | **1.4 MB** |

- The image is the same (finding 2), so the compression is lossless.
- At 3.1 MB per cover, the 3 sample covers alone would add about 9 MB to the submission ZIP. With `output_compression: 1` they add about 4 MB, for about 0.6 s extra per cover.

### 4. The "no text, no logos, no people" suffix held

- The test prompt was a neutral scene ending in "square album cover, no text, no letters, no logos, no real people".
- @felcervino looked at the image: a misty lake with mountains and trees, with no text, letters, logos, or people.
- This is one image only; C3 and C4 should keep checking real covers by eye.

## Recommendations for C2 (the FLUX client)

1. Send `model`, `n: 1`, `size` from `width` and `height` (`f"{width}x{height}"`), `seed` when given, `response_format: "b64_json"`, `output_format: "png"`, and `output_compression: 1`.
2. Read `data[0].b64_json` and base64-decode it. Treat a missing or empty `data`, a missing `b64_json`, or bytes that do not start with the PNG signature as a `bad_response` error.
3. Timeout: about 2 to 3 s per image with an empty queue, so `FLUX_TIMEOUT_S=120` leaves plenty of room for queueing. Not changed here; it's a team setting.
4. Retries: with the shared client's default retry (#9), a POST that times out after the server has started work generates a second image. That costs about 3 s of the shared GPU, so keeping the default retry for FLUX is reasonable, unlike ACE-Step's job submit.
5. Decide the format in C2 with one comparison call: `output_format` `jpeg` or `webp` (where `output_compression` is the encoder quality) and a smaller `size` such as 512x512 could cut the file size well below 1.4 MB. Untested. The PNG-signature check in item 2 must follow whichever format is chosen.

## Not checked

- Sizes other than 1024 x 1024, and JPEG or WebP output.
- `negative_prompt`, `num_inference_steps`, `guidance_scale`.
- Behavior under heavy load (for example everyone testing at once near the deadline).
- Error responses for bad input or an overloaded server (4xx/5xx). Only the missing-key response (HTTP 401) was seen, so C2's error mapping is not yet verified against real errors; C2's first error-path test should be built from a real error response.
- The suffix on more than one image, and on song-specific prompts (C3).

## How it was run

Without a key, `curl` fetched `/openapi.json` (HTTP 200, the full spec) and called `GET /v1/models` (HTTP 401). Then a throwaway script read the key from the local `.env` inside its own process (never printed) and checked that `FLUX_BASE_URL` uses port 9006. It made two `GET /v1/models` calls and two image generations with the same prompt, `seed: 42`, and `model: "black-forest-labs/FLUX.2-klein-4B"` spelled exactly as `/v1/models` reports it (both returned HTTP 200): one with default settings and one with `output_compression: 1`. The queue was empty for both: the server's own `metrics.stage_durations.queue_wait_ms` was about 0.1 ms each time. These are single samples, one call per setting. A second throwaway script decoded both PNGs with the Python standard library (zlib plus PNG unfiltering) and compared the raw pixel data. Neither script is committed, and the test images stay in the gitignored `runtime/tmp/`.
