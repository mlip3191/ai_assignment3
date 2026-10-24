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


# ---- the real-artist safeguard (B8) -------------------------------------------------------------

# Words that describe a sound rather than name someone, so "in the style of Latin jazz", "Detroit techno"
# or "Retro style synths" are kept. Anything else after a pointer phrase ("in the style of", "sounds like",
# ...) is treated as a name and removed. Bare names with no pointer phrase are not caught.
_SOUND_WORDS = frozenset(
    """
    pop rock jazz blues soul funk disco house techno trance edm electronic electronica dance ambient
    classical orchestral orchestra cinematic folk country bluegrass americana punk metal grunge emo indie
    alternative hip hop hip-hop rap trap drill r&b rnb gospel reggae reggaeton ska dub dubstep drum bass
    jungle garage grime lo-fi lofi chillhop chillwave synthwave vaporwave synth synths synth-pop synthpop
    wave shoegaze dream psychedelic psych prog progressive post-rock krautrock industrial gothic goth
    darkwave latin salsa bossa nova samba tango flamenco mariachi cumbia afrobeat afrobeats highlife
    celtic irish bollywood k-pop j-pop kpop jpop anime chiptune 8-bit baroque opera choral acoustic
    electric piano guitar guitars strings brass lounge swing bebop big band music beats neo christmas
    holiday western spaghetti southern bedroom yacht trip city video game games movie film soundtrack
    lullaby ballad ballads show tune tunes
    retro vintage classic modern old new epic dreamy dark soft heavy chill upbeat mellow warm bright
    moody lush minimal experimental instrumental vocal vocals live raw smooth funky jazzy groovy early late
    rainy sunny stormy summer winter spring autumn fall night nights midnight morning sunset sunrise
    detroit chicago nashville memphis orleans london berlin ibiza uk british english french spanish
    italian german greek nordic scandinavian russian japanese korean chinese indian arabic african
    brazilian cuban jamaican caribbean mexican american west east coast female male
    sunday monday tuesday wednesday thursday friday saturday motown brazil cuba jamaica mexico japan
    korea india africa ireland scotland spain france italy paris tokyo havana rio
    tropical island cozy phonk afro boom bap hyperpop dancehall nu halloween solo solos moonlight
    heartfelt emotional drums pad pads chorus tempo slow fast hooks catchy reverb beat driving deep sad
    happy road
    """.split()
)
MAX_SCREENED_CHARS = 300  # style and theme are cut to this before screening, so pasted text stays fast
_CONNECTORS = frozenset({"of", "the", "and", "or", "&", "de", "la", "del", "van", "von", "da", "y"})
# A capitalized word. "/" keeps "AC/DC" and "Gaga/Madonna" together; "$" inside keeps "A$AP" and "Ke$ha"
# whole (Mike's review of #48: "A$AP Rocky" left "$AP Rocky" behind).
_WORD_TAIL = r"[\w'’.&+/$-]*"
_CAP = rf"[A-ZÀ-ÖØ-Þ]{_WORD_TAIL}"
# A word that starts with "$" is a name only with a second "$" ("$uicideboy$") or after another name word
# ("Ty Dolla $ign"), so "$ummer", "$ad" and "$mall" stay everyday words.
_DOLLAR_NAME = r"\$[A-Za-z][\w'’.&+/-]*\$[\w'’.&+/$-]*"
_NAME = (
    rf"(?:[Tt]he\s+)?(?:{_CAP}|{_DOLLAR_NAME})"
    rf"(?:\s+(?:(?:of|the|and|or|&|de|la|del|van|von|da|y)\s+)*(?:{_CAP}|\$[A-Za-z]{_WORD_TAIL}))*"
)
_EVERYDAY_DOLLAR = re.compile(r"\$[a-z][^$]*")  # one leading "$" and no second one ("$ummer", "$ad")
_NAME_AHEAD = rf"(?=\s+(?-i:[A-ZÀ-ÖØ-Þ]|{_DOLLAR_NAME}))"  # a name follows: "feat Drake", "a la $uicideboy$"
_NAME_AT_START = re.compile(_NAME)
# Pointer phrases that say "make it sound like someone". The theme gets only the first group (a theme is
# a subject, so "a love song inspired by Paris" or "dancing like Nobody is watching" must stay).
_STYLE_POINTERS = (
    r"in\s+the\s+(?:style|vein|spirit|manner)\s+of|sounds?\s+like|à\s+la"
    rf"|a\s+la{_NAME_AHEAD}"  # "a la carte" isn't one
)
_THEME_POINTER = re.compile(rf"\b(?:{_STYLE_POINTERS})\s+", re.IGNORECASE)
# Credits name who made a song. A bare "by" counts only at the start of a part, so "folk by the Sea",
# "song by Candlelight" and "Played by Ear" stay; "feat"/"ft" without a period need a capital after them.
_CREDITS = (
    r"(?:sung|performed|produced|written|covered|vocals)\s+by|covers?\s+of|featuring|feat\.|ft\."
    rf"|(?:feat|ft){_NAME_AHEAD}"
    r"|(?<=^)by|(?<=^\s)by"
)
_CREDIT = re.compile(rf"(?:{_CREDITS})\s*$", re.IGNORECASE)
_POINTER = re.compile(
    rf"\b(?:{_STYLE_POINTERS}|the\s+voice\s+of|inspired\s+by|influenced\s+by|reminiscent\s+of|similar\s+to"
    rf"|{_CREDITS}"
    r"|like(?=\s+(?:a|an|my|our|your|his|her|their|this|that)\s))\s+",  # "like a <Name> anthem"
    re.IGNORECASE,
)
# Only the explicit "-style / -esque / -inspired". Looser forms ("<Name> vibe", "type beat", "-ish",
# "-like") can't be told apart from everyday styles ("Golden Hour vibes", "Workout type beat"), so they
# are a known limit (B9).
_NAME_STYLE = re.compile(rf"(?<![\w'’-])({_NAME})(?:-|\s+)(?i:style|esque|inspired)\b")
_POSSESSIVE = re.compile(
    rf"(?<![\w'’-])({_NAME})['’]s\s+(?i:voice|vocals?|sound|style|music|songs?|singing|band)\b"
)
_LIKE_NAME = re.compile(rf"(?i:\blike)\s+({_NAME})")
_JOINER = re.compile(r"^\s*(?:and|or|&|/)\s+", re.IGNORECASE)  # "Ed Sheeran and pop" leaves "pop"
_OWNER = frozenset({"a", "an", "my", "our", "your", "his", "her", "their", "this", "that"})
_ERA = re.compile(r"'?\d{2,4}s")


