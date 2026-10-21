"""Tests for scripts/generate_samples.py (task C5): the three bundled sample songs.

Qwen, ACE-Step and FLUX are faked: no class service is ever called. Each test builds into its own
temporary repository root, so the real samples/ folder is never touched.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sys
from pathlib import Path

import pytest
import respx

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
    assert len(list((tmp_path / "samples" / "audio").glob("*.mp3"))) == 3


# ---- wiring -----------------------------------------------------------------------------------


class FakeJob:
    def __init__(self, stage: str, status: str, track_id: str | None = None, error: str | None = None):
        self.stage, self.status, self.track_id, self.error = stage, status, track_id, error


def fake_songs_module(root: Path, *, fail: bool = False):
    """Stands in for B6's jukebox.services.songs: generate_song() yields Job snapshots and adds the Track
    to the library it is given (the interface @gunnaroc posted on #3)."""
    import types

    calls: list[dict] = []

    def generate_song(*, style, mood, duration_s, vocal, theme, seed, library):
        calls.append(dict(style=style, mood=mood, duration_s=duration_s, vocal=vocal, theme=theme, seed=seed))
        yield FakeJob("Queued", "queued")
        yield FakeJob("Writing lyrics…", "running")
        if fail:
            yield FakeJob(
                "Composing music…", "failed", error="The ACE-Step service took too long to respond."
            )
            return
        (root / "runtime" / "generated").mkdir(parents=True, exist_ok=True)
        (root / "runtime" / "generated" / "abc.mp3").write_bytes(MP3)
        library.add(
            Track(
                id="abc", title="Made by B6", style=style, mood=mood, theme=theme, duration_s=duration_s,
                vocal=vocal, lyrics="[verse]\nla" if vocal else None, audio_path="runtime/generated/abc.mp3",
                cover_path=None, cover_prompt=None, source="generated", seed=seed, created_at=NOW,
            )
        )  # fmt: skip
        yield FakeJob("Added to your library", "succeeded", track_id="abc")

    module = types.SimpleNamespace(generate_song=generate_song, calls=calls)
    return module


def test_the_song_step_runs_b6_to_the_end_and_returns_its_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jukebox.services as services

    fake = fake_songs_module(tmp_path)
    monkeypatch.setattr(services, "songs", fake, raising=False)
    monkeypatch.setitem(sys.modules, "jukebox.services.songs", fake)
    spec = gs.SPECS[1]
    track = gs.default_make_song(spec, library=Library(root=tmp_path))
    assert track.title == "Made by B6" and track.seed == spec.seed
    assert fake.calls == [
        dict(style=gs.song_style(spec), mood=spec.mood, duration_s=spec.duration_s, vocal=True,
             theme=spec.theme, seed=spec.seed)
    ]  # fmt: skip


def test_a_failed_song_stops_the_run_with_b6s_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jukebox.services as services

    fake = fake_songs_module(tmp_path, fail=True)
    monkeypatch.setattr(services, "songs", fake, raising=False)
    monkeypatch.setitem(sys.modules, "jukebox.services.songs", fake)
    with pytest.raises(gs.SampleError, match="took too long"):
        gs.default_make_song(gs.SPECS[0], library=Library(root=tmp_path))


def test_without_b6_the_song_step_says_so_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    import jukebox.services as services

    monkeypatch.setattr(services, "songs", types.SimpleNamespace(), raising=False)
    monkeypatch.setitem(sys.modules, "jukebox.services.songs", types.SimpleNamespace())
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


# ---- pre-push review follow-ups ---------------------------------------------------------------


def _snapshot(root: Path) -> dict:
    folder = root / "samples"
    return {p.relative_to(root): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def _fail_replace_from(monkeypatch: pytest.MonkeyPatch, source: Path) -> None:
    """Make the rename of `source` fail the way Windows does when a file inside it is open."""
    real = gs.os.replace

    def replace(src, dst):
        if Path(src).resolve() == source.resolve():
            raise PermissionError(32, "The process cannot access the file because it is being used")
        return real(src, dst)

    monkeypatch.setattr(gs.os, "replace", replace)


def test_a_sample_open_in_a_player_leaves_samples_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    _fail_replace_from(monkeypatch, tmp_path / "samples")
    with pytest.raises(gs.PublishError, match="in use"):
        build(tmp_path)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / gs.PREVIOUS).exists() and not (tmp_path / gs.SWAP_MARKER).exists()


def test_a_failed_move_of_the_new_samples_puts_the_old_ones_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    _fail_replace_from(monkeypatch, tmp_path / gs.STAGING / "samples")
    with pytest.raises(gs.PublishError, match="kept as it was"):
        build(tmp_path)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / gs.PREVIOUS).exists() and not (tmp_path / gs.SWAP_MARKER).exists()
    assert "interrupted run" not in capsys.readouterr().out  # it was this run, not an earlier one


