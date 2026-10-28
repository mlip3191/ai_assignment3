"""What plays next (PROJECT.md 8.4). Pure Python: no Gradio and no model clients.

`queue` is the track ids still waiting. `current` is the one item a single audio
element is playing, either the DJ clip or the song. `next_item` uses a DJ clip
only when `dj_clips` already holds a path for that track. A missing clip plays
the song on the same call. Nothing here waits for Chatterbox.

`songs` and `dj_clips` are read live, so a clip filled in after `enqueue` is
visible at the next advance. Lane D owns filling `dj_clips`. This module does
not generate anything.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

FINISHED = "Queue finished"
DJ_UNAVAILABLE = "DJ unavailable for this track"


class PlayerError(Exception):
    """A track id is blank or is not in the song map."""


@dataclass(frozen=True)
class PlayItem:
    kind: Literal["dj", "song"]
    track_id: str
    audio_path: str


class Player:
    def __init__(
        self,
        songs: Mapping[str, str],
        dj_clips: Mapping[str, str] | None = None,
        dj_failed: Callable[[str], bool] | None = None,
    ) -> None:
        """``dj_failed(track_id)`` says whether that song's DJ clip failed. With it, a song that has no
        clip plays with the "DJ unavailable" notice only when it did; without it, a missing clip always
        gets the notice."""
        self._songs = songs
        self._dj = dj_clips if dj_clips is not None else {}
        self._dj_failed = dj_failed
        self._lock = threading.Lock()
        self._queue: list[str] = []
        self._current: PlayItem | None = None
        self._notice: str | None = None

    @property
    def queue(self) -> list[str]:
        with self._lock:
            return list(self._queue)

    @property
    def current(self) -> PlayItem | None:
        with self._lock:
            return self._current

    @property
    def notice(self) -> str | None:
        with self._lock:
            return self._notice

    def enqueue(self, track_id: str) -> None:
        """Add a track to the end. Playback stays where it is."""
        with self._lock:
            self._require(track_id)
            self._queue.append(track_id)

    def play_now(self, track_id: str) -> PlayItem:
        """Drop whatever is playing and start this track. One queued copy is pulled out."""
        with self._lock:
            self._require(track_id)
            self._current = None
            try:
                self._queue.remove(track_id)
            except ValueError:
                pass
            self._queue.insert(0, track_id)
            item = self._advance()
            if item is None:
                raise PlayerError(f"track {track_id!r} did not start")
            return item

    def next_item(self) -> PlayItem | None:
        """Advance one step. From idle, this starts the queue. At the end, returns None."""
        with self._lock:
            return self._advance()

    def skip(self) -> PlayItem | None:
        """During a DJ clip, jump to that song. During a song, move to the next track.

        With nothing playing, the queue is left as it is.
        """
        with self._lock:
            if self._current is None:
                return None
            return self._advance()

    def clear(self) -> None:
        """Stop and forget the queue. This is not the natural end, so no finished notice."""
        with self._lock:
            self._queue.clear()
            self._current = None
            self._notice = None

    def _advance(self) -> PlayItem | None:
        if self._current is not None and self._current.kind == "dj":
            song = PlayItem("song", self._current.track_id, self._songs[self._current.track_id])
            self._current = song
            self._notice = None
            return song
        if not self._queue:
            self._current = None
            self._notice = FINISHED
            return None
        track_id = self._queue.pop(0)
        dj_path = self._dj_path(track_id)
        if dj_path is None:
            self._current = PlayItem("song", track_id, self._songs[track_id])
            failed = self._dj_failed is None or self._dj_failed(track_id)
            self._notice = DJ_UNAVAILABLE if failed else None
        else:
            self._current = PlayItem("dj", track_id, dj_path)
            self._notice = None
        return self._current

    def _dj_path(self, track_id: str) -> str | None:
        raw = self._dj.get(track_id)
        if isinstance(raw, str) and raw.strip():
            return raw
        return None

    def _require(self, track_id: str) -> None:
        if not isinstance(track_id, str) or not track_id.strip():
            raise PlayerError("track id must be a non-empty string")
        path = self._songs.get(track_id)
        if not isinstance(path, str) or not path.strip():
            raise PlayerError(f"unknown track {track_id!r}")
