"""The player panel (PROJECT.md 8.4, E1 Option A, E4).

Each browser session has its own ``Player``. One ``gr.Audio(autoplay=True)``
plays whatever that session returns. Play queue starts it. Skip and the audio
``stop`` event both advance, and a token in the served filename drops a late
end event so Skip cannot advance twice. Pause and resume are the native
controls (``interactive=False`` still plays). This module calls the library,
the cover lookup, and the queue. It does not call a model.

Add to queue and Play now (A7) reach the same session player from the Generate
card and the Library tab. ``render()`` returns a ``PlayerPanel`` that binds a
button and a track-id state to this panel's outputs. Add to queue never touches
the audio that is playing.
"""

from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import gradio as gr

from jukebox.config import ROOT
from jukebox.library import Library, get_library
from jukebox.services.art import cover_for
from jukebox.services.player import DJ_UNAVAILABLE, FINISHED, Player, PlayerError, PlayItem
from jukebox.ui.markdown import escape

SPEAKING = "DJ speaking…"
NOW_PLAYING = "Now playing"
PRESS_PLAY = "Press Play queue."
NO_SAMPLES = "No sample tracks are loaded."
UNKNOWN_TRACK = "That song is not in the library. Pick one from the list."
_TOKEN_IN_NAME = re.compile(r"^t(\d+)-")
_CLIPS: dict[str, str] = {}


class LibrarySongs(Mapping[str, str]):
    """Song paths read from the library on each lookup, so a new track is visible."""

    def __init__(self, library: Library) -> None:
        self._library = library

    def __getitem__(self, track_id: str) -> str:
        track = self._library.get(track_id)
        if track is None:
            raise KeyError(track_id)
        return str(self._library.resolve(track.audio_path))

    def __iter__(self) -> Iterator[str]:
        return (track.id for track in self._library.list())

    def __len__(self) -> int:
        return len(self._library.list())


@dataclass(frozen=True)
class PlayerView:
    """What the panel shows after one Play, Skip, end event, Add to queue, or Play now.

    ``keep_audio`` updates the text and Up next but leaves the audio, the cover, and the token alone,
    so a song that is playing is not interrupted (Add to queue, or a song that is not in the library).
    """

    audio: str | None
    label: str
    title: str
    cover: str | None
    notice: str | None
    up_next: tuple[tuple[str, str], ...]
    token: int
    ignored: bool
    keep_audio: bool = False


def open_player(library: Library, dj_clips: Mapping[str, str] | None = None) -> Player:
    """A queue over this library. ``dj_clips`` is read live and may start empty."""
    clips = dj_clips if dj_clips is not None else {}
    return Player(LibrarySongs(library), clips)


_SESSIONS: dict[str, Player] = {}


def player_for(session_id: str, library: Library) -> tuple[Player, str]:
    """The player for this browser session. A blank id starts a new one.

    Gradio state resets on reload, so the new page does not keep another tab's
    current song. The id stays server-side. ``Player`` holds a lock, so it is
    not stored in ``gr.State`` itself.
    """
    if session_id:
        found = _SESSIONS.get(session_id)
        if found is not None:
            return found, session_id
    new_id = uuid.uuid4().hex
    player = open_player(library, _CLIPS)
    _SESSIONS[new_id] = player
    return player, new_id


def on_play(player: Player, library: Library, token: int, runtime: Path) -> PlayerView:
    """Start the queue. A second Play while something is already playing does nothing.

    An empty queue is filled with the sample tracks, in library order, then started.
    """
    if player.current is not None:
        return _view(player, library, token, audio=None, ignored=True)
    if not player.queue:
        for track in library.list():
            if track.source == "sample":
                player.enqueue(track.id)
    if not player.queue:
        return PlayerView(None, NO_SAMPLES, "", None, None, (), token, False)
    return _show(player, library, player.next_item(), token + 1, runtime)


def on_skip(player: Player, library: Library, token: int, runtime: Path) -> PlayerView:
    """Skip the item that is playing. With nothing playing, the queue stays put."""
    if player.current is None:
        return _view(player, library, token, audio=None, ignored=True)
    return _show(player, library, player.skip(), token + 1, runtime)


def on_end(
    player: Player,
    library: Library,
    token: int,
    audio_value: object,
    runtime: Path,
) -> PlayerView:
    """Advance when the file that ended is the one this token started."""
    if token_from_audio(audio_value) != token:
        return _view(player, library, token, audio=None, ignored=True)
    return _show(player, library, player.next_item(), token + 1, runtime)


