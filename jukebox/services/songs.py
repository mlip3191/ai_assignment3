"""Song generation (PROJECT.md 8.1). Models: Qwen for the title and lyrics, ACE-Step for the audio.

B5 part: the title and lyrics prompts (`jukebox/prompts/lyrics.md`, `title.md`) and the parser for Qwen's
reply. `write_song_text()` makes one Qwen call and returns a `SongText`; the song pipeline (B6) passes its
lyrics to ACE-Step.

Lyrics use ACE-Step's lowercase section tags (PROJECT.md 7.1). Their structure scales with the duration
(`plan_sections`) and always starts with an empty `[intro]`, because lyrics that don't fit the length,
or singing that starts at 0 s, came out garbled in the live tests (B2, B4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

from jukebox.clients import qwen
from jukebox.errors import ServiceError

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LYRICS_MAX_TOKENS = 1200  # the longest planned song is about 40 lines
TITLE_MAX_TOKENS = 100
TEMPERATURE = 0.8
MAX_INPUT_CHARS = 200  # style, mood and theme as sent to Qwen
MAX_TITLE_CHARS = 60
NO_THEME = "none given; choose a subject that fits the style and mood"

# Section name variants Qwen writes, mapped to ACE-Step's tags. Checked in order, so pre-chorus comes first.
_SECTION_NAMES = re.compile(
    r"(pre[- ]?chorus|intro|verse|chorus|hook|refrain|bridge|outro)(?![a-z])", re.IGNORECASE
)
_TAG_FOR = {"hook": "chorus", "refrain": "chorus"}
_BRACKETED = re.compile(r"^\[([^\]]*)\]$")
_PARENTHESIZED = re.compile(r"^\(([^)]*)\)$")
_BARE_HEADER = re.compile(r"^([a-z][a-z -]*?)[\s\d]*:?$", re.IGNORECASE)
_TITLE_LINE = re.compile(r"^[\s*_#>]*title[\s*_]*[:\-][\s*_]*(.+)$", re.IGNORECASE | re.MULTILINE)
_LYRICS_LABEL = re.compile(r"^[\s*_#>]*lyrics[\s*_]*:?[\s*_]*$", re.IGNORECASE)
_FENCE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class SongText:
    """What Qwen wrote for one song. `lyrics` is None for an instrumental."""

    title: str
    lyrics: str | None


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


# ---- prompts ------------------------------------------------------------------------------------


def load_prompt(name: str) -> Prompt:
    """Read `jukebox/prompts/<name>.md`. Only its `## System` and `## User` sections are sent to Qwen."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip().lower(), [])
        elif current is not None:
            current.append(line)
    return Prompt(system="\n".join(sections["system"]).strip(), user="\n".join(sections["user"]).strip())