@dataclass(frozen=True)
class StyleCheck:
    """Style or theme text with anything pointing at a real artist removed (PROJECT.md 8.1, H10)."""

    text: str
    removed: tuple[str, ...] = ()

    @property
    def warning(self) -> str | None:
        """What the UI shows when something was removed, or None."""
        if not self.removed:
            return None
        quoted = [f"“{phrase}”" for phrase in self.removed]
        listed = quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " and " + quoted[-1]
        return f"Removed {listed}. Artist names aren't sent to the song models."


def check_style(text: str) -> StyleCheck:
    """Remove "in the style of <Name>", "sounds like <Name>", "<Name>-esque", "<Name>'s voice",
    "featuring <Name>", "like <Name>" and similar from the style.

    A name is a capitalized word run ("Taylor Swift", "AC/DC", "Adele or Drake"); lowercase words are
    never treated as a name, so "inspired by the sea" stays. Genres, places and eras are kept ("in the
    style of Detroit techno" becomes "Detroit techno"), and so is a description that starts with "a", "my"
    and the like unless it names someone. B7's form shows `.warning`.
    """
    return _screen(text, _POINTER, (_POSSESSIVE, _NAME_STYLE, _LIKE_NAME))


def check_theme(text: str) -> StyleCheck:
    """The theme's screen: only obvious style pointers ("in the style of <Name>", "sounds like <Name>",
    "à la <Name>"). A theme is a subject, so names and places in it stay ("inspired by Paris", "Mom").
    B7's form shows `.warning` for the theme too."""
    return _screen(text, _THEME_POINTER, (), list_rule=False)