def on_add(player: Player, library: Library, token: int, track_id: str | None, runtime: Path) -> PlayerView:
    """Add one song to the end of the queue, looked up by id. What is playing keeps playing."""
    try:
        player.enqueue(_known_id(library, track_id))
    except PlayerError:
        return _unknown(player, library, token)
    return replace(_view(player, library, token, audio=None, ignored=False), keep_audio=True)


def on_play_now(
    player: Player, library: Library, token: int, track_id: str | None, runtime: Path
) -> PlayerView:
    """Drop what is playing and start this song (its DJ clip first, when one is ready)."""
    try:
        item = player.play_now(_known_id(library, track_id))
    except PlayerError:
        return _unknown(player, library, token)
    return _show(player, library, item, token + 1, runtime)


def panel_text(view: PlayerView) -> str:
    """The now-playing line, the title, a DJ notice, and the up-next titles."""
    lines = [f"**{view.label}**", ""]
    if view.title:
        lines.append(escape(view.title))
        lines.append("")
    if view.notice and view.notice != view.label:
        lines.append(view.notice)
        lines.append("")
    if view.up_next:
        lines.append("Up next:")
        lines.extend(f"- {escape(title)}" for title, _cover in view.up_next)
    else:
        lines.append("Up next: nothing queued.")
    return "\n".join(lines)


@dataclass(frozen=True)
class PlayerPanel:
    """What the page needs to send a song to this panel's player from another button."""

    session: gr.State
    token: gr.State
    outputs: list
    library: Library
    runtime: Path

    def connect_add(self, button: gr.Button, track_id: gr.State) -> None:
        """Add to queue: ``track_id`` holds the song's id (the Generate card's, or the Library's choice)."""

        def clicked(chosen: str | None, current: int, session_id: str) -> tuple[object, ...]:
            player, session_id = player_for(session_id, self.library)
            view = _gradio(on_add(player, self.library, int(current), chosen, self.runtime))
            return (*view, session_id)

        button.click(
            clicked,
            inputs=[track_id, self.token, self.session],
            outputs=self.outputs,
            show_progress="hidden",
        )

    def connect_play_now(self, button: gr.Button, track_id: gr.State) -> None:
        """Play now: the same inputs, starting that song at once."""

        def clicked(chosen: str | None, current: int, session_id: str) -> tuple[object, ...]:
            player, session_id = player_for(session_id, self.library)
            view = _gradio(on_play_now(player, self.library, int(current), chosen, self.runtime))
            return (*view, session_id)

        button.click(
            clicked,
            inputs=[track_id, self.token, self.session],
            outputs=self.outputs,
            show_progress="hidden",
        )


def render(*, library: Library | None = None) -> PlayerPanel:
    """Wire Play queue, Skip, and the end event to this session's player, and return the panel handle."""
    library = get_library() if library is None else library
    runtime = ROOT / "runtime" / "player"
    status = gr.Markdown(_idle_text(), elem_id="player-panel")
    cover = gr.Image(
        label="Cover",
        type="filepath",
        interactive=False,
        buttons=["download"],
        elem_id="now-cover",
        height=280,
    )
    audio = gr.Audio(
        label="Now playing",
        type="filepath",
        autoplay=True,
        interactive=False,
        buttons=["download"],
        elem_id="now-playing",
    )
    upcoming = gr.Gallery(
        label="Up next",
        type="filepath",
        interactive=False,
        allow_preview=False,
        buttons=[],
        columns=3,
        elem_id="up-next",
    )
    token = gr.State(0)
    session = gr.State("")
    play_btn = gr.Button("Play queue", elem_id="play-queue")
    skip_btn = gr.Button("Skip", elem_id="skip")
    outputs = [audio, status, cover, upcoming, token, session]

    def play_clicked(current: int, session_id: str) -> tuple[object, ...]:
        player, session_id = player_for(session_id, library)
        view = _gradio(on_play(player, library, int(current), runtime))
        return (*view, session_id)

    def skip_clicked(current: int, session_id: str) -> tuple[object, ...]:
        player, session_id = player_for(session_id, library)
        view = _gradio(on_skip(player, library, int(current), runtime))
        return (*view, session_id)

    def end_fired(audio_value: object, current: int, session_id: str) -> tuple[object, ...]:
        player, session_id = player_for(session_id, library)
        view = _gradio(on_end(player, library, int(current), audio_value, runtime))
        return (*view, session_id)

    play_btn.click(play_clicked, inputs=[token, session], outputs=outputs)
    skip_btn.click(skip_clicked, inputs=[token, session], outputs=outputs)
    audio.stop(end_fired, inputs=[audio, token, session], outputs=outputs)
    return PlayerPanel(session, token, outputs, library, runtime)


