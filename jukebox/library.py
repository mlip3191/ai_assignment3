"""The process-wide, in-memory track library (PROJECT.md 6.3).

Loaded at startup from `samples/manifest.json`, then extended with generated tracks. Gradio runs
handlers concurrently, so every read and write goes through one lock. Tracks are looked up by id, and
callers get copies so nothing mutates library state outside the lock.

`samples/manifest.json` is written by lane C (`scripts/generate_samples.py`): a JSON list of Track
records (the 6.1 fields), with `audio_path` and `cover_path` relative to the repository root. Each
sample's audio and cover files must exist when the manifest loads, or loading fails.

Stored paths always use forward slashes (`Path.as_posix()`), whichever OS wrote them: the library turns
any Windows backslashes into forward slashes when a track is added, a cover is attached or the manifest
is loaded, so samples generated on Windows still resolve on macOS. Use `Library.resolve(path)` to get the
real file for a stored path instead of building it yourself.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path, PurePosixPath, PureWindowsPath

from jukebox.config import ROOT
from jukebox.models import Track

DEFAULT_MANIFEST = ROOT / "samples" / "manifest.json"


class LibraryError(Exception):
    """A track could not be added or found, or the sample manifest is unusable."""


class Library:
    def __init__(self, *, root: Path = ROOT) -> None:
        self._root = Path(root)
        self._lock = threading.Lock()
        self._tracks: dict[str, Track] = {}  # dicts keep insertion order

    def add(self, track: Track) -> Track:
        """Add a track whose audio already exists. The cover may be missing and attached later."""
        with self._lock:
            stored = self._add_locked(track)
        return dataclasses.replace(stored)

    def resolve(self, stored_path: str) -> Path:
        """The real file for a path stored on a Track (relative to the repo root, or absolute)."""
        path = Path(_posix(stored_path))
        return path if path.is_absolute() else self._root / path

    def get(self, track_id: str) -> Track | None:
        with self._lock:
            track = self._tracks.get(track_id)
            return dataclasses.replace(track) if track else None

    def list(self) -> list[Track]:
        with self._lock:
            return [dataclasses.replace(t) for t in self._tracks.values()]

    def attach_cover(self, track_id: str, cover_path: str, cover_prompt: str | None = None) -> Track:
        with self._lock:
            track = self._tracks.get(track_id)
            if track is None:
                raise LibraryError(f"no track {track_id!r} in the library")
            try:
                updated = dataclasses.replace(track, cover_path=cover_path, cover_prompt=cover_prompt)
                updated = _normalised(updated)
            except ValueError as exc:
                raise LibraryError(f"cover for track {track_id!r} is not usable: {exc}") from exc
            self._tracks[track_id] = updated
            return dataclasses.replace(updated)

    def load_manifest(self, path: Path = DEFAULT_MANIFEST) -> int:
        """Add the sample tracks listed in the manifest; return how many. A missing file adds none.

        All-or-nothing: if any entry is unusable, nothing is added and the error names the entry.
        """
        path = Path(path)
        if not path.is_file():
            return 0
        try:
            # utf-8-sig also reads files without a BOM; Windows editors often add one
            entries = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise LibraryError(f"sample manifest {path.name} could not be read: {exc}") from exc
        if not isinstance(entries, list):
            raise LibraryError(f"sample manifest {path.name} must be a list of track records")
        tracks: list[Track] = []
        for index, entry in enumerate(entries):
            try:
                track = Track.from_dict(entry)
            except ValueError as exc:
                raise LibraryError(f"sample manifest entry {index}: {exc}") from exc
            for field in ("audio_path", "cover_path"):
                value = getattr(track, field)
                if value is not None and not _is_inside_repo(value):
                    raise LibraryError(
                        f"sample manifest {path.name}: track {track.id!r} {field} must be a relative path "
                        f"inside the repo (no '..', drive letter or leading slash): {value!r}"
                    )
            track = _normalised(track)
            if track.cover_path is not None and not self.resolve(track.cover_path).is_file():
                raise LibraryError(
                    f"sample manifest {path.name}: track {track.id!r} has no cover file at "
                    f"{track.cover_path!r}"
                )
            tracks.append(track)
        with self._lock:
            staged = dict(self._tracks)
            try:
                for track in tracks:
                    self._add_locked(track, into=staged)
            except LibraryError as exc:
                raise LibraryError(f"sample manifest {path.name}: {exc}") from exc
            self._tracks = staged
        return len(tracks)

    def _add_locked(self, track: Track, *, into: dict[str, Track] | None = None) -> Track:
        tracks = self._tracks if into is None else into
        if track.id in tracks:
            raise LibraryError(f"track {track.id!r} is already in the library")
        if _has_parent_segment(track.audio_path):
            raise LibraryError(f"track {track.id!r} audio_path must not contain '..': {track.audio_path!r}")
        stored = _normalised(track)
        if not self.resolve(stored.audio_path).is_file():
            raise LibraryError(f"track {track.id!r} has no audio file at {track.audio_path!r}")
        tracks[track.id] = stored
        return stored


def _posix(value: str) -> str:
    """The same path with forward slashes, so `samples\\audio\\a.mp3` also works on macOS and Linux."""
    return PureWindowsPath(value).as_posix()


def _normalised(track: Track) -> Track:
    """A copy of the track whose stored paths use forward slashes."""
    cover = None if track.cover_path is None else _posix(track.cover_path)
    return dataclasses.replace(track, audio_path=_posix(track.audio_path), cover_path=cover)


def _has_parent_segment(value: str) -> bool:
    """A '..' step, whether the path is written with / or \\ (a manifest may come from either OS)."""
    return ".." in PurePosixPath(value).parts or ".." in PureWindowsPath(value).parts


def _is_inside_repo(value: str) -> bool:
    """A relative path with no '..', no drive letter or UNC share, and no leading slash."""
    windows = PureWindowsPath(value)
    if PurePosixPath(value).is_absolute() or windows.drive or windows.root:
        return False
    return not _has_parent_segment(value)


_shared: Library | None = None
_shared_lock = threading.Lock()


def get_library() -> Library:
    """The one library for this process, with the samples loaded on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            library = Library(root=ROOT)
            library.load_manifest(DEFAULT_MANIFEST)
            _shared = library
        return _shared