def test_a_crash_right_after_the_marker_is_written_changes_nothing(tmp_path: Path) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    (tmp_path / gs.SWAP_MARKER).write_text("swap in progress\n", encoding="utf-8")  # then the crash
    build(tmp_path)
    assert _snapshot(tmp_path) == before  # the fakes make the same files again
    assert not (tmp_path / gs.SWAP_MARKER).exists() and not (tmp_path / gs.PREVIOUS).exists()


def test_a_marker_that_cannot_be_removed_after_the_swap_still_counts_as_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(tmp_path)
    real_unlink = Path.unlink

    def unlink(self, *args, **kwargs):
        if self.name == gs.SWAP_MARKER.name:
            raise PermissionError(32, "in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    tracks = build(tmp_path)  # no error: the new samples are in place
    assert [t.id for t in tracks] == ["sample_01", "sample_02", "sample_03"]
    assert not (tmp_path / gs.PREVIOUS).exists()
    assert (tmp_path / gs.SWAP_MARKER).exists()  # the stuck marker really was left behind
    monkeypatch.setattr(Path, "unlink", real_unlink)
    build(tmp_path)  # the next run clears it
    assert not (tmp_path / gs.SWAP_MARKER).exists()


def test_the_swap_never_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build(tmp_path)

    def no_copy(*args, **kwargs):
        raise AssertionError("the swap must rename, never copy and delete")

    monkeypatch.setattr(gs.shutil, "move", no_copy)
    monkeypatch.setattr(gs.shutil, "copytree", no_copy)
    build(tmp_path)


def _crash_between_the_renames(root: Path) -> None:
    """What a run that stopped between the two renames leaves: the marker, and the old samples only
    in the backup folder."""
    (root / gs.PREVIOUS).parent.mkdir(parents=True, exist_ok=True)
    (root / gs.SWAP_MARKER).write_text("swap in progress\n", encoding="utf-8")
    (root / "samples").rename(root / gs.PREVIOUS)


def test_a_run_that_stopped_mid_swap_gets_the_old_samples_back(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    _crash_between_the_renames(tmp_path)
    with pytest.raises(ServiceError):
        build(tmp_path, make_song=FakeSong(tmp_path, fail_on="sample_01"))
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / gs.PREVIOUS).exists() and not (tmp_path / gs.SWAP_MARKER).exists()
    assert "Put back the samples from an interrupted run" in capsys.readouterr().out


def test_a_leftover_backup_is_never_restored_without_the_marker(tmp_path: Path) -> None:
    """A half-deleted backup (antivirus stopped the cleanup) must never come back after the user
    deleted samples/ on purpose."""
    build(tmp_path)
    (tmp_path / gs.PREVIOUS / "audio").mkdir(parents=True)
    (tmp_path / gs.PREVIOUS / "audio" / "sample_01.mp3").write_bytes(b"partial")
    import shutil

    shutil.rmtree(tmp_path / "samples")
    with pytest.raises(ServiceError):
        build(tmp_path, make_song=FakeSong(tmp_path, fail_on="sample_01"))
    assert not (tmp_path / "samples").exists()


def test_samples_recreated_after_an_interrupted_run_never_cost_the_backup(tmp_path: Path) -> None:
    """After a crash between the renames, `git checkout -- samples` brings back samples/; the backup may
    hold the only copy of uncommitted samples, so the run stops and keeps it."""
    build(tmp_path)
    before = _snapshot(tmp_path)
    _crash_between_the_renames(tmp_path)
    (tmp_path / "samples" / "audio").mkdir(parents=True)  # the user restored samples/ by hand
    (tmp_path / "samples" / "audio" / "mine.mp3").write_bytes(b"restored by hand")
    with pytest.raises(gs.PublishError, match="interrupted"):
        build(tmp_path)
    backup = tmp_path / gs.PREVIOUS
    kept = {p.relative_to(backup): p.read_bytes() for p in backup.rglob("*") if p.is_file()}
    assert kept == {path.relative_to("samples"): data for path, data in before.items()}
    assert _snapshot(tmp_path) == {Path("samples/audio/mine.mp3"): b"restored by hand"}
    assert (tmp_path / gs.SWAP_MARKER).exists()


def test_a_failed_restore_keeps_the_backup_and_says_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    real = gs.os.replace
    staged = (tmp_path / gs.STAGING / "samples").resolve()
    backup = (tmp_path / gs.PREVIOUS).resolve()

    def replace(src, dst):
        if Path(src).resolve() in (staged, backup):
            raise PermissionError(32, "in use")
        return real(src, dst)

    monkeypatch.setattr(gs.os, "replace", replace)
    with pytest.raises(gs.PublishError, match="previous samples are in"):
        build(tmp_path)
    assert (tmp_path / gs.PREVIOUS).is_dir() and (tmp_path / gs.SWAP_MARKER).exists()
    monkeypatch.setattr(gs.os, "replace", real)
    with pytest.raises(ServiceError):  # the next run puts them back first, even if it then fails
        build(tmp_path, make_song=FakeSong(tmp_path, fail_on="sample_01"))
    assert _snapshot(tmp_path) == before


def test_a_backup_that_cannot_be_cleared_stops_before_touching_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(tmp_path)
    before = _snapshot(tmp_path)
    (tmp_path / gs.PREVIOUS).mkdir(parents=True)
    (tmp_path / gs.PREVIOUS / "stuck.mp3").write_bytes(b"locked")
    real = gs.shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if Path(path).resolve() == (tmp_path / gs.PREVIOUS).resolve():
            return None  # a locked file: ignore_errors leaves it in place
        return real(path, *args, **kwargs)

    monkeypatch.setattr(gs.shutil, "rmtree", rmtree)
    with pytest.raises(gs.PublishError, match="could not clear"):
        build(tmp_path)
    assert _snapshot(tmp_path) == before


def test_only_the_pipelines_generated_folder_is_ever_cleaned(tmp_path: Path) -> None:
    class SongOutsideGenerated(FakeSong):
        def __call__(self, spec: gs.SampleSpec) -> Track:
            track = super().__call__(spec)
            other = self.root / "runtime" / "uploads" / f"{spec.id}.mp3"
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_bytes(MP3)
            return dataclasses.replace(track, audio_path=f"runtime/uploads/{spec.id}.mp3")

    build(tmp_path, make_song=SongOutsideGenerated(tmp_path))
    assert len(list((tmp_path / "runtime" / "uploads").glob("*.mp3"))) == 3


def test_the_committed_gitkeep_files_survive_a_run(tmp_path: Path) -> None:
    for folder in ("audio", "covers"):
        (tmp_path / "samples" / folder).mkdir(parents=True)
        (tmp_path / "samples" / folder / ".gitkeep").write_bytes(b"")
    build(tmp_path)
    assert (tmp_path / "samples" / "audio" / ".gitkeep").is_file()
    assert (tmp_path / "samples" / "covers" / ".gitkeep").is_file()


def test_the_pipelines_working_copy_of_the_audio_is_removed(tmp_path: Path) -> None:
    build(tmp_path)
    assert list((tmp_path / "runtime" / "generated").glob("*.mp3")) == []


def test_a_sample_with_no_recorded_calls_stops_the_run(tmp_path: Path) -> None:
    def silent_cover(track: Track, dest: Path) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(JPEG)
        return "A cover"

    logger = logging.getLogger("jukebox.clients")
    logger.disabled = True  # the fake song's request lines never reach the recorder
    try:
        with pytest.raises(gs.SampleError, match="no Qwen, ACE-Step, FLUX call was recorded"):
            build(tmp_path, make_cover=silent_cover)
    finally:
        logger.disabled = False
    assert not (tmp_path / "samples").exists()


def test_a_sample_missing_its_flux_call_stops_the_run(tmp_path: Path) -> None:
    def cover_without_flux(track: Track, dest: Path) -> str:
        logging.getLogger("jukebox.clients").info("qwen -> %s:9001 200 900ms", HOST)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(JPEG)
        return "A cover"

    with pytest.raises(gs.SampleError, match="sample_01: no FLUX call was recorded"):
        build(tmp_path, make_cover=cover_without_flux)


def test_the_log_shows_the_acestep_tags_exactly_as_sent(tmp_path: Path) -> None:
    build(tmp_path, describe_tags=lambda spec: f"{gs.song_style(spec)}, {spec.mood}, sent-as-is")
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    expected = "lo-fi hip hop, jazzy keys, vinyl crackle, soft drums, mellow, sent-as-is"
    assert f"| ACE-Step tags (exactly as sent) | {expected} |" in log


def test_the_log_says_so_when_the_acestep_tags_are_not_available(tmp_path: Path) -> None:
    build(tmp_path, describe_tags=None)
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert "| ACE-Step tags (exactly as sent) | not recorded" in log


def test_the_operator_is_not_written_as_a_github_handle(tmp_path: Path) -> None:
    gs.build_samples(
        gs.SPECS, root=tmp_path, make_song=FakeSong(tmp_path), make_cover=fake_cover,
        operator="Felipe Example", commit=COMMIT, models=MODELS, now=lambda: NOW,
    )  # fmt: skip
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert "- **Operator:** Felipe Example" in log and "@Felipe" not in log


# Real shared clients (respx), so a change to the client's request log can't silently empty the log.
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}


