"""A7 shared Markdown escape: generated text shown on the page can't add formatting, links or blocks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.ui.markdown import escape  # noqa: E402


def test_plain_text_is_left_alone() -> None:
    assert escape("Rainy Desk") == "Rainy Desk"
    assert escape("") == ""


@pytest.mark.parametrize("char", list("\\`*_{}[]<>()#+!|~"))
def test_markdown_characters_are_escaped(char: str) -> None:
    assert escape(f"a{char}b") == f"a\\{char}b"


@pytest.mark.parametrize("text", ["x\n# injected", "x\r\n# injected", "x\r# injected", "x # injected"])
def test_a_line_break_cannot_start_a_new_block(text: str) -> None:
    out = escape(text)
    assert "\n" not in out
    assert "\r" not in out
    assert " " not in out
    assert out == "x \\# injected"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("- Intro", "\\- Intro"),
        ("1. Intro", "1\\. Intro"),
        ("12. Intro", "12\\. Intro"),
        ("-- Intro", "\\-- Intro"),
        ("  - Intro", "\\- Intro"),
    ],
)
def test_a_leading_list_marker_is_escaped(text: str, expected: str) -> None:
    assert escape(text) == expected


def test_a_dash_or_number_inside_the_text_is_kept() -> None:
    assert escape("Lo-fi 2. Night") == "Lo-fi 2. Night"
