"""The process-wide, in-memory track library (PROJECT.md 6.3).

Loaded at startup from `samples/manifest.json`, then extended with generated tracks. Gradio runs
handlers concurrently, so every read and write goes through one lock. Tracks are looked up by id, and
callers get copies so nothing mutates library state outside the lock.

`samples/manifest.json` is written by lane C (`scripts/generate_samples.py`): a JSON list of Track
records (the 6.1 fields), with `audio_path` and `cover_path` relative to the repository root.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path

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
            self._add_locked(track)
        return dataclasses.replace(track)

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
            updated = dataclasses.replace(track, cover_path=cover_path, cover_prompt=cover_prompt)
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
                tracks.append(Track.from_dict(entry))
            except ValueError as exc:
                raise LibraryError(f"sample manifest entry {index}: {exc}") from exc
        with self._lock:
            staged = dict(self._tracks)
            try:
                for track in tracks:
                    self._add_locked(track, into=staged)
            except LibraryError as exc:
                raise LibraryError(f"sample manifest {path.name}: {exc}") from exc
            self._tracks = staged
        return len(tracks)

    def _add_locked(self, track: Track, *, into: dict[str, Track] | None = None) -> None:
        tracks = self._tracks if into is None else into
        if track.id in tracks:
            raise LibraryError(f"track {track.id!r} is already in the library")
        if not self._resolve(track.audio_path).is_file():
            raise LibraryError(f"track {track.id!r} has no audio file at {track.audio_path!r}")
        tracks[track.id] = dataclasses.replace(track)

    def _resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else self._root / path


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
