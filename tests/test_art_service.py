"""Tests for the cover job in jukebox/services/art.py (task C4).

Qwen and FLUX are faked: no class service is ever called. Each test gets its own temporary
repository root and library, so files land in tmp_path, never in the real runtime/ folder.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.errors import ServiceError  # noqa: E402
from jukebox.jobs import JobStore  # noqa: E402
from jukebox.library import Library, LibraryError  # noqa: E402
from jukebox.services import art  # noqa: E402

IMAGE = b"\xff\xd8\xff\xe0" + b"fake jpeg body"
SUFFIX = "square album cover, no text, no letters, no logos, no real people"


def fake_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    title = next(line for line in messages[-1]["content"].splitlines() if line.startswith("Title: "))
    return f"A quiet scene for {title[7:]}"


class FakeFlux:
    def __init__(self, fail: ServiceError | None = None) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    def __call__(self, prompt: str, *, seed: int | None = None) -> bytes:
        self.calls.append({"prompt": prompt, "seed": seed})
        if self.fail:
            raise self.fail
        return IMAGE


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "runtime" / "generated").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def library(root: Path, make_track) -> Library:
    lib = Library(root=root)
    for track_id in ("t1", "t2", "t3"):
        audio = root / "runtime" / "generated" / f"{track_id}.mp3"
        audio.write_bytes(b"ID3 fake audio")
        lib.add(
            make_track(id=track_id, title=f"Song {track_id}", audio_path=f"runtime/generated/{track_id}.mp3")
        )
    return lib


def cover(track_id: str, library: Library, root: Path, **kw):
    kw.setdefault("chat", fake_chat)
    kw.setdefault("generate", FakeFlux())
    return art.make_cover(track_id, library=library, root=root, **kw)


# ---- making a cover ---------------------------------------------------------------------------


def test_cover_is_saved_as_runtime_generated_track_id_png(library: Library, root: Path) -> None:
    cover("t2", library, root)
    assert (root / "runtime" / "generated" / "t2.jpg").read_bytes() == IMAGE


def test_track_gets_its_cover_path_and_the_exact_flux_prompt(library: Library, root: Path) -> None:
    flux = FakeFlux()
    updated = cover("t2", library, root, generate=flux)
    assert updated.cover_path == "runtime/generated/t2.jpg"
    assert updated.cover_prompt == flux.calls[0]["prompt"]
    assert updated.cover_prompt == f"A quiet scene for Song t2, {SUFFIX}"
    assert library.get("t2").cover_path == "runtime/generated/t2.jpg"


def test_the_tracks_seed_is_passed_to_flux(library: Library, root: Path) -> None:
    flux = FakeFlux()
    cover("t1", library, root, generate=flux)
    assert flux.calls[0]["seed"] == library.get("t1").seed


def test_cover_for_looks_up_by_track_id_not_position(library: Library, root: Path) -> None:
    cover("t2", library, root)
    placeholder = art.placeholder_path()
    assert art.cover_for("t2", library=library) == root / "runtime" / "generated" / "t2.jpg"
    assert art.cover_for("t1", library=library) == placeholder
    assert art.cover_for("t3", library=library) == placeholder


def test_each_track_keeps_its_own_cover_after_several_generations(library: Library, root: Path) -> None:
    for track_id in ("t3", "t1", "t2"):
        cover(track_id, library, root)
    for track_id in ("t1", "t2", "t3"):
        assert art.cover_for(track_id, library=library).name == f"{track_id}.jpg"
        assert f"Song {track_id}," in library.get(track_id).cover_prompt


def test_render_cover_writes_to_any_destination_for_the_samples(library: Library, root: Path) -> None:
    dest = root / "samples" / "covers" / "sample_01.jpg"
    prompt = art.render_cover(library.get("t1"), dest, chat=fake_chat, generate=FakeFlux())
    assert dest.read_bytes() == IMAGE
    assert prompt.endswith(SUFFIX)


# ---- failures keep the song playable ----------------------------------------------------------


def test_flux_failure_keeps_the_song_and_shows_the_placeholder(library: Library, root: Path) -> None:
    with pytest.raises(ServiceError) as exc:
        cover("t1", library, root, generate=FakeFlux(fail=ServiceError("flux", "timeout", "slow")))
    assert (exc.value.service, exc.value.kind) == ("flux", "timeout")
    track = library.get("t1")
    assert track is not None and track.cover_path is None
    assert not (root / "runtime" / "generated" / "t1.jpg").exists()
    assert art.cover_for("t1", library=library) == art.placeholder_path()


def test_qwen_failure_also_keeps_the_song(library: Library, root: Path) -> None:
    def broken_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        raise ServiceError("qwen", "unavailable", "down")

    flux = FakeFlux()
    with pytest.raises(ServiceError) as exc:
        cover("t1", library, root, chat=broken_chat, generate=flux)
    assert exc.value.service == "qwen"
    assert flux.calls == []
    assert library.get("t1").cover_path is None


def test_retry_cover_replaces_the_placeholder(library: Library, root: Path) -> None:
    with pytest.raises(ServiceError):
        cover("t1", library, root, generate=FakeFlux(fail=ServiceError("flux", "unavailable", "down")))
    updated = art.retry_cover("t1", library=library, root=root, chat=fake_chat, generate=FakeFlux())
    assert updated.cover_path == "runtime/generated/t1.jpg"
    assert art.cover_for("t1", library=library).name == "t1.jpg"


def test_a_cover_file_that_disappeared_falls_back_to_the_placeholder(library: Library, root: Path) -> None:
    cover("t1", library, root)
    (root / "runtime" / "generated" / "t1.jpg").unlink()
    assert art.cover_for("t1", library=library) == art.placeholder_path()


def test_a_cover_path_written_with_backslashes_still_resolves(library: Library, root: Path) -> None:
    (root / "runtime" / "generated" / "t3.jpg").write_bytes(IMAGE)
    library.attach_cover("t3", "runtime\\generated\\t3.jpg", "p")
    assert art.cover_for("t3", library=library) == root / "runtime" / "generated" / "t3.jpg"


def test_unknown_track_shows_the_placeholder_and_cannot_get_a_cover(library: Library, root: Path) -> None:
    assert art.cover_for("nope", library=library) == art.placeholder_path()
    with pytest.raises(LibraryError):
        cover("nope", library, root)


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "a\\b", "", "con.png"])
def test_unsafe_track_ids_never_become_file_names(library: Library, root: Path, bad_id: str) -> None:
    with pytest.raises(ValueError):
        cover(bad_id, library, root)


# ---- job status (R5) --------------------------------------------------------------------------


def test_job_shows_painting_cover_then_succeeds(library: Library, root: Path) -> None:
    jobs = JobStore()
    cover("t1", library, root, jobs=jobs)
    (job,) = jobs.list()
    assert (job.kind, job.status, job.stage, job.track_id) == ("cover", "succeeded", art.COVER_STAGE, "t1")


def test_failed_job_carries_the_plain_language_message(library: Library, root: Path) -> None:
    jobs = JobStore()
    with pytest.raises(ServiceError):
        cover("t1", library, root, jobs=jobs, generate=FakeFlux(fail=ServiceError("flux", "timeout", "x")))
    (job,) = jobs.list()
    assert job.status == "failed"
    assert job.error and "FLUX" in job.error and "x" not in job.error.split()


# ---- the placeholder and the model rules ------------------------------------------------------


def test_placeholder_is_a_committed_square_png() -> None:
    path = art.placeholder_path()
    assert path == ROOT / "jukebox" / "assets" / "placeholder_cover.png"
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height


def test_the_cover_service_uses_only_the_qwen_and_flux_clients() -> None:
    source = (ROOT / "jukebox" / "services" / "art.py").read_text(encoding="utf-8")
    for other in ("acestep", "chatterbox"):
        assert other not in source


# ---- robustness ---------------------------------------------------------------------------------


def test_an_unexpected_error_still_finishes_the_job(library: Library, root: Path) -> None:
    def exploding_flux(prompt: str, *, seed: int | None = None) -> bytes:
        raise RuntimeError("something odd")

    jobs = JobStore()
    with pytest.raises(RuntimeError):
        cover("t1", library, root, jobs=jobs, generate=exploding_flux)
    (job,) = jobs.list()
    assert job.status == "failed"
    assert job.error and "something odd" not in job.error
    assert library.get("t1").cover_path is None


def test_a_save_failure_finishes_the_job_and_keeps_the_song(
    library: Library, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(dest: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(art, "_write_atomically", disk_full)
    jobs = JobStore()
    with pytest.raises(OSError):
        cover("t1", library, root, jobs=jobs)
    assert jobs.list()[0].status == "failed"
    assert art.cover_for("t1", library=library) == art.placeholder_path()


def test_two_covers_for_the_same_track_at_once_do_not_collide(library: Library, root: Path) -> None:
    import threading

    barrier = threading.Barrier(2)

    def slow_flux(prompt: str, *, seed: int | None = None) -> bytes:
        barrier.wait(timeout=5)
        return IMAGE

    errors: list[BaseException] = []

    def run() -> None:
        try:
            cover("t1", library, root, generate=slow_flux)
        except BaseException as exc:  # noqa: BLE001 - collected for the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    folder = root / "runtime" / "generated"
    assert (folder / "t1.jpg").read_bytes() == IMAGE
    assert [p.name for p in folder.iterdir() if p.suffix == ".tmp"] == []


def test_a_briefly_locked_cover_file_is_retried(
    library: Library, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = art.os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(13, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(art.os, "replace", flaky_replace)
    monkeypatch.setattr(art.time, "sleep", lambda _s: None)
    cover("t1", library, root)
    assert calls["n"] == 3
    assert (root / "runtime" / "generated" / "t1.jpg").read_bytes() == IMAGE


def test_a_file_that_stays_locked_fails_the_job_and_leaves_no_temp_file(
    library: Library, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(src, dst) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(art.os, "replace", locked)
    monkeypatch.setattr(art.time, "sleep", lambda _s: None)
    jobs = JobStore()
    with pytest.raises(PermissionError):
        cover("t1", library, root, jobs=jobs)
    assert jobs.list()[0].status == "failed"
    assert list((root / "runtime" / "generated").glob("*.tmp")) == []
    assert library.get("t1").cover_path is None


# ---- start_cover(track) for the song pipeline (B6) ----------------------------------------------


def test_start_cover_returns_at_once_and_paints_in_the_background(library: Library, root: Path) -> None:
    import threading

    release = threading.Event()

    def slow_flux(prompt: str, *, seed: int | None = None) -> bytes:
        release.wait(timeout=5)
        return IMAGE

    thread = art.start_cover(
        library.get("t1"), library=library, root=root, chat=fake_chat, generate=slow_flux
    )
    assert library.get("t1").cover_path is None  # not painted yet: the caller wasn't blocked
    release.set()
    thread.join(timeout=5)
    assert library.get("t1").cover_path == "runtime/generated/t1.jpg"


def test_a_background_cover_failure_never_reaches_the_caller(library: Library, root: Path) -> None:
    jobs = JobStore()
    thread = art.start_cover(
        library.get("t1"),
        library=library,
        jobs=jobs,
        root=root,
        chat=fake_chat,
        generate=FakeFlux(fail=ServiceError("flux", "unavailable", "down")),
    )
    thread.join(timeout=5)
    assert jobs.list()[0].status == "failed"
    assert library.get("t1").cover_path is None
    assert art.cover_for("t1", library=library) == art.placeholder_path()
