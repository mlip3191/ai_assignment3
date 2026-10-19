"""The in-memory library (PROJECT.md 6.3): lookup by id, audio-first adds, manifest loading, thread safety."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from jukebox import library as library_module
from jukebox.library import Library, LibraryError


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "runtime" / "generated").mkdir(parents=True)
    return tmp_path


def audio(root: Path, name: str) -> str:
    """Create a fake audio file under root and return its root-relative path."""
    rel = f"runtime/generated/{name}.mp3"
    (root / rel).write_bytes(b"ID3")
    return rel


def test_add_get_list(root, make_track):
    lib = Library(root=root)
    first = make_track(id="t1", audio_path=audio(root, "t1"))
    second = make_track(id="t2", audio_path=audio(root, "t2"))
    lib.add(first)
    lib.add(second)
    assert lib.get("t2") == second
    assert lib.get("t1") == first
    assert [t.id for t in lib.list()] == ["t1", "t2"]


def test_get_unknown_id_returns_none(root):
    assert Library(root=root).get("nope") is None


def test_lookup_is_by_id_not_position(root, make_track):
    lib = Library(root=root)
    lib.add(make_track(id="a", audio_path=audio(root, "a")))
    lib.add(make_track(id="b", audio_path=audio(root, "b")))
    assert lib.get("0") is None
    assert lib.get("b").id == "b"


def test_add_refuses_track_without_audio(root, make_track):
    lib = Library(root=root)
    with pytest.raises(LibraryError, match="audio"):
        lib.add(make_track(id="t1", audio_path="runtime/generated/missing.mp3"))
    assert lib.list() == []


def test_add_refuses_a_path_that_climbs_out_of_the_root(root, make_track):
    repo = root / "repo"
    repo.mkdir()
    (root / "outside.mp3").write_bytes(b"ID3")
    lib = Library(root=repo)
    with pytest.raises(LibraryError, match=r"\.\."):
        lib.add(make_track(id="t1", audio_path="../outside.mp3"))
    assert lib.list() == []


def test_add_rejects_duplicate_id(root, make_track):
    lib = Library(root=root)
    lib.add(make_track(id="t1", audio_path=audio(root, "t1")))
    with pytest.raises(LibraryError, match="t1"):
        lib.add(make_track(id="t1", title="Other", audio_path=audio(root, "t1")))
    assert lib.get("t1").title == "Night Drive"


def test_absolute_audio_path_is_accepted(root, make_track):
    lib = Library(root=root)
    absolute = str((root / audio(root, "t1")).resolve())
    lib.add(make_track(id="t1", audio_path=absolute))
    assert lib.get("t1") is not None


def test_cover_can_be_attached_later(root, make_track):
    lib = Library(root=root)
    lib.add(make_track(id="t1", audio_path=audio(root, "t1"), cover_path=None))
    updated = lib.attach_cover("t1", "runtime/generated/t1.png", cover_prompt="a quiet road")
    assert updated.cover_path == "runtime/generated/t1.png"
    assert updated.cover_prompt == "a quiet road"
    assert lib.get("t1").cover_path == "runtime/generated/t1.png"


def test_attach_cover_unknown_track(root):
    with pytest.raises(LibraryError, match="nope"):
        Library(root=root).attach_cover("nope", "x.png")


def test_returned_tracks_are_copies(root, make_track):
    lib = Library(root=root)
    lib.add(make_track(id="t1", audio_path=audio(root, "t1")))
    lib.get("t1").title = "changed outside the lock"
    lib.list()[0].title = "changed outside the lock"
    assert lib.get("t1").title == "Night Drive"


def test_concurrent_adds(root, make_track):
    lib = Library(root=root)
    count = 50
    tracks = [make_track(id=f"t{i}", audio_path=audio(root, f"t{i}")) for i in range(count)]
    start = threading.Barrier(count)
    errors: list[Exception] = []

    def worker(track):
        try:
            start.wait()
            lib.add(track)
        except Exception as exc:  # noqa: BLE001 - the test reports any failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tracks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(t.id for t in lib.list()) == sorted(t.id for t in tracks)


def test_concurrent_adds_of_the_same_id_admit_exactly_one(root, make_track):
    lib = Library(root=root)
    rel = audio(root, "dup")
    attempts = 20
    start = threading.Barrier(attempts)
    results: list[str] = []

    def worker():
        start.wait()
        try:
            lib.add(make_track(id="dup", audio_path=rel))
            results.append("added")
        except LibraryError:
            results.append("refused")

    threads = [threading.Thread(target=worker) for _ in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("added") == 1
    assert len(lib.list()) == 1


# ---- manifest ---------------------------------------------------------------------------------


def write_manifest(root: Path, entries) -> Path:
    path = root / "samples" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def sample_entry(make_track, root: Path, n: int, **overrides) -> dict:
    audio_rel = f"samples/audio/sample_0{n}.mp3"
    cover_rel = f"samples/covers/sample_0{n}.png"
    for rel in (audio_rel, cover_rel):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x")
    entry = make_track(
        id=f"sample_0{n}",
        audio_path=audio_rel,
        cover_path=cover_rel,
        cover_prompt="a sample cover",
        source="sample",
    ).to_dict()
    entry.update(overrides)
    return entry


def test_loads_manifest(root, make_track):
    path = write_manifest(
        root,
        [
            sample_entry(make_track, root, 1),
            sample_entry(make_track, root, 2),
            sample_entry(make_track, root, 3),
        ],
    )
    lib = Library(root=root)
    assert lib.load_manifest(path) == 3
    assert [t.id for t in lib.list()] == ["sample_01", "sample_02", "sample_03"]
    assert lib.get("sample_02").source == "sample"
    assert lib.get("sample_02").cover_path == "samples/covers/sample_02.png"


def test_manifest_samples_come_before_generated_tracks(root, make_track):
    path = write_manifest(root, [sample_entry(make_track, root, 1)])
    lib = Library(root=root)
    lib.load_manifest(path)
    lib.add(make_track(id="gen1", audio_path=audio(root, "gen1")))
    assert [t.id for t in lib.list()] == ["sample_01", "gen1"]


def test_missing_manifest_loads_nothing(root):
    lib = Library(root=root)
    assert lib.load_manifest(root / "samples" / "manifest.json") == 0
    assert lib.list() == []


def test_manifest_with_a_utf8_bom_loads(root, make_track):
    """Notepad and PowerShell 5 on Windows save UTF-8 files with a BOM."""
    entries = [sample_entry(make_track, root, 1, title="Café Nights")]
    path = root / "samples" / "manifest.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(entries, ensure_ascii=False).encode("utf-8"))
    lib = Library(root=root)
    assert lib.load_manifest(path) == 1
    assert lib.get("sample_01").title == "Café Nights"


@pytest.mark.parametrize("field", ["audio_path", "cover_path"])
@pytest.mark.parametrize(
    "bad",
    [
        "../outside.mp3",
        "samples/../../outside.mp3",
        "..\\outside.mp3",
        "C:\\music\\x.mp3",
        "\\\\server\\share\\x.mp3",
    ],
)
def test_manifest_paths_must_stay_inside_the_repo(root, make_track, field, bad):
    (root / "outside.mp3").write_bytes(b"ID3")
    path = write_manifest(root, [sample_entry(make_track, root, 1, **{field: bad})])
    lib = Library(root=root)
    with pytest.raises(LibraryError, match="relative"):
        lib.load_manifest(path)
    assert lib.list() == []


def test_manifest_rejects_an_absolute_path_even_if_the_file_exists(root, make_track):
    entry = sample_entry(make_track, root, 1)
    entry["audio_path"] = str((root / entry["audio_path"]).resolve())
    path = write_manifest(root, [entry])
    with pytest.raises(LibraryError, match="relative"):
        Library(root=root).load_manifest(path)


def test_manifest_that_is_not_json_raises_clear_error(root):
    path = root / "samples" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(LibraryError, match="manifest"):
        Library(root=root).load_manifest(path)


def test_manifest_must_be_a_list(root):
    path = write_manifest(root, {"tracks": []})
    with pytest.raises(LibraryError, match="list"):
        Library(root=root).load_manifest(path)


def test_manifest_entry_with_missing_audio_raises(root, make_track):
    entry = sample_entry(make_track, root, 1)
    (root / entry["audio_path"]).unlink()
    path = write_manifest(root, [entry])
    lib = Library(root=root)
    with pytest.raises(LibraryError, match="sample_01"):
        lib.load_manifest(path)
    assert lib.list() == []


def test_manifest_entry_with_bad_fields_names_the_entry(root, make_track):
    entry = sample_entry(make_track, root, 1)
    del entry["title"]
    path = write_manifest(root, [entry])
    with pytest.raises(LibraryError, match="title"):
        Library(root=root).load_manifest(path)


def test_failed_manifest_load_adds_nothing(root, make_track):
    good = sample_entry(make_track, root, 1)
    bad = sample_entry(make_track, root, 2)
    (root / bad["audio_path"]).unlink()
    path = write_manifest(root, [good, bad])
    lib = Library(root=root)
    with pytest.raises(LibraryError):
        lib.load_manifest(path)
    assert lib.list() == []


def test_manifest_with_duplicate_ids_raises(root, make_track):
    path = write_manifest(root, [sample_entry(make_track, root, 1), sample_entry(make_track, root, 1)])
    with pytest.raises(LibraryError, match="sample_01"):
        Library(root=root).load_manifest(path)


# ---- process-wide accessor --------------------------------------------------------------------


def test_get_library_is_one_shared_instance(root, monkeypatch, make_track):
    path = write_manifest(root, [sample_entry(make_track, root, 1)])
    monkeypatch.setattr(library_module, "ROOT", root)
    monkeypatch.setattr(library_module, "DEFAULT_MANIFEST", path)
    monkeypatch.setattr(library_module, "_shared", None)
    first = library_module.get_library()
    assert library_module.get_library() is first
    assert [t.id for t in first.list()] == ["sample_01"]
