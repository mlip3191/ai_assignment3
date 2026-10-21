"""Generate the three bundled sample songs (PROJECT.md 8.5, tasks C5 and C6).

Run from the repo root with the project venv active and your settings in place:

    python scripts/generate_samples.py

Each sample goes through the app's own code path: the song pipeline (B6: Qwen writes the title and
lyrics, ACE-Step makes the audio) and the cover service (C4: Qwen writes the image prompt, FLUX
paints it). Nothing is written, drawn, or edited by a person. The script writes:

    samples/audio/sample_0N.mp3     samples/covers/sample_0N.jpg
    samples/manifest.json           samples/GENERATION_LOG.md

All or nothing: everything is built in a staging folder under runtime/tmp/, checked by loading the
manifest into the app's library, and only then swapped into samples/. A failure leaves samples/ as
it was. Seeds are sent and logged, but ACE-Step did not reproduce audio from a fixed seed (B2), so
the committed files are the source of truth, not a regeneration.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.errors import ServiceError, user_message  # noqa: E402
from jukebox.library import Library, LibraryError  # noqa: E402
from jukebox.models import Track  # noqa: E402

STAGING = Path("runtime") / "tmp" / "samples-staging"
PREVIOUS = Path("runtime") / "tmp" / "samples-previous"
SWAP_MARKER = Path("runtime") / "tmp" / "samples-swap-in-progress"  # exists only during the swap
GENERATED = Path("runtime") / "generated"  # where the song pipeline writes its working mp3s
REQUIRED_CALLS = ("qwen", "acestep", "flux")  # each sample's log must show all three
CLIENT_LOGGER = "jukebox.clients"
_CALL = re.compile(r"^(?P<service>\w+) -> \S+?:(?P<port>\d+) (?P<status>\S+) (?P<ms>\d+)ms$")


@dataclass(frozen=True)
class SampleSpec:
    id: str
    vocal: bool
    style: str
    voice_tags: str | None
    mood: str
    theme: str
    duration_s: int
    seed: int


# Agreed on #4 (10/16; release lead OK 10/20). Titles and lyrics are not set here: Qwen writes them.
# voice_tags: lane B's suggestion for B2's unnaturally high default vocals; keep them only if they
# sound better by ear.
SPECS: tuple[SampleSpec, ...] = (
    SampleSpec("sample_01", False, "lo-fi hip hop, jazzy keys, vinyl crackle, soft drums", None,
               "mellow", "late-night study session", 60, 101),
    SampleSpec("sample_02", True, "upbeat pop, summery, bright synths, catchy chorus",
               "warm natural female vocals", "joyful", "road trip with friends", 60, 202),
    SampleSpec("sample_03", True, "cinematic folk, acoustic guitar, strings", "warm natural male vocals",
               "melancholy", "leaving a hometown", 60, 303),
)  # fmt: skip

MakeSong = Callable[[SampleSpec], Track]
MakeCover = Callable[[Track, Path], str]


@dataclass
class Call:
    service: str
    port: str
    status: str
    ms: int


@dataclass
class Entry:
    spec: SampleSpec
    track: Track
    calls: list[Call] = field(default_factory=list)
    seconds: float = 0.0
    song_prompt: list[dict[str, str]] | None = None  # the Qwen title/lyrics messages, when known
    acestep_tags: str | None = None  # the style tags ACE-Step received, when known


def song_style(spec: SampleSpec) -> str:
    """The style tags sent to the song pipeline: voice tags only for vocal songs."""
    return f"{spec.style}, {spec.voice_tags}" if spec.vocal and spec.voice_tags else spec.style


class SampleError(RuntimeError):
    """A sample could not be made. The message is the pipeline's plain-language (7.3) message."""


class PublishError(SampleError):
    """The new samples could not be swapped in. The message says what state samples/ is in."""


def default_make_song(spec: SampleSpec, *, library: Library | None = None) -> Track:
    """Run one spec through the app's song pipeline (B6) and return the generated Track.

    B6's generate_song() yields Job snapshots and never raises: the last one is either succeeded, with
    the track_id of the Track it added to `library`, or failed, with the 7.3 message. No cover job is
    started (its start_cover hook is left unset); C5 makes the sample covers itself.
    """
    from jukebox.services import songs

    generate_song = getattr(songs, "generate_song", None)
    if generate_song is None:
        raise NotImplementedError(
            "the song step needs B6's songs.generate_song() (jukebox/services/songs.py), not merged yet"
        )
    lib = library if library is not None else Library()  # its own library, not the app's
    job = None
    for job in generate_song(
        style=song_style(spec),
        mood=spec.mood,
        duration_s=spec.duration_s,
        vocal=spec.vocal,
        theme=spec.theme,
        seed=spec.seed,
        library=lib,
    ):
        print(f"    {spec.id}: {job.stage}")
    if job is None or job.status != "succeeded" or not job.track_id:
        raise SampleError(f"{spec.id}: {getattr(job, 'error', None) or 'the song pipeline did not finish'}")
    track = lib.get(job.track_id)
    if track is None:
        raise SampleError(f"{spec.id}: the song pipeline reported success but the song is not in the library")
    return track


