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
from jukebox.library import Library  # noqa: E402
from jukebox.models import Track  # noqa: E402

STAGING = Path("runtime") / "tmp" / "samples-staging"
PREVIOUS = Path("runtime") / "tmp" / "samples-previous"
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


def song_style(spec: SampleSpec) -> str:
    """The style tags sent to the song pipeline: voice tags only for vocal songs."""
    return f"{spec.style}, {spec.voice_tags}" if spec.vocal and spec.voice_tags else spec.style


def default_make_song(spec: SampleSpec) -> Track:
    """Run one spec through the app's song pipeline (B6) and return the generated Track."""
    raise NotImplementedError(
        "the song step waits for B6 (jukebox/services/songs.py); wire it here once B6 is merged"
    )


def default_make_cover(track: Track, dest: Path) -> str:
    from jukebox.services import art

    return art.render_cover(track, dest)


def build_samples(
    specs: Sequence[SampleSpec],
    *,
    root: Path = ROOT,
    make_song: MakeSong = default_make_song,
    make_cover: MakeCover = default_make_cover,
    operator: str,
    commit: str,
    models: dict[str, str | None],
    now: Callable[[], str] = lambda: datetime.now(UTC).isoformat(timespec="seconds"),
) -> list[Track]:
    """Build every sample in a staging folder, check it, then swap it into samples/."""
    root = Path(root)
    staging = root / STAGING
    shutil.rmtree(staging, ignore_errors=True)
    out = staging / "samples"
    try:
        entries = [_build_one(spec, root, out, make_song, make_cover, now) for spec in specs]
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
        audio_src = root / song.audio_path.replace("\\", "/")
        audio_rel = f"samples/audio/{spec.id}{audio_src.suffix.lower()}"
        cover_rel = f"samples/covers/{spec.id}.jpg"
        (out / "audio").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(audio_src, out.parent / audio_rel)
        prompt = make_cover(song, out.parent / cover_rel)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
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
    """Swap the staged samples/ into place; restore the previous one if anything goes wrong."""
    target = root / "samples"
    previous = root / PREVIOUS
    shutil.rmtree(previous, ignore_errors=True)
    if target.exists():
        previous.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(previous))
    try:
        shutil.move(str(out), str(target))
    except BaseException:
        if previous.exists() and not target.exists():
            shutil.move(str(previous), str(target))
        raise
    shutil.rmtree(previous, ignore_errors=True)


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
        f"- **Operator:** @{operator}",
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
            f"| Style tags | {t.style} |",
            f"| Mood | {s.mood} |",
            f"| Theme | {s.theme} |",
            f"| Duration requested | {s.duration_s} s |",
            f"| Vocal | {'Yes' if s.vocal else 'No'} |",
            f"| Seed | {s.seed} |",
            "",
            f"**Calls** (from the app's request log; {e.seconds:.1f} s for this sample)",
            "",
            "| # | Service | Port | Status | Time |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {i} | {SERVICE_NAMES.get(c.service, c.service)} | {c.port} | {c.status} | {c.ms} ms |"
            for i, c in enumerate(e.calls, 1)
        ] or ["| | (no calls recorded) | | | |"]
        lines += ["", "**Lyrics** (exactly as generated, unedited)", ""]
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
