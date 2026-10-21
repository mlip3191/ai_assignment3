"""The AI DJ (F3): a short, song-specific spoken intro before each queued song (PROJECT.md 8.3).

Qwen writes the script from `prompts/dj.md`; Chatterbox speaks it; the clip is saved under
`runtime/generated/`. Only those two clients are used (H15).

  - The script is cleaned of anything TTS would read aloud (emojis, *stage directions*, [tags],
    labels, wrapping quotes), then checked: it must say the track's title and stay within
    MAX_WORDS. A script that fails is sent back to Qwen once with the reason. If the second one
    also fails, ServiceError(service="qwen", kind="bad_response") is raised and nothing is spoken.
    There is never a template or hand-written stand-in (PROJECT.md 7.0).
  - Errors from either client pass through unchanged. The caller (prefetch, D5) skips the DJ clip
    and the song still plays.
  - Clips are named `dj_<track_id>_<voice_key>.<ext>`. `voice_key` is "default" or a short hash of
    the reference recording, so a new voice never reuses an old clip (D5 caches by both).
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jukebox.clients import chatterbox, qwen
from jukebox.config import ROOT
from jukebox.errors import ServiceError

GENERATED_DIR = ROOT / "runtime" / "generated"
PROMPT_PATH = ROOT / "jukebox" / "prompts" / "dj.md"

MAX_WORDS = 50
MIN_WORDS = 15  # the prompt asks for 30-45; this floor only catches a one-liner like "Up next: X."
MAX_ATTEMPTS = 2
QWEN_MAX_TOKENS = 200
QWEN_TEMPERATURE = 0.9
# Delivery, picked by ear on 2026-10-19 (D3 tuning): the same intro at service defaults (0.5/0.5,
# flat, as noted in D1), 0.7/0.3, and 1.0/0.3. The last sounded most like a radio DJ.
DJ_EXAGGERATION = 1.0
DJ_CFG_WEIGHT = 0.3
# Saving a clip on Windows (see _write_atomically): retries when the target is briefly locked.
REPLACE_ATTEMPTS = 5
REPLACE_WAIT_S = 0.05
_REPLACE_LOCK = threading.Lock()
_sleep = time.sleep  # tests replace this


class TrackInfo(Protocol):
    """The Track fields the DJ needs (PROJECT.md 6.1)."""

    id: str
    title: str
    style: str
    mood: str
    theme: str | None


@dataclass(frozen=True)
class DjClip:
    track_id: str
    voice_key: str
    script: str
    audio_path: Path


# ---- prompt ------------------------------------------------------------------------------------


def _prompt_sections() -> tuple[str, str]:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    _, _, rest = text.partition("## System")
    system, _, user = rest.partition("## User")
    return system.strip(), user.strip()


_PLACEHOLDER = re.compile(r"\{(title|style|mood|theme|previous)\}")


def build_messages(track: TrackInfo, previous: TrackInfo | None = None) -> list[dict]:
    system, user = _prompt_sections()
    values = {
        "title": track.title,
        "style": track.style,
        "mood": track.mood,
        "theme": track.theme or "none given",
        "previous": f"Previous song: {previous.title} ({previous.style}, {previous.mood})"
        if previous
        else "",
    }
    # One pass over the template: a value that itself contains "{mood}" etc. is never filled in again,
    # and braces in a title can't break anything (no str.format).
    user = _PLACEHOLDER.sub(lambda m: values[m.group(1)], user)
    return [{"role": "system", "content": system}, {"role": "user", "content": user.strip()}]


# ---- script ------------------------------------------------------------------------------------

_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff‍️⭐⭕⤴⤵]")
# *stage direction* (no space just inside the asterisks, so "5 * 2" and "3*4" survive), [tag], and
# (laughs)-style parentheticals that start with a performance cue. Other parentheses are kept.
_STAGE = re.compile(
    r"\*[^\s*](?:[^*\n]{0,58}[^\s*])?\*"
    r"|\[[^\]\n]{1,60}\]"
    r"|\((?:laugh|chuckl|giggl|paus|sigh|whisper|cheer|applau|music|beat|cough|clears|excited|softly|upbeat)"
    r"[^)\n]{0,40}\)",
    re.IGNORECASE,
)
_LABEL = re.compile(r"^\s*(?:dj|intro|announcer|host)\s*:\s*", re.IGNORECASE)
_QUOTE_PAIRS = {'"': '"', "'": "'", "“": "”", "‘": "’"}  # strip only a matched opening/closing pair


def clean_script(text: str) -> str:
    """Remove what TTS would read aloud but shouldn't: emojis, *stage directions*, [tags], labels, quotes."""
    script = _EMOJI.sub("", text or "")
    script = _STAGE.sub(" ", script)
    script = script.replace("#", " ").replace("`", " ")
    script = " ".join(script.split())
    script = _LABEL.sub("", script)
    if len(script) >= 2 and _QUOTE_PAIRS.get(script[0]) == script[-1]:
        script = script[1:-1].strip()
    return script


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def script_problem(script: str, title: str) -> str | None:
    """Why this script can't be used, or None if it's fine."""
    if not script:
        return "the reply was empty"
    words = len(script.split())
    if words > MAX_WORDS:
        return f"it was {words} words; keep it to {MAX_WORDS} words or fewer"
    # The title goes through the same cleanup as the script ("Midnight [Remix]" is spoken as
    # "Midnight"), and must appear as whole words ("Run" doesn't match "Running").
    wanted = _normalize(clean_script(title))
    if wanted and f" {wanted} " not in f" {_normalize(script)} ":
        return f'it didn\'t say the song title, "{title}"'
    if words < MIN_WORDS:
        return f"it was only {words} words; use at least {MIN_WORDS}"
    return None


