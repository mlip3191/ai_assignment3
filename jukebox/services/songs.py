"""Song generation (PROJECT.md 8.1). Models: Qwen for the title and lyrics, ACE-Step for the audio.

`generate_song()` is the pipeline (B6): it checks the inputs, has Qwen write the title (and lyrics for a
vocal song), has ACE-Step compose the audio, saves it to `runtime/generated/{track_id}.{ext}`, adds the
Track to the library and starts the cover job without waiting for it. It yields a Job snapshot at every
stage for the UI, and never raises: any failure ends the job with a PROJECT.md 7.3 message.

The title and lyrics prompts (`jukebox/prompts/lyrics.md`, `title.md`) and the parser for Qwen's reply
are B5. Lyrics use ACE-Step's lowercase section tags (PROJECT.md 7.1). Their structure scales with the
duration (`plan_sections`) and always starts with an empty `[intro]`, because lyrics that don't fit the
length, or singing that starts at 0 s, came out garbled in the live tests (B2, B4).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from string import Template

from jukebox.clients import acestep, qwen
from jukebox.errors import ServiceError
from jukebox.jobs import JobStore
from jukebox.library import Library, get_library
from jukebox.models import Job, Track

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LYRICS_MAX_TOKENS = 1200  # the longest planned song is 18 lines; room to spare for a wordy reply
TITLE_MAX_TOKENS = 100
TEMPERATURE = 0.8
MAX_INPUT_CHARS = 200  # style, mood and theme as sent to Qwen
MAX_TITLE_CHARS = 60
NO_THEME = "none given; choose a subject that fits the style and mood"

# Section headers Qwen writes ("Final Chorus", "Verse Two", "Post-Chorus"), mapped to ACE-Step's tags.
_HEAD = re.compile(
    r"(?:(?:final|last|first|second|third|fourth|opening|closing)\s+)?"
    r"(post[- ]?chorus|pre[- ]?chorus|intro|verse|chorus|hook|refrain|bridge|outro)(?![a-z])",
    re.IGNORECASE,
)
# What may follow the name in an unbracketed header: a number, then a "- note" or "(note)", then ":".
_HEAD_TAIL = re.compile(
    r"\s*(?:\d+|one|two|three|four|five|i{1,3}|iv|v)?(?![a-z])\s*(?:[-–—]\s*[^:]*|\([^)]*\))?\s*:?\s*$",
    re.IGNORECASE,
)
_TAG_FOR = {"hook": "chorus", "refrain": "chorus", "postchorus": "chorus", "prechorus": "pre-chorus"}
_BRACKETED = re.compile(r"^\[([^\]]*)\]$")
_PARENTHESIZED = re.compile(r"^\(([^)]*)\)$")
# Repeat marks such as "(x2)", "[x3]" or "(Repeat chorus)": the prompt asks for repeats written out in full.
_REPEAT_MARK = re.compile(r"\s*[(\[]\s*(?:x\s*\d+|\d+\s*x|repeat\b[^)\]]*)\s*[)\]]\s*$", re.IGNORECASE)
_BARE_REPEAT = re.compile(r"^x\s*\d+$", re.IGNORECASE)
_LENIENT_JSON = json.JSONDecoder(strict=False)  # allows real line breaks inside strings
# A closing chat line such as "Hope you enjoy this song!": a phrase aimed at the listener and a word about
# the song. Single words like "hope" or "like" are too common in lyrics to count.
_SIGN_OFF = re.compile(
    r"^(?=.*\b(?:hope you|enjoy (?:this|the)|let me know|feel free|happy to)\b)(?=.*\b(?:song|lyrics|track)\b)",
    re.IGNORECASE,
)
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

    Write only what ACE-Step will sing. Heard in B5 and B6: from 30 to 60 s it sings about one verse and
    one chorus (8 to 10 lines). Given more, it skips whole sections from the middle of the song (18 lines
    at 45, 50 and 60 s came out as the first verse, part of the chorus and the outro), so extra lines only
    make the song lose its middle. Under 20 s, a 2-line verse; under 30 s, 2-line verse and chorus; under
    40 s, verse and chorus; under 75 s, verse, chorus and outro (at 60 s only the outro was dropped);
    from 75 s, two verses and choruses and an outro (not yet heard).
    """
    verse, chorus, outro = ("verse", 4), ("chorus", 4), ("outro", 2)
    if duration_s < 20:
        body = [("verse", 2)]
    elif duration_s < 30:
        body = [("verse", 2), ("chorus", 2)]
    elif duration_s < 40:
        body = [verse, chorus]
    elif duration_s < 75:
        body = [verse, chorus, outro]
    else:
        body = [verse, chorus, verse, chorus, outro]
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