def _screen(
    text: str, pointer: re.Pattern[str], patterns: tuple[re.Pattern[str], ...], *, list_rule: bool = True
) -> StyleCheck:
    if not isinstance(text, str) or not text.strip():
        return StyleCheck(text if isinstance(text, str) else "")
    text = text[:MAX_SCREENED_CHARS]
    removed: list[str] = []
    parts = re.split(r"([,;])", text)
    screened: list[str] = []
    after_name = False  # the last part ended with a removed name, so a listed name ("Adele, Drake") goes too
    for part in parts:
        if part in (",", ";"):
            screened.append(part)
        elif list_rule and after_name and _looks_like_another_name(part):
            removed[-1] += f", {part.strip()}"
            screened.append("")
        else:
            part, after_name = _screen_part(part, removed, pointer, patterns)
            screened.append(part)
    if screened == parts:
        return StyleCheck(text)
    joined = re.sub(r"\(\s*\)|\[\s*\]", "", "".join(screened))  # "pop (like Adele)" leaves no "()"
    joined = re.sub(r"\s+", " ", joined)
    joined = re.sub(r"\s*([,;])\s*", r"\1 ", joined)
    joined = re.sub(r"(?:[,;]\s*){2,}", ", ", joined)
    return StyleCheck(joined.strip(" ,;-"), tuple(removed))


def _screen_part(
    part: str, removed: list[str], pointer: re.Pattern[str], patterns: tuple[re.Pattern[str], ...]
) -> tuple[str, bool]:
    """One comma-separated part with any pointer at a real artist taken out, and whether it ended with a
    removed name."""
    start, ended_with_name = 0, False
    while match := pointer.search(part, start):
        rest = part[match.end() :]
        name = _NAME_AT_START.match(rest)
        words = rest.split()
        if name and not _is_sound(name.group(0)):
            removed.append(part[match.start() : match.end() + name.end()].strip())
            tail = _JOINER.sub("", rest[name.end() :])
            part = part[: match.start()] + tail
            ended_with_name = not tail.strip()
            start = match.start()
        elif name and _CREDIT.search(match.group(0)):
            start = match.end()  # "pop ft. Heavy Bass": a credit before a sound is ordinary text
        elif name:
            part = part[: match.start()] + rest  # a genre or place ("Latin jazz"): drop only the pointer
            start = match.start()
        elif words and words[0].lower() in _OWNER:
            # "sounds like a movie soundtrack" describes and is kept, unless it names someone
            # ("in the style of a Taylor Swift song"): then the whole description goes.
            if any(not _is_sound(m.group(0)) for m in _NAME_AT_START.finditer(rest)):
                removed.append(part[match.start() :].strip())
                part = part[: match.start()]
                start = match.start()
            else:
                start = match.end()
        elif words and _is_sound(words[0]) and not _CREDIT.search(match.group(0)):
            part = part[: match.start()] + rest  # "in the style of 80s synthwave": drop only the pointer
            start = match.start()
        else:
            # Lowercase words are a description ("inspired by the sea"), not a name. A lowercase artist
            # name isn't caught either; that is a known limit, like a bare name (B9).
            start = match.end()
    for pattern in patterns:
        part = pattern.sub(lambda m: _drop_name(m, removed), part)
    return part, ended_with_name


def _looks_like_another_name(part: str) -> bool:
    """A comma part right after a removed name that is another name ("in the style of Adele, Drake") or
    the rest of one ("Earth, Wind & Fire"): a capitalized name with no sound word in it. A title-case tag
    with any sound word ("Warm Pads", "Rainy Day", "Female Vocals") is kept and ends the list."""
    text = part.strip()
    if not _NAME_AT_START.fullmatch(text):
        return False
    words = [w.lower().strip(".,'’\"()") for w in text.split()]
    return not any(_is_sound_word(w) for w in words if w and w not in _CONNECTORS)


def _drop_name(match: re.Match[str], removed: list[str]) -> str:
    if _is_sound(match.group(1)):
        return match.group(0)
    removed.append(match.group(0).strip())
    return ""


def _is_sound(phrase: str) -> bool:
    """True if every word describes a sound (a genre, place, era or descriptor), so it isn't a name.

    An everyday "$" word ("$ummer", "$ound") is neutral: "Detroit $ound" is a sound, "Ty Dolla $ign" isn't.
    """
    words = [w.lower().strip(".,'’\"()") for w in phrase.split()]
    words = [w for w in words if w and w not in _CONNECTORS and not _EVERYDAY_DOLLAR.fullmatch(w)]
    return bool(words) and all(_is_sound_word(w) for w in words)


def _is_sound_word(word: str) -> bool:
    if word in _SOUND_WORDS or _ERA.fullmatch(word):
        return True
    pieces = [p for p in re.split(r"[-/]", word) if p]
    return len(pieces) > 1 and all(p in _SOUND_WORDS or _ERA.fullmatch(p) for p in pieces)