DescribePrompt = Callable[[SampleSpec], list[dict[str, str]] | None]


def default_describe_prompt(spec: SampleSpec) -> list[dict[str, str]] | None:
    """The exact Qwen messages the song pipeline sends for this spec (B5's build_messages), for the log.
    None if B5 isn't available, so the log says the prompt wasn't recorded instead of failing."""
    try:
        from jukebox.services import songs

        return songs.build_messages(
            "lyrics" if spec.vocal else "title",
            style=song_style(spec),
            mood=spec.mood,
            theme=spec.theme,
            duration_s=spec.duration_s,
        )
    except (ImportError, AttributeError):
        return None


DescribeTags = Callable[[SampleSpec], str | None]


def default_describe_tags(spec: SampleSpec) -> str | None:
    """The style tags the song pipeline sends ACE-Step for this spec (B6's build_tags), for the log.
    None if B6 isn't available, so the log says the tags weren't recorded instead of failing."""
    try:
        from jukebox.services import songs

        return songs.build_tags(song_style(spec), spec.mood, vocal=spec.vocal)
    except (ImportError, AttributeError):
        return None


def default_make_cover(track: Track, dest: Path) -> str:
    from jukebox.services import art

    return art.render_cover(track, dest)


def build_samples(
    specs: Sequence[SampleSpec],
    *,
    root: Path = ROOT,
    make_song: MakeSong = default_make_song,
    make_cover: MakeCover = default_make_cover,
    describe_prompt: DescribePrompt | None = default_describe_prompt,
    describe_tags: DescribeTags | None = default_describe_tags,
    operator: str,
    commit: str,
    models: dict[str, str | None],
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="seconds"),
) -> list[Track]:
    """Build every sample in a staging folder, check it, then swap it into samples/."""
    root = Path(root)
    _recover(root)
    staging = root / STAGING
    shutil.rmtree(staging, ignore_errors=True)
    out = staging / "samples"
    try:
        entries = [_build_one(spec, root, out, make_song, make_cover, now) for spec in specs]
        for entry in entries:
            entry.song_prompt = describe_prompt(entry.spec) if describe_prompt else None
            entry.acestep_tags = describe_tags(entry.spec) if describe_tags else None
        for folder in ("audio", "covers"):
            (out / folder / ".gitkeep").write_bytes(b"")  # committed, so a run never deletes them
        _write_manifest(out / "manifest.json", [e.track for e in entries])
        (out / "GENERATION_LOG.md").write_text(
            render_log(entries, operator=operator, commit=commit, models=models, date=now()[:10]),
            encoding="utf-8",
            newline="\n",
        )
        Library(root=staging).load_manifest(out / "manifest.json")  # the app must be able to load it
        _publish(out, root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return [e.track for e in entries]


def _build_one(
    spec: SampleSpec,
    root: Path,
    out: Path,
    make_song: MakeSong,
    make_cover: MakeCover,
    now: Callable[[], str],
) -> Entry:
    calls: list[Call] = []
    handler = _CallRecorder(calls)
    logger = logging.getLogger(CLIENT_LOGGER)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    started = time.perf_counter()
    try:
        song = make_song(spec)
        audio_src = Library(root=root).resolve(song.audio_path)
        audio_rel = f"samples/audio/{spec.id}{audio_src.suffix.lower()}"
        cover_rel = f"samples/covers/{spec.id}.jpg"
        (out / "audio").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(audio_src, out.parent / audio_rel)
        working = audio_src.resolve()
        if (root / GENERATED).resolve() in working.parents:
            working.unlink(missing_ok=True)  # the pipeline's working copy; the sample is the copy
        prompt = make_cover(song, out.parent / cover_rel)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    missing = [SERVICE_NAMES[s] for s in REQUIRED_CALLS if not any(c.service == s for c in calls)]
    if missing:
        raise SampleError(
            f"{spec.id}: no {', '.join(missing)} call was recorded, so the log could not show its model and port"
        )
    track = Track(
        id=spec.id,
        title=song.title,
        style=song_style(spec),
        mood=spec.mood,
        theme=spec.theme,
        duration_s=int(spec.duration_s),
        vocal=spec.vocal,
        lyrics=song.lyrics if spec.vocal else None,
        audio_path=audio_rel,
        cover_path=cover_rel,
        cover_prompt=prompt,
        source="sample",
        seed=spec.seed,
        created_at=now(),
    )
    return Entry(spec=spec, track=track, calls=calls, seconds=time.perf_counter() - started)


class _CallRecorder(logging.Handler):
    """Keeps the shared client's one-line request log (service, port, status, ms); drops the host."""

    def __init__(self, calls: list[Call]) -> None:
        super().__init__(level=logging.INFO)
        self.calls = calls

    def emit(self, record: logging.LogRecord) -> None:
        match = _CALL.match(record.getMessage())
        if match:
            self.calls.append(Call(match["service"], match["port"], match["status"], int(match["ms"])))


def _write_manifest(path: Path, tracks: list[Track]) -> None:
    path.write_text(
        json.dumps([t.to_dict() for t in tracks], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _publish(out: Path, root: Path) -> None:
    """Swap the staged samples/ into place with two renames, never a copy, so a failure leaves samples/
    whole. On Windows a rename fails at once while a file inside is open (a sample playing).

    The marker file exists only between the first rename and the end of the swap, so only a run that
    really stopped mid-swap is ever recovered; without it, a backup folder is just a leftover.
    """
    target, previous, marker = root / "samples", root / PREVIOUS, root / SWAP_MARKER
    _recover(root)
    shutil.rmtree(previous, ignore_errors=True)  # a leftover (no marker): samples/ itself is whole
    if previous.exists():
        raise PublishError(f"could not clear {PREVIOUS.as_posix()}; close any open sample and run again.")
    previous.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("swap in progress\n", encoding="utf-8")
    if target.exists():
        try:
            os.replace(target, previous)
        except OSError as err:
            marker.unlink(missing_ok=True)
            raise PublishError(
                "samples/ is in use or could not be moved (is a sample open or playing?); close it and run "
                "again. samples/ was not changed."
            ) from err
    try:
        os.replace(out, target)
    except OSError as err:
        _recover(root)  # puts the old samples back, or says where they are
        raise PublishError("could not move the new samples into place; samples/ was kept as it was.") from err
    marker.unlink(missing_ok=True)
    shutil.rmtree(previous, ignore_errors=True)


def _recover(root: Path) -> None:
    """Finish a swap that stopped between the two renames (the marker is still there)."""
    target, previous, marker = root / "samples", root / PREVIOUS, root / SWAP_MARKER
    if not marker.exists():
        return
    if previous.exists() and target.exists():
        # samples/ came back some other way (for example `git checkout -- samples`); the backup may hold
        # the only copy of uncommitted samples, so keep it and let the person decide.
        raise PublishError(
            f"an earlier run was interrupted and the samples it replaced are in {PREVIOUS.as_posix()}; "
            "keep what you need from that folder, delete it, and run again. samples/ was not changed."
        )
    if previous.exists():
        try:
            os.replace(previous, target)
        except OSError as err:
            raise PublishError(
                f"the previous samples are in {PREVIOUS.as_posix()}; move that folder back to samples/ "
                "(or close any open sample and run again)."
            ) from err
        print(f"Put back the samples from an interrupted run (from {PREVIOUS.as_posix()}).")
    marker.unlink(missing_ok=True)


SERVICE_NAMES = {"qwen": "Qwen", "acestep": "ACE-Step", "flux": "FLUX", "chatterbox": "Chatterbox"}


def render_log(
    entries: Sequence[Entry], *, operator: str, commit: str, models: dict[str, str | None], date: str
) -> str:
    lines = [
        "# Sample generation log",
        "",
        "How the three bundled sample songs, their lyrics, and their covers were made (PROJECT.md 8.5, tasks C5",
        "and C6). Everything was generated with the class services only, through the app's own code path",
        "(`scripts/generate_samples.py`, the song pipeline and `jukebox/services/art.py`). No lyric, title,",
        "cover, or sound was written, drawn, or edited by a person. If a lyric needed changing, the sample was",
        "regenerated, never hand-edited.",
        "",
        f"- **Date:** {date}",
        f"- **Operator:** {operator}",
        "- **Command:** `python scripts/generate_samples.py`",
        f"- **Commit the script ran from:** `{commit}`",
        "- **Models (from the app's settings):**",
        f"  - Qwen3.6-35B-A3B, port 9001: `{models.get('qwen') or 'not set'}`",
        f"  - ACE-Step 1.5 XL Turbo, port 9007: `{models.get('acestep') or 'not set'}`",
        f"  - FLUX.2 klein 4B, port 9006: `{models.get('flux') or 'not set'}`",
        "- **Seeds:** sent and recorded below. ACE-Step did not reproduce audio from a fixed seed in B2's test,",
        "  so the committed files are the source of truth, not a regeneration.",
    ]
    for e in entries:
        t, s = e.track, e.spec
        kind = "vocal" if s.vocal else "instrumental"
        lines += [
            "",
            "---",
            "",
            f"## {t.id}: {t.title} ({kind})",
            "",
            "**Inputs**",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Style (sent to the song pipeline) | {t.style} |",
            "| ACE-Step tags (exactly as sent) | "
            + (e.acestep_tags or "not recorded (the song pipeline's tag builder was unavailable)")
            + " |",
            f"| Mood | {s.mood} |",
            f"| Theme | {s.theme} |",
            f"| Duration requested | {s.duration_s} s |",
            f"| Vocal | {'Yes' if s.vocal else 'No'} |",
            f"| Seed | {s.seed} |",
            "",
            f"**Calls** (from the app's request log; {e.seconds:.1f} s for this sample)",
            "",
            "| # | Service | Model | Port | Status | Time |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {i} | {SERVICE_NAMES.get(c.service, c.service)} | `{models.get(c.service) or 'not set'}` "
            f"| {c.port} | {c.status} | {c.ms} ms |"
            for i, c in enumerate(e.calls, 1)
        ]
        what = "title and lyrics" if s.vocal else "title"
        lines += ["", f"**Qwen song prompt** ({what}; system and user, exactly as sent)", ""]
        if e.song_prompt:
            for message in e.song_prompt:
                lines += [f"{message['role'].capitalize()}:", "", "```", message["content"], "```", ""]
        else:
            lines += [
                "Qwen song prompt not recorded (the song pipeline's prompt builder was unavailable).",
                "",
            ]
        lines += ["**Lyrics** (exactly as generated, unedited)", ""]
        lines += ["```", t.lyrics, "```"] if t.lyrics else ["Instrumental: no lyrics."]
        lines += [
            "",
            "**FLUX prompt** (written by Qwen, exactly as sent, including the fixed suffix)",
            "",
            "```",
            t.cover_prompt or "",
            "```",
            "",
            f"**Files:** `{t.audio_path}`, `{t.cover_path}`",
            "",
            "**Human checks** (fill in after listening and looking):",
            "",
            "- Listened by ______ on ______: plays to the end, matches style and mood, "
            + ("no vocals" if not s.vocal else "sings the lyrics")
            + ": Yes / No",
            "- Cover looked at by ______: matches mood and style; no text, letters, logos, or people: Yes / No",
        ]
        if s.vocal:
            lines += [
                "",
                "**Originality spot check** (a limited check, not proof): an exact-phrase web search on two",
                "distinctive lines.",
                "",
                "| Line searched | Search engine | Result |",
                "|---|---|---|",
                '| "" | | No match found / match: link |',
                '| "" | | |',
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    from jukebox.config import load_config

    config = load_config()
    models = {"qwen": config.qwen.model, "acestep": config.acestep.model, "flux": config.flux.model}
    commit = _git("rev-parse", "--short", "HEAD") or "unknown"
    operator = _git("config", "user.name") or "unknown"
    print(f"Generating {len(SPECS)} samples from commit {commit} (this takes about a minute)...")
    try:
        tracks = build_samples(SPECS, operator=operator, commit=commit, models=models)
    except ServiceError as err:
        print(f"Stopped: {user_message(err)} samples/ was not changed.")
        return 1
    except PublishError as err:
        print(f"Stopped: {err}")  # says itself what state samples/ is in
        return 1
    except (SampleError, NotImplementedError, LibraryError, OSError) as err:
        # Everything before the swap only touches the staging folder, so samples/ is as it was.
        print(f"Stopped: {err} samples/ was not changed.")
        return 1
    for t in tracks:
        print(f"  {t.id}: {t.title}  ({t.audio_path}, {t.cover_path})")
    print("Done. Now listen to each song, look at each cover, and fill in samples/GENERATION_LOG.md.")
    return 0


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