# ---- the pipeline (B6) --------------------------------------------------------------------------

STAGE_QUEUED = "Queued"
STAGE_LYRICS = "Writing lyrics…"
STAGE_TITLE = "Naming your track…"
STAGE_MUSIC = "Composing music…"
STAGE_SAVING = "Saving your song…"
STAGE_DONE = "Added to your library"
GENERATED_DIR = "runtime/generated"  # stored paths are relative to the repo root (PROJECT.md 6.3)

# Song jobs go here unless the caller passes the app's own store.
JOBS = JobStore()


def build_tags(style: str, mood: str, *, vocal: bool) -> str:
    """ACE-Step's style tags: the style, the mood, and the voice or "instrumental".

    "warm natural vocals" because the default voice came out too high-pitched and whiny (B2, B6). A voice
    the user puts in the style ("deep male vocals") comes first, so it wins.
    """
    return ", ".join([style.strip(), mood.strip(), "warm natural vocals" if vocal else "instrumental"])


def generate_song(
    *,
    style: str,
    mood: str,
    duration_s: int,
    vocal: bool,
    theme: str | None = None,
    seed: int | None = None,
    library: Library | None = None,
    jobs: JobStore | None = None,
    start_cover: Callable[[Track], object] | None = None,
) -> Iterator[Job]:
    """Make one song and yield a Job snapshot at every stage (R5).

    The last snapshot is `succeeded` with the new `track_id`, or `failed` with a user-facing `error`
    (PROJECT.md 7.3). It never raises, so the UI can always re-enable its buttons. The Track joins the
    library only after its audio is saved (6.3); after any failure there is no track and no audio file.
    `start_cover(track)` runs on a background thread once the track is in the library, and nothing it
    does (slow, failing) affects the song.
    """
    jobs = JOBS if jobs is None else jobs
    job = jobs.create("song", STAGE_QUEUED)
    yield job
    saved: Path | None = None
    track: Track | None = None
    try:
        _check_inputs(style, mood, duration_s)
        library = get_library() if library is None else library
        yield jobs.set_stage(job.id, STAGE_LYRICS if vocal else STAGE_TITLE)
        text = write_song_text(style=style, mood=mood, theme=theme, duration_s=duration_s, vocal=vocal)
        yield jobs.set_stage(job.id, STAGE_MUSIC)
        audio, ext = acestep.generate_music(
            tags=build_tags(style, mood, vocal=vocal), lyrics=text.lyrics, duration_s=duration_s, seed=seed
        )
        yield jobs.set_stage(job.id, STAGE_SAVING)
        track_id = uuid.uuid4().hex
        audio_path = f"{GENERATED_DIR}/{track_id}.{ext}"
        saved = _save_audio(library.resolve(audio_path), audio)
        track = library.add(
            Track(
                id=track_id,
                title=text.title,
                style=style.strip(),
                mood=mood.strip(),
                theme=theme.strip() if theme and theme.strip() else None,
                duration_s=duration_s,
                vocal=vocal,
                lyrics=text.lyrics,
                audio_path=audio_path,
                cover_path=None,
                cover_prompt=None,
                source="generated",
                seed=seed,
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        saved = None  # the library has it now
        jobs.set_stage(job.id, STAGE_DONE, track.id)
    except GeneratorExit:
        # The UI stopped listening part-way. Finish the job so it never stays "running".
        _discard(saved)
        jobs.fail(job.id, "stopped before the song was finished")
        raise
    except Exception as e:  # every failure ends the job; ServiceError gets its 7.3 message
        _discard(saved)
        yield jobs.fail(job.id, e)
        return
    _start_cover(start_cover, track)
    yield jobs.succeed(job.id, track.id)


def _check_inputs(style: str, mood: str, duration_s: int) -> None:
    """Refuse what ACE-Step can't make before spending a Qwen call on it."""
    if not isinstance(style, str) or not style.strip():
        raise _bad_input("Choose a style.")
    if not isinstance(mood, str) or not mood.strip():
        raise _bad_input("Choose a mood.")
    if not acestep.MIN_DURATION_S <= duration_s <= acestep.MAX_DURATION_S:
        raise _bad_input(
            f"Duration must be between {acestep.MIN_DURATION_S} and {acestep.MAX_DURATION_S} seconds."
        )


def _bad_input(reason: str) -> ServiceError:
    return ServiceError("acestep", "bad_request", f"input check: {reason}", reason=reason)


def _save_audio(path: Path, audio: bytes) -> Path:
    """Write the audio under a temporary name first, so a half-written file is never visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        part.write_bytes(audio)
        part.replace(path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return path


def _discard(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


def _start_cover(start_cover: Callable[[Track], object] | None, track: Track) -> None:
    """Run the cover job on its own thread. A cover problem is logged, never passed to the song."""
    if start_cover is None:
        return

    def run() -> None:
        try:
            start_cover(track)
        except Exception as e:
            log.warning("cover job for track %s failed (%s)", track.id, type(e).__name__)

    try:
        threading.Thread(target=run, name=f"cover-{track.id[:8]}", daemon=True).start()
    except RuntimeError:
        log.warning("cover job for track %s could not start", track.id)


# ---- parsing the reply --------------------------------------------------------------------------


def parse_song_reply(text: str, *, vocal: bool) -> SongText:
    """Read Qwen's reply: JSON `{"title", "lyrics"}` first, then a plain-text "Title: ..." fallback.

    JSON with real line breaks inside a string (a common model mistake) is still read as JSON. Lyrics are
    normalized to ACE-Step's tags. Raises `ServiceError(kind="bad_response")` if there is no title, or a
    vocal song has no usable lyrics. The reply's text is never copied into the error.
    """
    try:
        data: dict | None = qwen.parse_json_reply(text)
    except ServiceError:
        data = None
    if data is None or "title" not in data:
        data = _parse_lenient_json(text) or _parse_plain_text(text)
    title = clean_title(data.get("title"))
    if not title:
        raise _bad_response("the reply had no title")
    if not vocal:
        return SongText(title, None)
    lyrics = data.get("lyrics")
    if isinstance(lyrics, list):
        lyrics = "\n".join(line for line in lyrics if isinstance(line, str))
    if not isinstance(lyrics, str) or not lyrics.strip():
        raise _bad_response("the reply had no lyrics")
    return SongText(title, normalize_lyrics(_without_leading_title(lyrics, title)))


def _parse_lenient_json(text: str) -> dict | None:
    """The first JSON object with a "title" in the reply, allowing real line breaks inside strings.

    Skips other objects (`{"thought": ...}`) so the song after them is still found. None if there is none.
    """
    cleaned = qwen.strip_think(text)
    start = cleaned.find("{")
    while start != -1:
        try:
            value, _end = _LENIENT_JSON.raw_decode(cleaned, start)
        except ValueError:
            value = None
        if isinstance(value, dict) and "title" in value:
            return value
        start = cleaned.find("{", start + 1)
    return None


def _parse_plain_text(text: str) -> dict[str, str]:
    """`Title: ...` on one line, and the lyrics after it.

    The lyrics start at the first section header and stop at a code fence, so "Here are your lyrics:" and
    text after the fence are not sung. A last single line that reads like chat ("Hope you enjoy this
    song!") is the model's sign-off and is dropped too; blank lines inside the lyrics change nothing.
    """
    cleaned = qwen.strip_think(text)
    match = _TITLE_LINE.search(cleaned)
    if not match:
        raise _bad_response("the reply was neither JSON nor 'Title: ...' text")
    lines = cleaned[match.end() :].splitlines()
    start = next((i for i, line in enumerate(lines) if _section_tag(line)), 0)
    lines = lines[start:]
    end = next((i for i, line in enumerate(lines) if _FENCE.match(line)), len(lines))
    lines = [line for line in lines[:end] if not _LYRICS_LABEL.match(line)]
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > 1 and _SIGN_OFF.match(lines[-1]) and not _section_tag(lines[-1]):
        lines.pop()
    return {"title": match.group(1), "lyrics": "\n".join(lines)}


def _without_leading_title(lyrics: str, title: str) -> str:
    """Lyrics without the title repeated above them ("Open Road", "**Open Road**", "Title: Open Road").

    Only when a section header comes next, so a first sung line that matches the title is kept.
    """
    lines = lyrics.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    following = [line for line in lines[1:] if line.strip()]
    if lines and clean_title(lines[0]).lower() == title.lower() and following and _section_tag(following[0]):
        lines.pop(0)
    return "\n".join(lines)


def clean_title(raw: object) -> str:
    """The title's first line, without quotes, markdown or a "Title:" label, capped at a word boundary."""
    if not isinstance(raw, str):
        return ""
    lines = [line for line in raw.splitlines() if line.strip()]
    title = " ".join(lines[0].split()) if lines else ""
    title = re.sub(r"^title\s*[:\-]\s*", "", title.strip("#*_ "), flags=re.IGNORECASE)
    title = title.strip("\"'“”‘’*_ .").strip()
    if len(title) > MAX_TITLE_CHARS:
        cut = title[: MAX_TITLE_CHARS + 1]
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
        title = cut[:MAX_TITLE_CHARS].rstrip(" ,;:-")
    return title


def normalize_lyrics(text: str) -> str:
    """Rewrite lyrics in ACE-Step's format.

    Section headers in any common form (`[Verse 1]`, `**[CHORUS]**`, `**Verse 1**:`, `Final Chorus:`,
    `## Hook`, `(Bridge)`, `Chorus (x2)`) become lowercase tags; other bracketed lines (`[Guitar Solo]`)
    and repeat marks (`(x2)`, `(Repeat chorus)`) are dropped. Lines before the first tag become a verse,
    and empty sections are dropped. The song always starts with an empty `[intro]`.
    Raises `ServiceError(kind="bad_response")` if there are no section tags or no sung lines.
    """
    sections: list[tuple[str, list[str]]] = []
    loose: list[str] = []
    found_tag = False
    for raw_line in text.splitlines():
        line = _REPEAT_MARK.sub("", raw_line).strip()
        if not line or _BARE_REPEAT.match(line):
            continue
        tag = _section_tag(line)
        if tag:
            found_tag = True
            sections.append((tag, []))
        elif _BRACKETED.match(_header_text(line)):
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


def _header_text(line: str) -> str:
    """A line without markdown: `**Verse 1**:` becomes `Verse 1:`, `## Hook` becomes `Hook`."""
    return re.sub(r"[*_]", "", line).strip().lstrip("#>").strip()


def _section_tag(line: str) -> str | None:
    """The ACE-Step tag a line stands for, or None if it is not a section header.

    A bracketed header may carry any note after the name ("[Verse 2 - softer]"). Other forms must be just
    the name, a number, and a "- note" or "(note)", so a sung line like "Chorus of angels" stays a lyric.
    """
    text = _header_text(line)
    bracketed = _BRACKETED.match(text)
    parenthesized = _PARENTHESIZED.match(text)
    content = (bracketed or parenthesized).group(1).strip() if bracketed or parenthesized else text
    head = _HEAD.match(content)
    if not head:
        return None
    if not bracketed and not _HEAD_TAIL.match(content, head.end()):
        return None
    word = re.sub(r"[- ]", "", head.group(1).lower())
    return _TAG_FOR.get(word, word)


def _bad_response(detail: str) -> ServiceError:
    return ServiceError("qwen", "bad_response", detail)
