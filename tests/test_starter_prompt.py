"""Tests that protect the assignment's starter prompt in docs/STARTER_PROMPT.md (task C0).

The assignment says to "retain all existing language". These tests compare the
"Original starter prompt" block with a copy taken from the assignment PDF
(MBAX 6418 Assignment 3), so nobody can change it by accident.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER_PROMPT = ROOT / "docs" / "STARTER_PROMPT.md"

ORIGINAL_HEADING = "## Original starter prompt"
ADDITIONS_HEADING = "## Team additions"

# Copied from the assignment PDF, line for line, including its blank lines.
ASSIGNMENT_PROMPT = """\
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
"""


def _text() -> str:
    return STARTER_PROMPT.read_text(encoding="utf-8")


def _fenced_block_after(heading: str) -> list[str]:
    """Return the lines inside the first ``` fence that follows a heading."""
    lines = _text().splitlines()
    start = lines.index(heading)
    opening = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "```")
    closing = next(i for i in range(opening + 1, len(lines)) if lines[i].strip() == "```")
    return lines[opening + 1 : closing]


def _non_blank(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip()]


def test_original_block_matches_assignment_word_for_word() -> None:
    original = _fenced_block_after(ORIGINAL_HEADING)
    assert _non_blank(original) == _non_blank(ASSIGNMENT_PROMPT.splitlines())


def test_original_block_keeps_the_assignment_blank_lines() -> None:
    assert _fenced_block_after(ORIGINAL_HEADING) == ASSIGNMENT_PROMPT.splitlines()


def test_original_block_present_once() -> None:
    text = _text()
    assert text.count(ORIGINAL_HEADING) == 1
    assert text.count("# Overarching Task: Build an AI Jukebox") == 1


def test_additions_block_is_separate_and_after_original() -> None:
    lines = _text().splitlines()
    assert ADDITIONS_HEADING in lines
    assert lines.index(ORIGINAL_HEADING) < lines.index(ADDITIONS_HEADING)
    additions = _fenced_block_after(ADDITIONS_HEADING)
    assert additions[0] == "# Team Additions"
    assert "# Overarching Task: Build an AI Jukebox" not in additions


def test_no_em_dashes() -> None:
    assert "\u2014" not in _text()