def plan_sections(duration_s: int) -> list[tuple[str, int]]:
    """The song's sections and how many lines each gets, scaled to the duration.

    Roughly two sung sections per 30 s (PROJECT.md 8.1). Starting points, to be tuned by ear:
    under 40 s, one verse and chorus; under 75 s, two of each and an outro; from 75 s, a bridge before the
    last chorus, and one more verse and chorus per extra minute, up to two more.
    """
    verse, chorus, bridge, outro = ("verse", 4), ("chorus", 4), ("bridge", 4), ("outro", 2)
    if duration_s < 40:
        body = [verse, chorus]
    elif duration_s < 75:
        body = [verse, chorus, verse, chorus, outro]
    else:
        extra = min(2, (duration_s - 75) // 60)
        body = [verse, chorus, verse, chorus] + [verse, chorus] * extra + [bridge, chorus, outro]
    return [("intro", 0), *body]


def build_messages(
    name: str, *, style: str, mood: str, theme: str | None, duration_s: int
) -> list[dict[str, str]]:
    """The system and user messages for prompt `name`, with the user's inputs filled in."""
    prompt = load_prompt(name)
    values = {
        "style": _tidy(style),
        "mood": _tidy(mood),
        "theme": _tidy(theme or "") or NO_THEME,
        "duration_s": str(duration_s),
        "structure": _describe(plan_sections(duration_s)),
    }
    return [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": Template(prompt.user).substitute(values)},
    ]


def _describe(plan: list[tuple[str, int]]) -> str:
    return "\n".join(
        f"[{name}] (instrumental, no lyrics)" if lines == 0 else f"[{name}] {lines} lines"
        for name, lines in plan
    )


def _tidy(text: str) -> str:
    """One line of user text: whitespace collapsed and length capped."""
    return " ".join(str(text).split())[:MAX_INPUT_CHARS].strip()


# ---- calling Qwen -------------------------------------------------------------------------------


def write_song_text(*, style: str, mood: str, theme: str | None, duration_s: int, vocal: bool) -> SongText:
    """Ask Qwen for a title, plus lyrics for a vocal song. One call. Raises ServiceError (PROJECT.md 7.3).

    Uses `qwen.chat()` rather than `chat_json()` so a reply that isn't JSON can still be read as plain text.
    """
    name, max_tokens = ("lyrics", LYRICS_MAX_TOKENS) if vocal else ("title", TITLE_MAX_TOKENS)
    messages = build_messages(name, style=style, mood=mood, theme=theme, duration_s=duration_s)
    reply = qwen.chat(messages, max_tokens=max_tokens, temperature=TEMPERATURE)
    return parse_song_reply(reply, vocal=vocal)


# ---- parsing the reply --------------------------------------------------------------------------


def parse_song_reply(text: str, *, vocal: bool) -> SongText:
    """Read Qwen's reply: JSON `{"title", "lyrics"}` first, then a plain-text "Title: ..." fallback.

    Lyrics are normalized to ACE-Step's tags. Raises `ServiceError(kind="bad_response")` if there is no
    title, or a vocal song has no usable lyrics. The reply's text is never copied into the error.
    """
    try:
        data = qwen.parse_json_reply(text)
    except ServiceError:
        data = _parse_plain_text(text)
    title = clean_title(data.get("title"))
    if not title:
        raise _bad_response("the reply had no title")
    if not vocal:
        return SongText(title, None)
    lyrics = data.get("lyrics")
    if isinstance(lyrics, list):
        lyrics = "\n".join(str(line) for line in lyrics)
    if not isinstance(lyrics, str) or not lyrics.strip():
        raise _bad_response("the reply had no lyrics")
    return SongText(title, normalize_lyrics(lyrics))


def _parse_plain_text(text: str) -> dict[str, str]:
    """`Title: ...` on one line, and everything after it as the lyrics."""
    cleaned = qwen.strip_think(text)
    match = _TITLE_LINE.search(cleaned)
    if not match:
        raise _bad_response("the reply was neither JSON nor 'Title: ...' text")
    rest = cleaned[match.end() :].splitlines()
    lines = [line for line in rest if not _LYRICS_LABEL.match(line) and not _FENCE.match(line)]
    return {"title": match.group(1), "lyrics": "\n".join(lines)}


def clean_title(raw: object) -> str:
    """The title's first line, without quotes, markdown or a "Title:" label, capped at a word boundary."""
    if not isinstance(raw, str):
        return ""
    lines = [line for line in raw.splitlines() if line.strip()]
    title = " ".join(lines[0].split()) if lines else ""
    title = re.sub(r"^title\s*[:\-]\s*", "", title.strip("#*_ "), flags=re.IGNORECASE)
    title = title.strip("\"'“”‘’*_ .").strip()
    if len(title) > MAX_TITLE_CHARS:
        title = title[: MAX_TITLE_CHARS + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return title


def normalize_lyrics(text: str) -> str:
    """Rewrite lyrics in ACE-Step's format.

    Section headers in any common form (`[Verse 1]`, `**[CHORUS]**`, `Pre-Chorus:`, `## Hook`, `(Bridge)`)
    become lowercase tags; other bracketed lines (`[Guitar Solo]`) are dropped. Lines before the first tag
    become a verse, and empty sections are dropped. The song always starts with an empty `[intro]`.
    Raises `ServiceError(kind="bad_response")` if there are no section tags or no sung lines.
    """
    sections: list[tuple[str, list[str]]] = []
    loose: list[str] = []
    found_tag = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = line.strip("*_#> ").strip()
        tag = _section_tag(header)
        if tag:
            found_tag = True
            sections.append((tag, []))
        elif _BRACKETED.match(header):
            continue  # an instrumental or performance note, not a sung line
        elif sections:
            sections[-1][1].append(line)
        else:
            loose.append(line)
    if not found_tag:
        raise _bad_response("the lyrics had no section tags")
    if loose:
        sections.insert(0, ("verse", loose))
    if not any(lines for tag, lines in sections if tag != "intro"):
        raise _bad_response("the lyrics had no sung lines")
    kept = [(tag, lines) for tag, lines in sections if lines and tag != "intro"]
    blocks = ["[intro]"] + ["\n".join([f"[{tag}]", *lines]) for tag, lines in kept]
    return "\n\n".join(blocks)


def _section_tag(header: str) -> str | None:
    """The ACE-Step tag a header line stands for, or None if the line is not a section header."""
    for pattern, whole_line in ((_BRACKETED, False), (_PARENTHESIZED, True), (_BARE_HEADER, True)):
        match = pattern.match(header)
        if not match:
            continue
        name = match.group(1).strip().lower()
        found = _SECTION_NAMES.match(name)
        if not found:
            return None
        # A bracket may carry a note ("[Verse 2 - softer]"); other forms must be just the name and a number.
        if whole_line and name[found.end() :].strip(" 0123456789:"):
            return None
        word = re.sub(r"[- ]", "", found.group(1).lower())
        word = "pre-chorus" if word == "prechorus" else word
        return _TAG_FOR.get(word, word)
    return None


def _bad_response(detail: str) -> ServiceError:
    return ServiceError("qwen", "bad_response", detail)