def token_from_audio(value: object) -> int | None:
    """The play token encoded in a served filename, if this value has one."""
    path = _audio_path(value)
    if path is None:
        return None
    match = _TOKEN_IN_NAME.match(Path(path).name)
    if match is None:
        return None
    return int(match.group(1))


def _show(
    player: Player,
    library: Library,
    item: PlayItem | None,
    token: int,
    runtime: Path,
) -> PlayerView:
    if item is None:
        return _view(player, library, token, audio=None, ignored=False)
    try:
        served = _serve(item.audio_path, token, runtime)
    except OSError:
        failed = _view(player, library, token, audio=None, ignored=False)
        return PlayerView(
            None,
            failed.label,
            failed.title,
            failed.cover,
            DJ_UNAVAILABLE,
            failed.up_next,
            token,
            False,
        )
    return _view(player, library, token, audio=str(served), ignored=False)


def _title(library: Library, track_id: str) -> str:
    track = library.get(track_id)
    return track.title if track is not None else track_id


def _view(
    player: Player,
    library: Library,
    token: int,
    *,
    audio: str | None,
    ignored: bool,
) -> PlayerView:
    current = player.current
    if current is None:
        label = FINISHED if player.notice == FINISHED else PRESS_PLAY
        title = ""
        cover = None
    else:
        label = SPEAKING if current.kind == "dj" else NOW_PLAYING
        title = _title(library, current.track_id)
        cover = str(cover_for(current.track_id, library=library))
    upcoming = tuple(
        (_title(library, track_id), str(cover_for(track_id, library=library))) for track_id in player.queue
    )
    return PlayerView(audio, label, title, cover, player.notice, upcoming, token, ignored)


def _serve(source: str, token: int, runtime: Path) -> Path:
    """Copy the clip to a new name that carries the token.

    The name is new on every play. A reload starts its token at 1 again, and
    the old ``t1-`` file stays on disk untouched.
    """
    src = _source_file(source)
    runtime.mkdir(parents=True, exist_ok=True)
    dest = runtime / f"t{token}-{uuid.uuid4().hex}-{src.name}"
    shutil.copyfile(src, dest)
    return dest


def _source_file(source: str) -> Path:
    src = Path(source)
    if src.is_file():
        return src
    rooted = ROOT / src
    if rooted.is_file():
        return rooted
    raise FileNotFoundError(source)


def _audio_path(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return str(value)
    if isinstance(value, dict):
        for key in ("path", "name", "orig_name"):
            item = value.get(key)
            if item:
                return str(item)
    named = getattr(value, "path", None)
    if named:
        return str(named)
    return None


def _idle_text() -> str:
    return "\n".join(
        [
            f"**{PRESS_PLAY}**",
            "",
            "Cover and title appear here when a sample starts.",
            "",
            "Up next: nothing queued.",
        ]
    )


def _gradio(view: PlayerView) -> tuple[object, ...]:
    if view.ignored:
        return (gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip())
    gallery = [(cover, title) for title, cover in view.up_next]
    if view.keep_audio:
        return (gr.skip(), panel_text(view), gr.skip(), gallery, gr.skip())
    return (view.audio, panel_text(view), view.cover, gallery, view.token)


def _known_id(library: Library, track_id: str | None) -> str:
    """The id, if it names a song in the library; otherwise PlayerError (blank, None, or gone)."""
    if not isinstance(track_id, str) or not track_id.strip() or library.get(track_id) is None:
        raise PlayerError(f"unknown track {track_id!r}")
    return track_id


def _unknown(player: Player, library: Library, token: int) -> PlayerView:
    """Nothing changes: the text says the song is not there, and the audio keeps playing."""
    view = _view(player, library, token, audio=None, ignored=False)
    return replace(view, notice=UNKNOWN_TRACK, keep_audio=True)