@pytest.fixture
def cfg(tmp_path: Path):
    from jukebox.config import load_config

    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    for service, model in MODELS.items():
        env[f"{service.upper()}_MODEL"] = model
    return load_config(env=env, env_file=tmp_path / "missing-file")


@respx.mock
def test_real_client_calls_are_logged_with_model_and_port_never_host_or_key(tmp_path: Path, cfg) -> None:
    from jukebox.clients.base import ServiceClient

    for port in PORTS.values():
        respx.post(f"http://{HOST}:{port}/v1/test").respond(200, json={"ok": True})
    clients = {s: ServiceClient(s, cfg, sleep=lambda _s: None) for s in ("qwen", "acestep", "flux")}
    fake_song = FakeSong(tmp_path)

    def song(spec: gs.SampleSpec) -> Track:
        clients["qwen"].request("POST", "/v1/test", json={})
        clients["acestep"].request("POST", "/v1/test", json={}, retry=False)
        logger = logging.getLogger("jukebox.clients")
        logger.disabled = True  # keep only the real client's lines, not the fake's hand-written ones
        try:
            return fake_song(spec)
        finally:
            logger.disabled = False

    def cover(track: Track, dest: Path) -> str:
        clients["qwen"].request("POST", "/v1/test", json={})
        clients["flux"].request("POST", "/v1/test", json={})
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(JPEG)
        return "A cover, square album cover, no text, no letters, no logos, no real people"

    try:
        build(tmp_path, make_song=song, make_cover=cover)
    finally:
        for c in clients.values():
            c.close()
    log = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    assert f"| 2 | ACE-Step | `{MODELS['acestep']}` | 9007 | 200 |" in log
    assert f"| 4 | FLUX | `{MODELS['flux']}` | 9006 | 200 |" in log
    assert log.count(f"| Qwen | `{MODELS['qwen']}` | 9001 | 200 |") == 6  # 2 per sample
    assert HOST not in log and KEY not in log


