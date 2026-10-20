# Test cases

Every automated test case for the AI Jukebox lives here. The rules are the same for everyone:

1. **Every change needs test cases.** If you change code in `jukebox/`, `scripts/`, `.claude/hooks/`, `.githooks/`, or `app.py`, add or update a test here in the same branch. Only docs-only changes are exempt. The pre-push gate blocks a push that changes code without touching `tests/`.
2. **Build the tests first.** Write the test, watch it fail, then write the code until it passes (`/start-session` plans it this way).
3. **Every push runs every test.** The pre-push gate (`scripts/prepush.py`) runs the full suite, so new work is always checked against all existing test cases. CI runs it again on every PR.
4. **Never call the real class services in tests.** Mock them with `respx`. No credentials in tests.

## Layout

One file per module, named `test_<module>.py`:

| File | Covers |
|---|---|
| `test_guardrails.py` | Claude Code guard hook, session check, hook launcher |
| `test_prepush.py` | Pre-push gate and the secret scan's `.env` handling |
| `test_check_models.py` | Only-the-four-class-models check |
| `test_lanes.py` | Lane issue generation |
| `test_config.py` | `jukebox/config.py`: required variables, one port per service, no port 9000, no secrets in output |
| `test_check_config.py` | `scripts/check_config.py`: OK/missing table that never prints values |
| `test_chatterbox.py` | `jukebox/clients/chatterbox.py`: `speak()` request format (default and reference voice), local input checks, each error kind with no retry, speech endpoint on 9008 only |
| `test_dj.py` | `jukebox/services/dj.py` and `prompts/dj.md`: song-specific script (title, word limit, cleanup, one retry), clip saved under `runtime/generated/`, only the Qwen and Chatterbox clients |
| `test_<service>.py` | One per client in `jukebox/clients/` (added by lanes B, C, D) |

A good test case covers the happy path, at least one failure path (service down, bad input, timeout), and each "Done when" criterion of its task.

## Running them

```
pytest -q                 # everything (what the gate and CI run)
pytest tests/test_x.py -q # one file while you work
```

Manual and live tests (real class servers, audio, covers) are recorded in `docs/TEST_EVIDENCE.md` with `/log-test` (PROJECT.md §12.2).