def _screen_artists(style: str, theme: str | None) -> tuple[str, str | None]:
    """Apply check_style to the style and check_theme to the theme before any model call. A style that
    named only an artist is refused; a theme that named only an artist becomes no theme."""
    if isinstance(style, str):
        checked = check_style(style)
        if checked.removed and not checked.text:
            raise _bad_input("Describe the style without naming real artists.")
        style = checked.text
    if isinstance(theme, str):
        theme = check_theme(theme).text or None
    return style, theme


# ---- the pipeline (B6) --------------------------------------------------------------------------

STAGE_QUEUED = "Queued"
STAGE_LYRICS = "Writing lyrics…"
STAGE_TITLE = "Naming your track…"
STAGE_MUSIC = "Composing music…"
STAGE_SAVING = "Saving your song…"
STAGE_DONE = "Added to your library"
GENERATED_DIR = "runtime/generated"  # stored paths are relative to the repo root (PROJECT.md 6.3)
# A singing voice named in the style; "singer-songwriter" (a genre) and "vocal chops" (an effect) are not.
_VOICE_WORDS = re.compile(
    r"\b(?:vocal(?:s|ists?)?|voices?|singers?|singing|choirs?|rappers?|sopranos?|falsetto|crooners?"
    r"|a\s+cappella|acapella)\b(?!-songwriter|\s+chops?\b|\s+sax)",
    re.IGNORECASE,
)

# Song jobs go here unless the caller passes the app's own store.
JOBS = JobStore()


def build_tags(style: str, mood: str, *, vocal: bool) -> str:
    """ACE-Step's style tags: the style, the mood, and the voice or "instrumental".

    "warm natural vocals" because the default voice came out too high-pitched and whiny (B2, B6). It is
    added only when the style names no voice of its own ("deep male vocals", "choir"), so the tags never
    carry two voices (review of #40).
    """
    if not vocal:
        voice = "instrumental"
    elif _VOICE_WORDS.search(style):
        voice = ""
    else:
        voice = "warm natural vocals"
    return ", ".join(part for part in (style.strip(), mood.strip(), voice) if part)


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
    saved: Path | None = None
    track: Track | None = None
    try:
        yield job
        style, theme = _screen_artists(style, theme)
        duration_s, seed = _check_inputs(style, mood, duration_s, seed)
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


def _check_inputs(style: str, mood: str, duration_s: object, seed: object) -> tuple[int, int | None]:
    """Refuse what ACE-Step can't make before spending a Qwen call on it.

    Returns the duration and seed as ints: a Gradio slider or number box may send 60.0 for 60, and the
    Track needs whole numbers (PROJECT.md 6.1).
    """
    if not isinstance(style, str) or not style.strip():
        raise _bad_input("Choose a style.")
    if not isinstance(mood, str) or not mood.strip():
        raise _bad_input("Choose a mood.")
    duration = _whole_number(duration_s)
    if duration is None:
        raise _bad_input("Duration must be a whole number of seconds.")
    if not acestep.MIN_DURATION_S <= duration <= acestep.MAX_DURATION_S:
        raise _bad_input(
            f"Duration must be between {acestep.MIN_DURATION_S} and {acestep.MAX_DURATION_S} seconds."
        )
    whole_seed = None if seed is None else _whole_number(seed)
    if seed is not None and whole_seed is None:
        raise _bad_input("Seed must be a whole number.")
    return duration, whole_seed


def _whole_number(value: object) -> int | None:
    """`value` as an int if it is a whole number (60 or 60.0), else None. True and "60" are not numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


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
        else:
            sung = _without_unmatched_brackets(line)
            if sung:
                (sections[-1][1] if sections else loose).append(sung)
    if not found_tag:
        raise _bad_response("the lyrics had no section tags")
    if loose:
        sections.insert(0, ("verse", loose))
    if not any(lines for tag, lines in sections if tag != "intro"):
        raise _bad_response("the lyrics had no sung lines")
    kept = [(tag, lines) for tag, lines in sections if lines and tag != "intro"]
    blocks = ["[intro]"] + ["\n".join([f"[{tag}]", *lines]) for tag, lines in kept]
    return "\n\n".join(blocks)


def _without_unmatched_brackets(line: str) -> str:
    """A sung line without stray brackets ("Corporate chains are tight]", seen live in B6).

    Matched pairs like "(with me)" stay; if a line's [ and ] (or ( and )) don't pair up, they all go.
    """
    for opening, closing in ("[]", "()"):
        if line.count(opening) != line.count(closing):
            line = line.replace(opening, "").replace(closing, "")
    return " ".join(line.split())


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