@pytest.mark.parametrize(
    "error, says",
    [
        (NotImplementedError("the song step needs B6's songs.generate_song()"), "needs B6"),
        (OSError("disk full"), "disk full"),
        (gs.SampleError("sample_02: The ACE-Step service took too long to respond."), "took too long"),
    ],
)
def test_main_stops_with_a_clear_line_not_a_traceback(
    error: Exception, says: str, cfg, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import jukebox.config as config

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(gs, "build_samples", fail)
    assert gs.main() == 1
    out = capsys.readouterr().out
    assert "Stopped:" in out and says in out and "samples/ was not changed." in out


def test_main_prints_a_publish_problem_as_is(
    cfg, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import jukebox.config as config

    def fail(*args, **kwargs):
        raise gs.PublishError("samples/ is in use (is a sample open or playing?); close it and run again.")

    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(gs, "build_samples", fail)
    assert gs.main() == 1
    out = capsys.readouterr().out
    assert "Stopped: samples/ is in use" in out and "was not changed" not in out


# ---- C6 dress rehearsal: the real B6 pipeline and C4 cover code, only the three calls faked ------


def test_the_whole_run_through_the_real_song_pipeline_and_cover_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs only once B6 (#36) is on main. Proves C6 is one command: the script, B6's generate_song(),
    B5's prompts and parser, and C4's render_cover() work together. Only qwen.chat, acestep.generate_music
    and flux.generate_image are replaced, each logging its call the way the shared client does."""
    from jukebox.services import songs

    if not hasattr(songs, "generate_song"):
        pytest.skip("needs B6's songs.generate_song() (#36)")
    from jukebox.clients import acestep, flux, qwen

    log = logging.getLogger("jukebox.clients")
    sent_tags: list[str] = []

    def fake_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        log.info("qwen -> %s:9001 200 700ms", HOST)
        if "album cover" in messages[0]["content"]:
            return "A quiet road at dusk, warm light"
        lyrics = "[verse]\nWheels on warm asphalt\nWindows open wide\n[chorus]\nWe sing all the way home"
        return json.dumps({"title": "Open Road", "lyrics": lyrics})

    def fake_music(*, tags: str, lyrics: str | None, duration_s: int, seed: int | None = None):
        log.info("acestep -> %s:9007 200 2600ms", HOST)
        sent_tags.append(tags)
        return MP3, "mp3"

    def fake_image(prompt: str, **kwargs) -> bytes:
        log.info("flux -> %s:9006 200 2400ms", HOST)
        return JPEG

    monkeypatch.setattr(qwen, "chat", fake_chat)
    monkeypatch.setattr(acestep, "generate_music", fake_music)
    monkeypatch.setattr(flux, "generate_image", fake_image)
    library = Library(root=tmp_path)
    tracks = gs.build_samples(
        gs.SPECS,
        root=tmp_path,
        make_song=lambda spec: gs.default_make_song(spec, library=library),
        operator="felcervino",
        commit=COMMIT,
        models=MODELS,
        now=lambda: NOW,
    )
    assert [t.id for t in tracks] == ["sample_01", "sample_02", "sample_03"]
    assert all(t.title == "Open Road" for t in tracks)
    assert tracks[0].lyrics is None and "We sing all the way home" in tracks[1].lyrics
    assert Library(root=tmp_path).load_manifest(tmp_path / "samples" / "manifest.json") == 3
    log_text = (tmp_path / "samples" / "GENERATION_LOG.md").read_text(encoding="utf-8")
    for tags in sent_tags:  # the log shows exactly what ACE-Step received
        assert f"| ACE-Step tags (exactly as sent) | {tags} |" in log_text
    assert "not recorded" not in log_text  # B5's song prompt and B6's tags were both found
    assert "A quiet road at dusk, warm light, square album cover" in log_text
    assert HOST not in log_text
    assert list((tmp_path / "runtime" / "generated").glob("*.mp3")) == []
