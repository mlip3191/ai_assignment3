"""Tests for scripts/generate_samples.py (task C5): the three bundled sample songs.

Qwen, ACE-Step and FLUX are faked: no class service is ever called. Each test builds into its own
temporary repository root, so the real samples/ folder is never touched.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_samples as gs  # noqa: E402

from jukebox.errors import ServiceError  # noqa: E402
from jukebox.library import Library  # noqa: E402
from jukebox.models import Track  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
JPEG = b"\xff\xd8\xff\xe0" + b"fake cover"
MP3 = b"ID3" + b"fake audio"
COMMIT = "abc1234"
NOW = "2026-10-20T12:00:00+00:00"
MODELS = {
    "qwen": "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
    "acestep": "ACE-Step/acestep-v15-xl-turbo",
    "flux": "black-forest-labs/FLUX.2-klein-4B",
}


class FakeSong:
    """Stands in for the B6 song pipeline: writes an MP3 under runtime/generated and logs like the
    shared client does (`service -> host:port status ms`)."""

    def __init__(self, root: Path, fail_on: str | None = None) -> None:
        self.root = root
        self.fail_on = fail_on
        self.specs: list[gs.SampleSpec] = []

    def __call__(self, spec: gs.SampleSpec) -> Track:
        self.specs.append(spec)
        log = logging.getLogger("jukebox.clients")
        log.info("qwen -> %s:9001 200 812ms", HOST)
        if spec.id == self.fail_on:
            raise ServiceError("acestep", "timeout", "slow")
        log.info("acestep -> %s:9007 200 2650ms", HOST)
        folder = self.root / "runtime" / "generated"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"gen-{spec.id}.mp3").write_bytes(MP3)
        return Track(
            id=f"gen-{spec.id}",
            title=f"Title of {spec.id}",
            style=gs.song_style(spec),
            mood=spec.mood,
            theme=spec.theme,
            duration_s=spec.duration_s,
            vocal=spec.vocal,
            lyrics=f"[verse]\nWords for {spec.id}\n[chorus]\nMore words" if spec.vocal else None,
            audio_path=f"runtime/generated/gen-{spec.id}.mp3",
            cover_path=None,
            cover_prompt=None,
            source="generated",
            seed=spec.seed,
            created_at=NOW,
        )


def fake_cover(track: Track, dest: Path) -> str:
    logging.getLogger("jukebox.clients").info("qwen -> %s:9001 200 900ms", HOST)
    logging.getLogger("jukebox.clients").info("flux -> %s:9006 200 2400ms", HOST)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(JPEG)
    return f"A cover for {track.title}, square album cover, no text, no letters, no logos, no real people"


def build(root: Path, **kw) -> list[Track]:
    kw.setdefault("make_song", FakeSong(root))
    kw.setdefault("make_cover", fake_cover)
    return gs.build_samples(
        gs.SPECS, root=root, operator="felcervino", commit=COMMIT, models=MODELS, now=lambda: NOW, **kw
    )


# ---- the specs agreed on #4 -------------------------------------------------------------------


def test_three_specs_one_instrumental_two_vocal_about_a_minute_each() -> None:
    assert [s.id for s in gs.SPECS] == ["sample_01", "sample_02", "sample_03"]
    assert [s.vocal for s in gs.SPECS] == [False, True, True]
    assert all(isinstance(s.duration_s, int) and s.duration_s == 60 for s in gs.SPECS)
    assert len({s.seed for s in gs.SPECS}) == 3


def test_specs_name_no_artists_or_imitation() -> None:
    for spec in gs.SPECS:
        text = f"{spec.style} {spec.voice_tags or ''} {spec.theme}".lower()
        assert "in the style of" not in text and " like " not in f" {text} "


def test_voice_tags_are_added_only_for_vocal_songs() -> None:
    by_id = {s.id: s for s in gs.SPECS}
    assert gs.song_style(by_id["sample_01"]) == by_id["sample_01"].style
    assert gs.song_style(by_id["sample_02"]).endswith(by_id["sample_02"].voice_tags)


# ---- building the samples ---------------------------------------------------------------------


def test_files_land_in_samples_with_sample_ids(tmp_path: Path) -> None:
    build(tmp_path)
    for n in (1, 2, 3):
        assert (tmp_path / "samples" / "audio" / f"sample_0{n}.mp3").read_bytes() == MP3
        assert (tmp_path / "samples" / "covers" / f"sample_0{n}.jpg").read_bytes() == JPEG


def test_manifest_loads_in_the_app_library(tmp_path: Path) -> None:
    build(tmp_path)
    library = Library(root=tmp_path)
    assert library.load_manifest(tmp_path / "samples" / "manifest.json") == 3
    for track in library.list():
        assert track.source == "sample"
        assert track.audio_path == f"samples/audio/{track.id}.mp3"
        assert track.cover_path == f"samples/covers/{track.id}.jpg"
        assert isinstance(track.duration_s, int)
        assert track.cover_prompt and track.cover_prompt.endswith("no real people")


def test_manifest_uses_forward_slashes_and_utf8(tmp_path: Path) -> None:
    build(tmp_path)
    entries = json.loads((tmp_path / "samples" / "manifest.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in entries] == ["sample_01", "sample_02", "sample_03"]
    for e in entries:
        assert "\\" not in e["audio_path"] and "\\" not in e["cover_path"]


def test_titles_and_lyrics_come_from_the_song_pipeline(tmp_path: Path) -> None:
    tracks = build(tmp_path)
    assert tracks[0].title == "Title of sample_01" and tracks[0].lyrics is None
    assert "Words for sample_02" in tracks[1].lyrics


def test_the_song_pipeline_gets_each_spec_with_its_seed(tmp_path: Path) -> None:
    song = FakeSong(tmp_path)
    build(tmp_path, make_song=song)
    assert [s.seed for s in song.specs] == [s.seed for s in gs.SPECS]


# ---- the generation log -----------------------------------------------------------------------


def test_log_records_inputs_prompts_lyrics_models_and_ports(tmp_path: Path) -> None:
    build(tmp_path)
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    for needle in ("felcervino", COMMIT, "2026-10-20", *MODELS.values()):
        assert needle in log
    for spec in gs.SPECS:
        assert spec.id in log and spec.mood in log and str(spec.seed) in log
    assert "Words for sample_02\n[chorus]\nMore words" in log
    assert "A cover for Title of sample_03" in log
    for port in ("9001", "9006", "9007"):
        assert port in log
    assert "Listened by" in log and "Originality spot check" in log


def test_log_never_contains_the_host_or_a_key(tmp_path: Path) -> None:
    build(tmp_path)
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert HOST not in log and KEY not in log


# ---- all or nothing ---------------------------------------------------------------------------


def test_a_failed_sample_leaves_existing_samples_untouched(tmp_path: Path) -> None:
    build(tmp_path)
    before = {
        p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "samples").rglob("*") if p.is_file()
    }
    with pytest.raises(ServiceError):
        build(tmp_path, make_song=FakeSong(tmp_path, fail_on="sample_02"))
    after = {
        p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "samples").rglob("*") if p.is_file()
    }
    assert after == before
    assert not (tmp_path / gs.STAGING).exists()


def test_a_failed_first_run_creates_no_samples_folder(tmp_path: Path) -> None:
    with pytest.raises(ServiceError):
        build(tmp_path, make_song=FakeSong(tmp_path, fail_on="sample_01"))
    assert not (tmp_path / "samples").exists()


def test_a_rerun_replaces_the_previous_samples(tmp_path: Path) -> None:
    build(tmp_path)
    (tmp_path / "samples" / "audio" / "stale.mp3").write_bytes(b"old")
    build(tmp_path)
    assert not (tmp_path / "samples" / "audio" / "stale.mp3").exists()
    assert len(list((tmp_path / "samples" / "audio").iterdir())) == 3


# ---- wiring -----------------------------------------------------------------------------------


def test_default_song_step_says_clearly_that_it_waits_for_b6() -> None:
    with pytest.raises(NotImplementedError, match="B6"):
        gs.default_make_song(gs.SPECS[0])


def test_the_script_uses_no_client_directly() -> None:
    source = (ROOT / "scripts" / "generate_samples.py").read_text(encoding="utf-8")
    assert "jukebox.clients" not in source.replace('"jukebox.clients"', "")


# ---- the Qwen title/lyrics prompt in the log (B5's build_messages) ------------------------------


def fake_prompt(spec: gs.SampleSpec) -> list[dict]:
    kind = "lyrics" if spec.vocal else "title"
    return [
        {"role": "system", "content": f"You write the {kind} for one new, original song."},
        {"role": "user", "content": f"Style: {gs.song_style(spec)}\nMood: {spec.mood}"},
    ]


def test_log_records_the_exact_qwen_song_prompt_when_available(tmp_path: Path) -> None:
    build(tmp_path, describe_prompt=fake_prompt)
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert "You write the title for one new, original song." in log
    assert "You write the lyrics for one new, original song." in log
    assert "Style: upbeat pop, summery, bright synths, catchy chorus, warm natural female vocals" in log


def test_log_says_so_when_the_song_prompt_is_not_available(tmp_path: Path) -> None:
    build(tmp_path, describe_prompt=None)
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert "song prompt not recorded" in log
