"""Show generated text on the page as plain text, never as Markdown formatting."""

from __future__ import annotations

import re

_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~])")
_LINE_BREAKS = re.compile(r"[\r\n  \x0b\x0c\x85]+")
_LIST_MARKER = re.compile(r"^(?:(\d+)\.|-)")


def escape(text: str) -> str:
    """One plain line: line breaks become a space, and no character or leading list marker formats."""
    one_line = _LINE_BREAKS.sub(" ", text).strip()
    escaped = _SPECIAL.sub(r"\\\1", one_line)
    return _LIST_MARKER.sub(lambda m: f"{m.group(1)}\\." if m.group(1) else "\\-", escaped)
