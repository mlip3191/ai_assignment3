"""Cover art (PROJECT.md 8.2): Qwen writes the FLUX image prompt, FLUX paints it.

Two halves:
  - The prompt builder (task C3): `write_cover_prompt()` turns a song's details into one FLUX prompt.
  - The cover job (task C4): `make_cover()` / `retry_cover()` paint a cover for a track, save it as
    `runtime/generated/{track_id}.jpg`, and attach it to the track by id. `cover_for()` gives the UI
    the file to show, falling back to the team-made placeholder. A failed cover never removes the song.

Allowed clients for this module: qwen and flux only (scripts/model_policy.json).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jukebox.clients import flux
from jukebox.config import ROOT
from jukebox.errors import ServiceError
from jukebox.jobs import JobStore
from jukebox.library import Library, LibraryError, get_library
from jukebox.models import Job, Track

_log = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompts" / "cover_art.md"
SECTIONS = ("System", "User", "Suffix")
LYRICS_EXCERPT_CHARS = 600
MAX_TOKENS = 300
TEMPERATURE = 0.8

COVER_EXT = "jpg"  # FLUX returns JPEG (C2; release lead's decision on #4)
COVER_DIR = "runtime/generated"  # relative to the repo root, forward slashes (works on every OS)
PLACEHOLDER = "jukebox/assets/placeholder_cover.png"  # drawn by a person, not by any model (8.2)
COVER_STAGE = "Painting cover…"

ChatFn = Callable[..., str]
ImageFn = Callable[..., bytes]

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
_DEVICE_NAME = re.compile(r"con|prn|aux|nul|com[1-9]|lpt[1-9]", re.IGNORECASE)  # Windows reserves these
_REPLACE_TRIES = 5
_REPLACE_WAIT_S = 0.05
# One save at a time. Windows refuses two swaps at once on the same file, and make_cover() holds it
# from the swap until the prompt is attached, so the stored prompt always matches the file on disk.
_write_lock = threading.RLock()
_cover_jobs = JobStore()  # cover jobs started without a `jobs` store (B6 hook, Retry cover)

_PLACEHOLDER = re.compile(r"\{(title|style|mood|theme|lyrics_block)\}")
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_EDGE_PUNCT = " \t\n.,;:"
_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’"}
_TAG_LINE = re.compile(r"^\s*\[[^\]]*\]\s*$")
# People and body parts in an image prompt. Body-part words don't count when they name part of a thing
# ("the face of the cliff", "a clock face", "clock hands", "table legs", "a hand-painted sign"); nor do "the
# man in the moon", "a figure of speech", "a couple of candles", "guy ropes" or "a table runner". Any word
# ending in "man" or "men" counts (fisherman, policewoman, human) except the few listed that aren't people
# (German, ottoman, Pullman, omen, ramen). A silhouette counts only after "a", "two", "lone" and the like
# ("a lone silhouette", sample 3), not in "palm tree silhouettes" or "a skyline, the silhouette softened";
# a silhouette of a person names the person.
_PEOPLE = re.compile(
    r"\b(?:"
    r"people|persons?|humans?|men|woman|women|boys?|girls?|child(?:ren)?|kids?|teen(?:ager)?s?|toddlers?"
    r"|bab(?:y|ies)(?!-|'s\s+breath|\s+(?:blue|pink|grand|breath)\b)|ladies|lady|guys?(?!-|\s+(?:ropes?|lines?|wires?)\b)"
    r"|(?:boy|girl)?friends?|(?:couples?|crowds?)(?!\s+of\b)|audiences?|spectators?|tourists?|famil(?:y|ies)"
    r"|lovers?|strangers?|owners?|someone|somebody|everyone|everybody"
    r"|(?:a|an|one|two|three|four|lone|single|solitary|distant|small|tiny)\s+silhouettes?(?!-|\s+of\b)"
    r"|mothers?|fathers?|daughters?|sons?|sisters?|brothers?|grand(?:mother|father)s?|(?:grand)?parents?|brides?"
    r"|travell?ers?|wanderers?|hikers?|sailors?|cyclists?|bikers?|riders?|skaters?|surfers?|swimmers?|skiers?"
    r"|drivers?|passengers?|(?<!\btable\s)(?<!\bcarpet\s)(?<!\bsled\s)runners?(?!\s+(?:of|beans?)\b)"
    r"|pedestrians|pedestrian(?!\s+(?:bridges?|crossings?|paths?|streets?|zones?|walkways?|tunnels?)\b)"
    r"|astronauts?|cowboys?(?!-|\s+(?:hats?|boots?)\b)|cowgirls?|soldiers?|warriors?|pilots?(?!\s+(?:lights?|whales?)\b)"
    r"|farmers?|workers?|baristas?|chefs?|nurses?|monks?|nuns?|ballerinas?|mermaids?|students?"
    r"|(?<!\brecord\s)(?<!\bvinyl\s)(?<!\bmusic\s)(?<!\bcassette\s)(?<!\btape\s)(?<!\bcd\s)(?<!\bdvd\s)"
    r"(?<!\bmp3\s)(?<!\bmedia\s)(?<!\bvideo\s)players?(?!-|\s+pianos?\b)"
    r"|dancers?|singers?|vocalists?|musicians?|performers?|guitarists?|drummers?|bassists?|pianists?|violinists?"
    r"|saxophonists?|trumpeters?|djs?(?!\s+(?:booths?|decks)\b)|concertgoers?|partygoers?|festivalgoers?|ravers?"
    r"|(?:rock|jazz|punk|indie|folk|blues|brass|marching|garage|boy|girl)\s+bands?"
    r"|bands?(?=\s+(?:plays?|playing|performs?|performing|on\s+stage)\b)"
    r"|(?<!\bceiling\s)(?<!\belectric\s)(?<!\bpalm\s)fans(?!\s+of\b)"
    r"|(?<!\bisle\sof\s)(?<!\bpac-)man(?!\s+in\s+the\s+moon|['’]s\s+land)(?!-)|figures?(?!-|\s+of\b)"
    r"|(?!(?:ger|otto|talis|cai|cay|snow|walk|dober|ro|pac|pull|tas|speci|abdo|acu|regi|o|sta|ra|a|lu|ye|hy"
    r"|se|cycla|dol|bitu|albu|ceru|ru|fora)m[ae]n\b)\w+m[ae]n(?!-)"
    r")\b",
    re.IGNORECASE,
)
# Body parts, in two kinds (see mentions_people). Hands, fingers, arms and shoulders are a person's: animals
# have paws and wings. Faces, heads, eyes, legs, feet and bodies can be an animal's.
_HANDS = re.compile(
    r"\b(?:"
    r"(?<!\bcoat\sof\s)(?<!\btone\s)arms?|(?<!\bclock\s)(?<!\bwatch\s)(?<!\bhour\s)(?<!\bminute\s)hands?|fingers?"
    r"|(?<!\bgravel\s)(?<!\broad\s)(?<!\bhard\s)(?<!\bdirt\s)(?<!\bpaved\s)(?<!\bhighway\s)shoulders?"
    r")(?!-|\s+of\b)\b",
    re.IGNORECASE,
)
_PARTS = re.compile(
    r"\b(?:"
    r"(?<!\bclock\s)(?<!\bwatch\s)(?<!\bcliff\s)(?<!\brock\s)faces?|bod(?:y|ies)|(?<!\btable\s)(?<!\bchair\s)legs?"
    r"|feet|foot|eyes|heads?(?!\s+(?:west|east|north|south|toward|towards|into|home)\b)"
    r")(?!-|\s+of\b)\b",
    re.IGNORECASE,
)
_ANIMAL = (
    r"(?:owl|cat|kitten|kitt(?:y|ies)|dog|pupp(?:y|ies)|fox(?:es)?|deer|stag|fawn|horse|pon(?:y|ies)|foal"
    r"|wol(?:f|ves)|bird|crow|raven|bear|rabbit|bunn(?:y|ies)|hare|fish|koi|whale|dolphin|seal|otter|lion|tiger"
    r"|leopard|elephant|giraffe|zebra|camel|cow|cal(?:f|ves)|sheep|lamb|goat|pig|frog|toad|butterfl(?:y|ies)"
    r"|moth|bee|duck|swan|goose|geese|heron|crane|eagle|hawk|falcon|sparrow|robin|finch|parrot|pigeon|(?:sea)?gull"
    r"|penguin|mouse|mice|rat|squirrel|hedgehog|badger|raccoon|monkey|panda|koala|octop(?:us|i)|jellyfish|snake"
    r"|serpent|lizard|turtle|tortoise|dragon|unicorn|creature|animal|beast)s?"
)
_ANIMAL_WORD = re.compile(rf"\b{_ANIMAL}\b", re.IGNORECASE)
_BIRDS_EYE = re.compile(r"\bbird['’]?s[-\s]+eye\b", re.IGNORECASE)  # a camera angle, not a bird
# Just before a body part (the text up to it ends with one of these): "her hands" and "his tired eyes" are
# a person's; "its long-fingered hands" and "a lizard with tiny hands" aren't.
_A_PERSONS = re.compile(r"\b(?:her|his|their|my|your|our)\s+(?:[\w'’-]+\s+){0,2}$", re.IGNORECASE)
_ITS = re.compile(r"\bits\s+(?:[\w'’-]+\s+){0,2}$", re.IGNORECASE)
_ANIMAL_WITH = re.compile(rf"\b{_ANIMAL}\s+with\s+(?:[\w'’-]+\s+){{0,3}}$", re.IGNORECASE)
# A thing's part: "the mountain's face", "the moon's pale face", "a record's label face down".
_A_THINGS = re.compile(
    r"\b(?:mountain|hill|moon|sun|planet|cliff|rock|stone|glacier|tower|building|wall|clock|watch|record"
    r"|turntable|statue|guitar|piano|chair|table)['’]s\s+(?:[\w'’-]+\s+){0,2}$",
    re.IGNORECASE,
)
# "Face" as a verb, or "face down": "a cabin faces a frozen lake", "windows face the sea".
_FACE_VERB = re.compile(
    r"faces?\s+(?:the|a|an|down|up|out|outward|away|toward|towards|onto|each|east|west|north|south)\b",
    re.IGNORECASE,
)
# Measurements: "a thousand feet above", "fifty feet tall", "a six-foot wave", "a 10-foot cactus".
_NUMBER = (
    r"(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty"
    r"|hundred|thousand|hundreds|thousands|few|several|many)"
)
_MEASURE = re.compile(
    rf"\b{_NUMBER}(?:\s+of)?\s+(?:feet|foot)(?=\s+(?:tall|high|deep|long|wide|thick|above|below|away"
    rf"|across)\b)|\b{_NUMBER}-(?:feet|foot)\b",
    re.IGNORECASE,
)
# "No people", "without a single person", "no faces or hands" and the like: an empty scene, so these words
# don't count. A list needs "or", "and" or "nor", so "no crowds, figures in the distance" keeps the figures.
_NO_NOUN = r"(?:(?:visible|real|other|human)\s+)?(?:people|persons?|humans?|figures?|crowds?|faces?|hands?|bod(?:y|ies))"
_NO_PEOPLE = re.compile(
    rf"\b(?:no|without(?:\s+any|\s+a\s+single)?|devoid\s+of|empty\s+of|free\s+of)\s+{_NO_NOUN}"
    rf"(?:,?\s+(?:or|and|nor)\s+{_NO_NOUN})*\b",
    re.IGNORECASE,
)
# Added to any prompt with people in it. FLUX follows positive descriptions better than "no ...": small,
# backlit figures with faces in shadow have no identifiable face, and soft hands hide its anatomy mistakes.
SOFT_PEOPLE = (
    "only as many people as described, seen from behind or at a distance as soft-focus backlit silhouettes, "
    "faces in shadow and not detailed, hands not in focus"
)
# A chatty opener such as "Here is your prompt:" or "Sure! Here's the image prompt:" (only these forms,
# so a real prompt with a colon in it, like "A quiet room: soft light", is left alone).
_LEAD_IN = re.compile(
    r"^(?:(?:sure|okay|ok|certainly)[!,.]?\s+)?(?:here(?:'s| is)|this is)\b[^:]{0,60}:\s*", re.IGNORECASE
)


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
    if mentions_people(body):
        # People stay in the scene, drawn so faces aren't defined and hands aren't prominent.
        body = re.sub(re.escape(SOFT_PEOPLE), "", body, flags=re.IGNORECASE)  # in case Qwen echoed it
        body = re.sub(r"\s*,(?:\s*,)+\s*", ", ", body).strip(_EDGE_PUNCT)
        body = f"{body}, {SOFT_PEOPLE}"
    return f"{body}, {t.suffix}"


def mentions_people(text: str) -> bool:
    """True if an image prompt describes people or body parts. FLUX draws them from the front with
    detailed faces, and sometimes wrong hands or an extra arm (TC-04 dry run, 10/24)."""
    text = _BIRDS_EYE.sub(" ", _MEASURE.sub(" ", _NO_PEOPLE.sub(" ", text)))
    if _PEOPLE.search(text):
        return True
    for part in _HANDS.finditer(text):
        before = text[max(0, part.start() - 80) : part.start()]  # bounded, so long prompts stay fast
        if _A_THINGS.search(before):
            continue
        if _A_PERSONS.search(before) or not (_ITS.search(before) or _ANIMAL_WITH.search(before)):
            return True
    for part in _PARTS.finditer(text):
        # An animal earlier in the sentence owns these ("a wolf howling at the moon, eyes glowing").
        before = text[max(0, part.start() - 120) : part.start()]
        # "A cabin faces the lake" names no person; "her face toward the rain" does.
        a_verb = _FACE_VERB.match(text, part.start()) and not _A_PERSONS.search(before)
        if _A_THINGS.search(before) or a_verb:
            continue
        sentence = before[max(before.rfind(end) for end in ".;!?") + 1 :]
        if _A_PERSONS.search(before) or not (_ITS.search(before) or _ANIMAL_WORD.search(sentence)):
            return True
    return False


def _lyrics_block(vocal: bool, lyrics: str | None) -> str:
    if not vocal:
        return "Instrumental track, no lyrics."
    # Section tags ([verse], [chorus]) and blank lines carry no imagery, so they don't use up the excerpt.
    lines = [
        line.strip() for line in (lyrics or "").splitlines() if line.strip() and not _TAG_LINE.match(line)
    ]
    text = "\n".join(lines)
    if not text:
        return "Vocal track, lyrics not available."
    if len(text) > LYRICS_EXCERPT_CHARS:
        cut = text[: LYRICS_EXCERPT_CHARS + 1]
        text = cut[: max(cut.rfind(" "), cut.rfind("\n"))].rstrip() or text[:LYRICS_EXCERPT_CHARS]
    return "Lyrics (excerpt):\n" + text


def _clean(reply: str | None, suffix: str) -> str:
    text = _THINK.sub(" ", reply or "")
    text = _LEAD_IN.sub("", " ".join(text.split()))
    text = _unquote(text).strip(_EDGE_PUNCT)
    if text.lower().endswith(suffix.lower()):
        # The quotes may sit before the suffix: '"A field", square album cover, ...'
        text = _unquote(text[: -len(suffix)].strip(_EDGE_PUNCT))
    return text.strip(_EDGE_PUNCT)


def _unquote(text: str) -> str:
    """Remove one pair of quotes around the whole reply; a lone quote inside it is left alone."""
    core = text.strip().rstrip(".,;: ")
    if len(core) >= 2 and core[0] in _QUOTE_PAIRS and core[-1] == _QUOTE_PAIRS[core[0]]:
        return core[1:-1]
    return text


def _qwen_chat() -> ChatFn:
    from jukebox.clients import qwen  # imported on first use, so building messages needs no settings

    return qwen.chat


# ---- the cover job (C4) -------------------------------------------------------------------------


def render_cover(
    track: Track, dest: Path, *, chat: ChatFn | None = None, generate: ImageFn | None = None
) -> str:
    """Write the prompt with Qwen, paint it with FLUX, save the image at `dest`. Returns the prompt.

    Used by `make_cover()` for generated songs and by scripts/generate_samples.py for the samples.
    Raises ServiceError on any service failure; nothing is left at `dest` in that case.
    """
    prompt, image = _paint(track, chat=chat, generate=generate)
    _write_atomically(Path(dest), image)
    return prompt


def _paint(track: Track, *, chat: ChatFn | None, generate: ImageFn | None) -> tuple[str, bytes]:
    """The prompt (Qwen) and the image bytes (FLUX, with the track's seed). Saves nothing."""
    prompt = write_cover_prompt(
        title=track.title,
        style=track.style,
        mood=track.mood,
        theme=track.theme,
        vocal=track.vocal,
        lyrics=track.lyrics,
        chat=chat,
    )
    return prompt, (generate or flux.generate_image)(prompt, seed=track.seed)


def make_cover(
    track_id: str,
    *,
    library: Library | None = None,
    jobs: JobStore | None = None,
    root: Path = ROOT,
    chat: ChatFn | None = None,
    generate: ImageFn | None = None,
) -> Track:
    """Paint a cover for the track and attach it. Returns the updated Track.

    On a service failure the track keeps playing with no cover (the UI shows the placeholder and
    "Retry cover"), the job (if given) records the plain-language message, and the ServiceError is
    re-raised for the caller. Raises LibraryError for an unknown track, ValueError for an unsafe id.
    The job is created before any check, so every failure, these included, ends on a job: a UI that
    polls cover_job_for() never waits on "Painting cover…" for a cover that will never come.
    """
    job = jobs.create("cover", COVER_STAGE) if jobs else None
    if jobs and job:
        jobs.set_stage(job.id, COVER_STAGE, track_id)
    try:
        if not _SAFE_ID.fullmatch(track_id) or _DEVICE_NAME.fullmatch(track_id):
            raise ValueError(f"track id {track_id!r} can't be used as a file name")
        lib = library or get_library()
        track = lib.get(track_id)
        if track is None:
            raise LibraryError(f"no track {track_id!r} in the library")
        relative = f"{COVER_DIR}/{track_id}.{COVER_EXT}"
        prompt, image = _paint(track, chat=chat, generate=generate)  # slow, so outside the lock
        with _write_lock:
            _write_atomically(Path(root) / relative, image)
            updated = lib.attach_cover(track_id, relative, prompt)
    except Exception as err:
        # Any failure, not only a ServiceError, must finish the job so the UI never stays
        # stuck on "Painting cover". JobStore.fail() shows only a safe message.
        if jobs and job:
            jobs.fail(job.id, err)
        raise
    if jobs and job:
        jobs.succeed(job.id, track_id)
    return updated


def start_cover(track: Track, **kwargs) -> threading.Thread:
    """Start painting the track's cover on a background thread and return at once (for B6).

    The song is already in the library and playable; the cover appears when ready. A failure never
    reaches the caller: make_cover() records it on the job and the UI shows the placeholder with
    "Retry cover" (see cover_job_for()). Only the error's type is logged, never its text. Takes the
    same keyword arguments as make_cover(); without `jobs` the shared cover job store is used.
    Returns the thread, so tests and callers can wait for it.
    """
    kwargs["jobs"] = kwargs.get("jobs") or _cover_jobs

    def run() -> None:
        try:
            make_cover(track.id, **kwargs)
        except Exception as err:
            _log.warning("cover for track %s failed in the background (%s)", track.id, type(err).__name__)

    thread = threading.Thread(target=run, name=f"cover-{track.id}", daemon=True)
    thread.start()
    return thread


def retry_cover(track_id: str, **kwargs) -> Track:
    """The "Retry cover" button: paint a fresh cover for the track (same rules as make_cover).

    Without `jobs` the shared cover job store is used, so cover_job_for() shows this attempt.
    """
    kwargs["jobs"] = kwargs.get("jobs") or _cover_jobs
    return make_cover(track_id, **kwargs)


def cover_job_for(track_id: str, *, jobs: JobStore | None = None) -> Job | None:
    """The cover job the UI should show for the track ("Painting cover…" or the failed message), or None.

    A running job comes first. Otherwise it is the job that finished last, not the one started last:
    Retry clicked twice can finish out of order. Times are to the second, so on a tie a success wins,
    since its cover really is attached.
    """
    store = jobs or _cover_jobs
    matching = [j for j in store.list() if j.kind == "cover" and j.track_id == track_id]
    running = [j for j in matching if j.finished_at is None]
    if running:
        return running[-1]
    if not matching:
        return None
    return max(enumerate(matching), key=lambda p: (p[1].finished_at, p[1].status == "succeeded", p[0]))[1]


def cover_for(track_id: str, *, library: Library | None = None) -> Path:
    """The image file to show for a track, always looked up by id: its cover, or the placeholder.

    Paths are resolved by the library itself (`Library.resolve`), the same rule the UI uses.
    """
    lib = library or get_library()
    track = lib.get(track_id)
    if track and track.cover_path:
        path = lib.resolve(track.cover_path)
        if path.is_file():
            return path
    return placeholder_path()


def placeholder_path() -> Path:
    """The committed, hand-drawn placeholder cover (never generated by a model)."""
    return ROOT / PLACEHOLDER


def _write_atomically(dest: Path, data: bytes) -> None:
    """Write via a uniquely named temporary file, then swap it in, so a reader never sees half an
    image and two covers for the same track at once (Retry clicked twice) never collide."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        with _write_lock:
            _replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _replace(tmp: Path, dest: Path) -> None:
    """os.replace, retried briefly: on Windows it fails with PermissionError while another
    process (for example the browser loading the old cover) still has the file open."""
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            if attempt == _REPLACE_TRIES - 1:
                raise
            time.sleep(_REPLACE_WAIT_S)
