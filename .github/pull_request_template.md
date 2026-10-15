## Summary
Part of #<!-- your lane issue number -->
Task: <!-- task key, e.g. B4 (the checkbox in your lane issue ticks itself when this PR merges) -->

**Requirement IDs:** <!-- e.g. F1a, R6 -->

## What changed
-

## How it was tested
<!-- Exact commands and results. Manual browser steps you actually did, and on which OS. Include what failed. -->
- [ ] `ruff check .` passes
- [ ] `pytest` passes
- [ ] `python scripts/scan_secrets.py` passes
- [ ] `python scripts/check_models.py` passes (only the four class models, each used for its own feature)
- Manual:

## Task "Done when" criteria (copy from your lane issue)
- [ ] Met / Partly / Not met — evidence:

## Screenshots
<!-- Required for any UI change. Save keepers to docs/screenshots/ for the README. No credentials visible. -->

## Safeguards check
- [ ] No credentials, `.env`, or key values in code, logs, docs, screenshots, or this PR
- [ ] No port 9000; no AI model, SDK, or provider other than Qwen (text), FLUX (covers), ACE-Step (music), Chatterbox (DJ speech); no fallback to any other model
- [ ] No uploads or voice recordings committed; no third-party music/lyrics/art/voice
- [ ] New dependencies pinned to exact versions
- [ ] Only files in my lane changed, or the owning lane is tagged as a reviewer
- [ ] PROJECT.md updated if this changes an interface, an endpoint format, or a decision

## AI assistance
<!-- e.g. "Written with Claude Code; I reviewed every change and ran the tests above." -->

## For the reviewer
<!-- What should they try in the browser? Anything risky to look at closely? -->
