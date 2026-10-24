# Test cases

Every automated test case for the AI Jukebox lives here. The rules are the same for everyone:

1. **Every change needs test cases.** If you change code in `jukebox/`, `scripts/`, `.claude/hooks/`, `.githooks/`, or `app.py`, add or update a test here in the same branch. Only docs-only changes are exempt. The pre-push gate blocks a push that changes code without touching `tests/`.
2. **Build the tests first.** Write the test, watch it fail, then write the code until it passes (`/start-session` plans it this way).
3. **Every push runs every test.** The pre-push gate (`scripts/prepush.py`) runs the full suite, so new work is always checked against all existing test cases. CI runs it again on every PR. The gate runs it the way CI does (plain `pytest -q`, with the repo root **not** on `sys.path`), so a test file that imports `jukebox` must set up `sys.path` itself, as the existing test files do. `python -m pytest` would hide a missing setup that CI then catches.
4. **Never call the real class services in tests.** Mock them with `respx`. No credentials in tests.

## Layout

One file per module, named `test_<module>.py`:

| File | Covers |
|---|---|
| `test_guardrails.py` | Claude Code guard hook, session check, hook launcher |
| `test_prepush.py` | Pre-push gate (including that it runs the tests the way CI does) and the secret scan's `.env` handling |
| `test_check_models.py` | Only-the-four-class-models check |
| `test_lanes.py` | Lane issue generation |
| `test_playback_spike.py` | E1 Option A queue: clip order, skip, stale end event, one autoplay Audio |
| `test_library_tab.py` | A7 Library tab: list, preview by track id, escaped fields, pick and timer tick, no model client |
| `test_markdown.py` | A7 shared escape: generated text stays plain text (characters, line breaks, list markers) |
| `test_integration.py` | A7 integration with mocked services: generate, library, queue, cover later, DJ clip, failures |
| `test_app_shell.py` | E2 shell: placeholder panels, loopback launch, no model clients |
| `test_player_panel.py` | E4 player: one autoplay Audio, Play queue, Skip, end event, cover and title; A7 Add to queue, Play now, DJ clip plug point |
| `test_generate_tab.py` | B7 Generate tab: the 8.1 controls and help text, Generate disabled while running and re-enabled after success or failure, each stage with elapsed time and the usual wait, 7.3 errors with Retry and inputs kept, the result card, the cover by `track_id`, B8 warnings before Generate, one run end to end with Qwen and ACE-Step mocked |
| `test_config.py` | `jukebox/config.py`: required variables, one port per service, no port 9000, no secrets in output |
| `test_check_config.py` | `scripts/check_config.py`: OK/missing table that never prints values |
| `test_requirements_dev.py` | `requirements-dev.txt`: exact `==` pins for pytest, respx and ruff; CI and `setup_dev.py` install it |
| `test_player.py` | `jukebox/services/player.py`: queue order, skip, a missing DJ clip, end of queue |
| `test_chatterbox.py` | `jukebox/clients/chatterbox.py`: `speak()` request format (default and reference voice), local input checks, each error kind with no retry, speech endpoint on 9008 only |
| `test_dj.py` | `jukebox/services/dj.py` and `prompts/dj.md`: song-specific script (title, word limit, cleanup, one retry), clip saved under `runtime/generated/`, only the Qwen and Chatterbox clients |
| `test_flux.py` | `jukebox/clients/flux.py`: `generate_image()` request format, defaults, decoded JPEG, each error kind, FLUX on 9006 only, key and image data never logged |
| `test_art_prompt.py` | `jukebox/services/art.py` prompt builder (C3): the `cover_art.md` template, filled placeholders and lyrics excerpt, reply cleanup, the safety suffix added once, Qwen errors, never FLUX |
| `test_art_service.py` | `jukebox/services/art.py` cover job (C4): saved by `track_id`, cover attached by id, placeholder on failure, Retry cover, job status, the committed placeholder, Qwen and FLUX only |
| `test_generate_samples.py` | `scripts/generate_samples.py` (C5): the 3 sample specs, files and manifest under `samples/`, the manifest loads in the library, the generation log (inputs, prompts, lyrics, models and ports, no host or key), all-or-nothing runs, B6's song pipeline, no client used directly |
| `test_<service>.py` | One per client in `jukebox/clients/` (added by lanes B, C, D) |

A good test case covers the happy path, at least one failure path (service down, bad input, timeout), and each "Done when" criterion of its task.

## Running them

```
pytest -q                 # everything (the gate and CI run it this same way; use plain pytest, not python -m pytest)
pytest tests/test_x.py -q # one file while you work
```

Manual and live tests (real class servers, audio, covers) are recorded in `docs/TEST_EVIDENCE.md` with `/log-test` (PROJECT.md §12.2).
