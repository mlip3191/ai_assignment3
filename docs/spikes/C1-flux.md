# C1 spike: FLUX on port 9006

Task C1 (lane #4). Run by @felcervino with Claude Code on Windows 11, 2026-10-15, against the class server. Two image generations in total; the class server's load varies, so treat the numbers as a snapshot, not a guarantee.

## How the service is called

| | |
|---|---|
| Method + path | `POST {FLUX_BASE_URL}/v1/images/generations` (OpenAI-style images API; the server's spec is at `/openapi.json` and needs no key) |
| Auth | `Authorization: Bearer <CLASS_API_KEY>`. Without it: HTTP 401 `{"error":"Unauthorized"}` |
| Model name | `black-forest-labs/FLUX.2-klein-4B`, as given in class-endpoints.txt and as the server reports in `/v1/models` |
| Call style | Synchronous; one request, one reply. No job ID or polling |
| Request fields we use | `prompt`, `model`, `n` (1), `size` (`"1024x1024"`), `seed`, `response_format` (`b64_json`), `output_format` (`png`), `output_compression` |
| Reply image | `data[0].b64_json`: a base64-encoded PNG |

Other documented request fields (not used yet): `negative_prompt`, `num_inference_steps` (1 to 200), `guidance_scale` (0 to 20). `n` accepts 1 to 10. `size` is `WIDTHxHEIGHT`; the model default applies if it is left out. `response_format` also lists `url`, which the spec marks "not implemented", and `file`.

## Findings

### 1. Output is a PNG, so no conversion is needed

- `output_format` defaults to `png`, and the reply carries it as base64 in `data[0].b64_json`. Decoding gives a valid 1024 x 1024 PNG.
- `data[0].url` and `data[0].revised_prompt` came back empty: the server does not rewrite the prompt.
- The reply also has `created`, `output_format`, `size`, `cot_output` and `metrics` (server timings).
- For C2, `generate_image()` can return the decoded bytes directly. No image library (such as Pillow) is needed.

### 2. A fixed seed reproduces the same image

- The two calls used the same prompt and `seed: 42`. After decoding, their pixels were **identical**, byte for byte.
- This helps C5 (sample songs with fixed seeds) and makes covers repeatable for tests and evidence.

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

## Not checked

- Sizes other than 1024 x 1024.
- `negative_prompt`, `num_inference_steps`, `guidance_scale`.
- Behavior under heavy load (for example everyone testing at once near the deadline).
- Error responses for bad input or an overloaded server (4xx/5xx). Only the missing-key response (HTTP 401) was seen, so C2's error mapping is not yet verified against real errors.
- The suffix on more than one image, and on song-specific prompts (C3).

## How it was run

A throwaway script read the key from the local `.env` inside its own process (never printed) and checked that `FLUX_BASE_URL` uses port 9006. It made two `GET /v1/models` calls and two image generations: one with default settings and one with `output_compression: 1`, both with `seed: 42`. A second throwaway script decoded both PNGs with the Python standard library and compared their pixels. Neither script is committed, and the test images stay in the gitignored `runtime/tmp/`.