def write_script(track: TrackInfo, previous: TrackInfo | None = None) -> str:
    """Ask Qwen for the intro; one corrective retry; raises ServiceError if it still can't be used."""
    messages = build_messages(track, previous)
    problem = ""
    for _ in range(MAX_ATTEMPTS):
        reply = qwen.chat(messages, max_tokens=QWEN_MAX_TOKENS, temperature=QWEN_TEMPERATURE)
        script = clean_script(reply)
        problem = script_problem(script, track.title) or ""
        if not problem:
            return script
        messages = [
            *messages,
            {"role": "assistant", "content": reply},
            {
                "role": "user",
                "content": f"That intro can't be used: {problem}. Write it again: 30 to 45 words, "
                f'plain text, and say the exact title "{track.title}" once.',
            },
        ]
    raise ServiceError(
        "qwen", "bad_response", f"DJ script still unusable after {MAX_ATTEMPTS} tries: {problem}"
    )


# ---- clip --------------------------------------------------------------------------------------


def voice_key(voice_ref_path: str | None) -> str:
    """'default', or a short hash of the reference recording's bytes."""
    if voice_ref_path is None:
        return "default"
    return hashlib.sha256(Path(voice_ref_path).read_bytes()).hexdigest()[:12]


def _safe_id(track_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", track_id).strip("_") or "track"


def make_clip(
    track: TrackInfo,
    *,
    voice_ref_path: str | None = None,
    previous: TrackInfo | None = None,
    out_dir: Path | None = None,
) -> DjClip:
    """Write and speak the intro for `track`, save it, and return where it is.

    Raises ServiceError when Qwen or Chatterbox fails, and OSError when the clip can't be written
    (disk full, or on Windows the old clip still open). The caller treats both as "skip the DJ clip".
    """
    script = write_script(track, previous)
    audio, ext = chatterbox.speak(
        script, voice_ref_path=voice_ref_path, exaggeration=DJ_EXAGGERATION, cfg_weight=DJ_CFG_WEIGHT
    )
    key = voice_key(voice_ref_path)
    folder = Path(out_dir) if out_dir is not None else GENERATED_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"dj_{_safe_id(track.id)}_{key}.{ext}"
    _write_atomically(path, audio)
    return DjClip(track_id=track.id, voice_key=key, script=script, audio_path=path)


def _write_atomically(path: Path, data: bytes) -> None:
    """Write to a temp file in the same folder, then rename, so a reader never sees half a clip.

    On Windows, renaming onto a file that another thread is replacing at the same moment, or that the
    player still has open, raises PermissionError (macOS and Linux allow it). The lock serializes our
    own swaps, and a short retry rides out a brief open handle. Same approach as the cover saves (C4).
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".dj-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        with _REPLACE_LOCK:
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    _sleep(REPLACE_WAIT_S)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
