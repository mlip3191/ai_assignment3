# B1 spike: Qwen on port 9001

Task B1 (lane #3). Run by @gunnaroc on Windows 11, 2026-10-15, against the class server. All numbers below are from that one session; the class server's load varies, so treat them as a snapshot, not a guarantee.

## How the service is called

| | |
|---|---|
| Method + path | `POST {QWEN_BASE_URL}/v1/chat/completions` (OpenAI-compatible; the server's spec is at `/openapi.json`) |
| Auth | `Authorization: Bearer <CLASS_API_KEY>`. Without it: HTTP 401 `{"error":"Unauthorized"}` |
| Model name | `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit`, as given in class-endpoints.txt and as the server reports in `/v1/models` and in every response's `model` field |
| Call style | Synchronous; one request, one reply. No job ID or polling |
| Request fields we use | `model`, `messages`, `max_tokens`, `temperature`, `chat_template_kwargs`, `response_format` |
| Reply text | `choices[0].message.content` |

## Findings

### 1. Thinking is ON by default. Turn it off on every call.

- With default settings, a two-line poem took **6.98 s and 1,300 completion tokens**, almost all of them reasoning.
- The reasoning comes back in a separate `message.reasoning` field, **not** as `<think>` tags inside `content`. In all 20+ calls, `content` never contained `<think>`.
- Sending `"chat_template_kwargs": {"enable_thinking": false}` turns it off: the same poem took **0.22 s and 15 tokens**, and `reasoning` was empty.
- **Main risk:** with thinking on, 2 of 3 longer requests used up the whole `max_tokens` budget (2,500) on reasoning and returned **`content: null`** with `finish_reason: "length"`. In the app that would look like an empty or failed reply.

### 2. JSON output for `{title, lyrics}` is reliable (with thinking off)

| Method | Parsed directly with `json.loads` | Needed cleanup | Failed |
|---|---|---|---|
| Prompt asks for JSON only | 5/5 | 0 | 0 |
| `response_format` with a JSON schema | 5/5 | 0 | 0 |

- Both methods gave clean JSON, with no code fences and no extra text.
- Every set of lyrics used `[verse]` / `[chorus]` tags as asked. Titles varied run to run ("Sunset Gearshift", "Windows Down, World Up", ...).
- Lyrics often contain curly apostrophes (`’`), so files and logs must be handled as UTF-8.
- **The lyrics came out shorter than asked:** the prompt asked for about 2 verses and a chorus for 60 s, but 9 of 10 runs returned one verse and one chorus (285–515 characters). This needs tuning in B5.

### 3. Latency

| Request | Runs | Seconds (median) | Completion tokens | Speed |
|---|---|---|---|---|
| ~200-token paragraph, thinking off | 5 | 1.43–1.78 (**1.5**) | 215–253 | ~150 tok/s |
| Title + lyrics JSON, thinking off | 10 | 0.78–1.16 (~1.0) | | |
| Same paragraph, thinking on | 3 | 9.44–10.87 (10.5) | 2,192–2,500 | ~230 tok/s |

## Recommendations for B3 (the Qwen client)

1. Always send `chat_template_kwargs: {"enable_thinking": false}`.
2. Read only `message.content` and ignore `message.reasoning`. Still strip any `<think>…</think>` text defensively, as the plan asks, even though we never saw it.
3. Treat `content` being `null` or empty, or `finish_reason == "length"`, as a `bad_response` error rather than returning an empty string.
4. Use `response_format` with a JSON schema for title and lyrics. It was as reliable as the prompt-only method, and it is the server's documented way to guarantee the shape. Keep the plain-text fallback parser anyway.
5. Timeout: replies took about 1–2 s with thinking off, so `QWEN_TIMEOUT_S=90` is very generous. 30 s would still leave a wide margin. Not changed here; it's a team setting.

## Not checked

- Behavior under heavy load (for example everyone testing at once near the deadline).
- Very long prompts or replies, and the context-window limit.
- Whether `seed` gives repeatable output (it matters for the sample songs, C5).
- Lyric quality beyond a quick read of a few samples.

## How it was run

A throwaway script read the key from the local `.env` (never printed) and made 22 calls: one default call, one thinking-off call, 5 prompt-only JSON calls, 5 schema JSON calls, 5 thinking-off latency calls and 3 thinking-on latency calls. The script itself is not committed.
