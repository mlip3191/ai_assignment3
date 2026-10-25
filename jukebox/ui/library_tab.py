"""The Library tab (A7): every song in the library, with its cover, and a way to play it.

The list is a Radio whose values are track ids, so a choice always means the same song, whatever else
joins the library afterwards. Songs and covers that arrive later show up on the next refresh, with no
page reload. Play now and Add to queue are returned from render() with the chosen id, and the page
connects them to the player (see ``PlayerPanel``). This module calls the library and the cover lookup
only. It does not call a model.
"""

from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from jukebox.library import Library, get_library
from jukebox.services.art import cover_for, placeholder_path
from jukebox.ui.markdown import escape
from jukebox.ui.player_panel import UNKNOWN_TRACK

EMPTY_TEXT = "No songs yet. Generate one, or press Play queue to hear the samples."
PICK_TEXT = "Pick a song from the list to see its cover and play it."
REFRESH_S = 3.0


@dataclass(frozen=True)
class Preview:
    """The cover and the details for the chosen song. ``track_id`` is None when nothing is chosen."""

    cover: str
    details: str
    track_id: str | None


@dataclass(frozen=True)
class LibraryTab:
    """What the page connects to the player: both buttons read the list, whose value is the chosen id."""

    play_now: gr.Button
    add_to_queue: gr.Button
    selected: gr.Radio


def choices(library: Library) -> list[tuple[str, str]]:
    """(label, track id) for every song, in library order."""
    return [
        (f"{t.title} ({'sample' if t.source == 'sample' else 'generated'})", t.id) for t in library.list()
    ]


def preview(library: Library, track_id: str | None) -> Preview:
    """The cover and details for one song, looked up by its id."""
    placeholder = str(placeholder_path())
    if not isinstance(track_id, str) or not track_id.strip():
        return Preview(placeholder, PICK_TEXT if library.list() else EMPTY_TEXT, None)
    track = library.get(track_id)
    if track is None:
        return Preview(placeholder, UNKNOWN_TRACK, None)
    kind = "Vocal" if track.vocal else "Instrumental"
    lines = [f"### {escape(track.title)}", "", f"{escape(track.style)} · {escape(track.mood)} · {kind}"]
    lines.append(f"About {track.duration_s} seconds")
    if track.theme:
        lines.append(f"Idea: {escape(track.theme)}")
    return Preview(str(cover_for(track.id, library=library)), "\n\n".join(lines), track.id)


def snapshot(library: Library) -> tuple[tuple[str, str | None], ...]:
    """Which songs there are and which have covers: when this changes, the tab has something new to show."""
    return tuple((t.id, t.cover_path) for t in library.list())


def pick(library: Library, track_id: str | None) -> tuple[str, str, str | None]:
    """The cover, the details and the chosen id after a click on the list."""
    shown = preview(library, track_id)
    return shown.cover, shown.details, shown.track_id


def tick(library: Library, current: str | None, last: object) -> tuple[object, ...]:
    """Show new songs and new covers. When nothing changed, touch nothing, so the list doesn't flicker.

    The list's own choice is never set here: a click made while this runs must not be undone by an
    older value. (The library has no way to remove a song, so a chosen song can't vanish.)
    """
    now = snapshot(library)
    if now == last:
        return (gr.skip(),) * 4
    shown = preview(library, current)
    return gr.update(choices=choices(library)), shown.cover, shown.details, now


def render(*, library: Library | None = None) -> LibraryTab:
    """Build the tab inside the current Blocks."""
    library = get_library() if library is None else library
    first = preview(library, None)
    with gr.Row():
        with gr.Column(scale=1):
            listing = gr.Radio(
                choices=choices(library),
                value=None,
                label="Songs",
                info="Songs you generate join this list while the app runs.",
                elem_id="lib-list",
            )
        with gr.Column(scale=1):
            cover = gr.Image(
                value=first.cover,
                label="Cover",
                type="filepath",
                interactive=False,
                height=240,
                buttons=["download"],  # no share link
                elem_id="lib-cover",
            )
            details = gr.Markdown(first.details, elem_id="lib-details")
            with gr.Row():
                play_now = gr.Button("Play now", elem_id="lib-play-now")
                add_to_queue = gr.Button("Add to queue", elem_id="lib-add-to-queue")
    selected = gr.State(None)
    seen = gr.State(snapshot(library))
    timer = gr.Timer(REFRESH_S)

    # One lane for both handlers: a tick that is running finishes before a pick is handled, so it can't
    # overwrite the pick's cover and details.
    lane = {"concurrency_id": "library-tab", "concurrency_limit": 1, "show_progress": "hidden"}
    listing.change(
        lambda track_id: pick(library, track_id), inputs=[listing], outputs=[cover, details, selected], **lane
    )
    timer.tick(
        lambda current, last: tick(library, current, last),
        inputs=[selected, seen],
        outputs=[listing, cover, details, seen],
        **lane,
    )
    return LibraryTab(play_now, add_to_queue, listing)
