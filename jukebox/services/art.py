"""Cover art (PROJECT.md 8.2): Qwen writes the FLUX image prompt, FLUX paints it.

This file currently holds the prompt-building half (task C3). The cover job that calls FLUX,
saves the image, and offers Retry cover is task C4.

Allowed clients for this module: qwen and flux only (scripts/model_policy.json).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jukebox.errors import ServiceError

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "cover_art.md"
SECTIONS = ("System", "User", "Suffix")
LYRICS_EXCERPT_CHARS = 600
MAX_TOKENS = 300
TEMPERATURE = 0.8

ChatFn = Callable[..., str]

_PLACEHOLDER = re.compile(r"\{(title|style|mood|theme|lyrics_block)\}")
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_EDGE_PUNCT = " \t\n.,;:"
_QUOTES = "\"'“”‘’"


@dataclass(frozen=True)
class CoverTemplate:
    system: str
    user: str
    suffix: str


def load_template(path: Path = TEMPLATE_PATH) -> CoverTemplate:
    """Read the System, User, and Suffix sections of prompts/cover_art.md."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    missing = [name for name in SECTIONS if not "\n".join(sections.get(name, [])).strip()]
    if missing:
        raise ValueError(f"{path.name} is missing the section(s): {', '.join(missing)}")
    text = {name: "\n".join(sections[name]).strip() for name in SECTIONS}
    return CoverTemplate(system=text["System"], user=text["User"], suffix=text["Suffix"])


def build_messages(
    *,
    title: str,
    style: str,
    mood: str,
    theme: str | None,
    vocal: bool,
    lyrics: str | None,
    template: CoverTemplate | None = None,
) -> list[dict[str, str]]:
    """The chat messages that ask Qwen for one image prompt for this song."""
    t = template or load_template()
    values = {
        "title": title.strip(),
        "style": style.strip(),
        "mood": mood.strip(),
        "theme": (theme or "").strip() or "none given",
        "lyrics_block": _lyrics_block(vocal, lyrics),
    }
    user = _PLACEHOLDER.sub(lambda m: values[m.group(1)], t.user)
    return [{"role": "system", "content": t.system}, {"role": "user", "content": user}]


def write_cover_prompt(
    *,
    title: str,
    style: str,
    mood: str,
    theme: str | None,
    vocal: bool,
    lyrics: str | None,
    chat: ChatFn | None = None,
) -> str:
    """Ask Qwen for the image prompt and add the fixed suffix. Raises ServiceError on failure.

    `chat` defaults to the Qwen client's `chat()` (PROJECT.md 7.2); tests pass a fake.
    """
    t = load_template()
    messages = build_messages(
        title=title, style=style, mood=mood, theme=theme, vocal=vocal, lyrics=lyrics, template=t
    )
    ask = chat or _qwen_chat()
    reply = ask(messages, max_tokens=MAX_TOKENS, temperature=TEMPERATURE)
    body = _clean(reply, t.suffix)
    if not body:
        raise ServiceError("qwen", "bad_response", "the cover prompt reply was empty")
    return f"{body}, {t.suffix}"


def _lyrics_block(vocal: bool, lyrics: str | None) -> str:
    if not vocal:
        return "Instrumental track, no lyrics."
    text = (lyrics or "").strip()
    if not text:
        return "Vocal track, lyrics not available."
    return "Lyrics (excerpt):\n" + text[:LYRICS_EXCERPT_CHARS].rstrip()


def _clean(reply: str | None, suffix: str) -> str:
    text = _THINK.sub(" ", reply or "")
    text = " ".join(text.split()).strip(_QUOTES + " ")
    text = text.strip(_EDGE_PUNCT)
    if text.lower().endswith(suffix.lower()):
        text = text[: -len(suffix)]
    return text.strip(_EDGE_PUNCT + _QUOTES)


def _qwen_chat() -> ChatFn:
    from jukebox.clients import qwen  # B3; imported here so C3 can be built and tested first

    return qwen.chat
