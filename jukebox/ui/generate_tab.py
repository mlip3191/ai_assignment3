"""The Generate tab (task B7): the form for F1, its status line, and the result card (PROJECT.md 8.1).

The handler runs songs.generate_song on a worker thread and yields a view about once a second, so the
status line keeps counting while ACE-Step works (R5). It never raises: success and failure both end
with the Generate button enabled, and no handler writes to the form, so the user's choices stay (R6).
This module calls the song pipeline and the cover service only. It does not import a model client.

Play now and Add to queue are returned from render() with the new track's id, for the integration (A7)
to connect to the player.
"""

from __future__ import annotations

import functools
import logging
import queue
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import get_args

import gradio as gr

from jukebox import errors
from jukebox.errors import Kind, Recovery, Service, ServiceError
from jukebox.jobs import GENERIC_FAILURE, JobStore
from jukebox.library import Library, get_library
from jukebox.models import Job, Track
from jukebox.services import art, songs

GENRES = (
    "pop",
    "rock",
    "hip hop",
    "lo-fi hip hop",
    "electronic",
    "jazz",
    "country",
    "folk",
    "R&B",
    "ambient",
)
MOODS = ("upbeat", "mellow", "dark", "triumphant", "dreamy", "melancholy", "energetic", "romantic")
VOCAL = "Vocal"
INSTRUMENTAL = "Instrumental"
MIN_DURATION_S = 10  # ACE-Step's documented minimum (B2)
MAX_DURATION_S = 120  # longer songs are untested and make large files (B2, the brief)
DEFAULT_DURATION_S = 60
DURATION_STEP_S = 5
# B1: Qwen's title and lyrics take about 1 s; B2: ACE-Step takes 5 to 7 s from submit to saved file.
# Both were measured with an empty class queue.
USUAL_WAIT_S = 10
TICK_S = 1.0
MAX_EXTRA_CHARS = 120
MAX_THEME_CHARS = 200

HELP = "\n".join(
    [
        "**Make a new song.** Pick a style and a mood, choose the length, and press **Generate**.",
        "",
        "- **Style:** the kind of music. Add your own words under *Extra style tags*, like instruments or "
        "an era. Names of real artists are removed: every song is original and never imitates a real artist.",
        "- **Mood:** how the song should feel.",
        f"- **Length:** {MIN_DURATION_S} to {MAX_DURATION_S} seconds. Vocal songs sound best at 30 seconds "
        "or more.",
        "- **Vocal or Instrumental:** a vocal song gets original lyrics written for it. "
        "An instrumental has no singing.",
        "- **Song idea (optional):** what the song is about, like *a road trip*. "
        "It shapes the lyrics and the cover.",
        f"- **Generate:** a song usually takes about {USUAL_WAIT_S} seconds, longer when the class servers "
        "are busy. The status line counts the seconds. The cover is painted afterwards, and the song can "
        "play before it is ready.",
    ]
)

# Positions in the tuple updates() returns, matching the outputs list in render().
OUT_STATUS, OUT_BUTTON, OUT_RETRY, OUT_RESULT, OUT_TITLE, OUT_LYRICS = range(6)
OUT_COVER, OUT_COVER_NOTE, OUT_PLAY_NOW, OUT_ADD, OUT_TRACK, OUT_TIMER, OUT_PLAY_NOTE = range(6, 13)

PLAYER_NOT_CONNECTED = "Play now and Add to queue work once the player is connected."

# What the status line tells the user to do after a failure (7.3 recovery).
_NEXT_STEP: dict[Recovery, str] = {
    "retry": "Your choices are kept: press **Retry**, or change them and press **Generate**.",
    "edit_inputs": "Your choices are kept: change them and press **Generate**.",
    "fix_and_restart": "Fix the settings, then restart the app.",
}
_PROBE = "\x00reason\x00"  # stands in for a bad_request reason when matching messages

_DONE = object()
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~])")
_log = logging.getLogger(__name__)

StartCover = Callable[[Track], object]


@dataclass(frozen=True)
class CoverView:
    path: str  # the cover, or the placeholder
    note: str  # "Painting cover…", the failure message, or ""
    done: bool  # True once there is nothing more to wait for


@dataclass(frozen=True)
class GenerateView:
    status: str
    running: bool
    failed: bool = False
    retry: bool = False  # 7.3 offers Retry for this failure
    elapsed_s: int = 0
    track_id: str | None = None
    title: str | None = None
    lyrics: str | None = None
    cover: CoverView | None = None


@dataclass(frozen=True)
class GenerateTab:
    """What the integration connects to the player: both buttons pass the new song's `track_id`."""

    play_now: gr.Button
    add_to_queue: gr.Button
    track_id: gr.State


def compose_style(genre: str | None, extra: str | None) -> str:
    """The style sent to the pipeline: the genre, then the extra tags, without empty parts."""
    parts = [genre or "", *(extra or "").split(",")]
    return ", ".join(p.strip() for p in parts if p.strip())


def style_note(genre: str | None, extra: str | None) -> str:
    """What B8 would remove from the style, shown before Generate is clicked; "" when nothing."""
    return songs.check_style(compose_style(genre, extra)).warning or ""


def theme_note(theme: str | None) -> str:
    return songs.check_theme(theme or "").warning or ""


def generate(
    genre: str | None,
    extra: str | None,
    mood: str,
    duration_s: float,
    song_type: str,
    theme: str | None,
    *,
    library: Library | None = None,
    run: Callable[..., Iterator[Job]] | None = None,
    start_cover: StartCover | None = None,
    clock: Callable[[], float] = time.monotonic,
    tick_s: float = TICK_S,
) -> Iterator[GenerateView]:
    """Make one song and yield what the tab should show, ending with the Generate button enabled.

    If the browser stops listening part-way, the worker still finishes and the song joins the library.
    """
    library = get_library() if library is None else library
    run = songs.generate_song if run is None else run
    vocal = song_type != INSTRUMENTAL
    updates: queue.Queue[object] = queue.Queue()

    def work() -> None:
        try:
            for job in run(
                style=compose_style(genre, extra),
                mood=mood,
                duration_s=duration_s,
                vocal=vocal,
                theme=(theme or "").strip() or None,
                library=library,
                start_cover=start_cover,
            ):
                updates.put(job)
        except Exception as err:  # generate_song never raises; this guards the page anyway
            _log.warning("song generation stopped unexpectedly (%s)", type(err).__name__)
        finally:
            updates.put(_DONE)

    start = clock()
    stage = songs.STAGE_QUEUED
    yield _running(stage, 0)
    threading.Thread(target=work, name="generate-song", daemon=True).start()
    last: Job | None = None
    while True:
        try:
            item = updates.get(timeout=tick_s)
        except queue.Empty:
            yield _running(stage, int(clock() - start))
            continue
        if item is _DONE:
            break
        last = item  # type: ignore[assignment]
        if last.status in ("queued", "running"):
            stage = last.stage
            yield _running(stage, int(clock() - start))
    yield _finished(last, int(clock() - start), library)


def cover_view(
    track_id: str | None, *, library: Library | None = None, jobs: JobStore | None = None
) -> CoverView:
    """The result card's cover, looked up by `track_id`: the cover, or the placeholder and why."""
    library = get_library() if library is None else library
    placeholder = str(art.placeholder_path())
    track = library.get(track_id) if track_id else None
    if track is None:
        return CoverView(placeholder, "", True)
    if track.cover_path and library.resolve(track.cover_path).is_file():
        return CoverView(str(art.cover_for(track_id, library=library)), "", True)
    job = art.cover_job_for(track_id, jobs=jobs)
    if job is not None and job.status == "failed":
        message = job.error or GENERIC_FAILURE
        return CoverView(
            placeholder, f"{message} Your song is safe; it plays with a placeholder cover.", True
        )
    return CoverView(placeholder, art.COVER_STAGE, False)


def updates(view: GenerateView, *, player_connected: bool = False) -> tuple[object, ...]:
    """The view as Gradio updates, in the order of OUT_* and render()'s outputs list.

    Play now and Add to queue light up only when the integration has connected them to the player.
    """
    done = view.track_id is not None
    playable = done and player_connected
    cover = view.cover
    return (
        gr.update(value=view.status),
        gr.update(interactive=not view.running),
        gr.update(visible=view.retry),
        gr.update(visible=done),
        gr.update(value=f"### {_escape(view.title)}" if done and view.title else ""),
        gr.update(value=view.lyrics or "", visible=bool(view.lyrics)),
        gr.update(value=cover.path if cover else None),
        gr.update(value=cover.note if cover else "", visible=bool(cover and cover.note)),
        gr.update(interactive=playable),
        gr.update(interactive=playable),
        view.track_id,
        gr.update(active=bool(cover and not cover.done)),
        gr.update(value=PLAYER_NOT_CONNECTED, visible=done and not player_connected),
    )


def cover_updates(view: CoverView) -> tuple[object, ...]:
    """One cover check: the image, its note, and whether the check keeps running."""
    return (
        gr.update(value=view.path),
        gr.update(value=view.note, visible=bool(view.note)),
        gr.update(active=not view.done),
    )


def render(
    *,
    library: Library | None = None,
    run: Callable[..., Iterator[Job]] | None = None,
    start_cover: StartCover | None = None,
    player_connected: bool = False,
) -> GenerateTab:
    """Build the tab inside the current Blocks. The cover is painted for each new song by default.

    Pass `player_connected=True` once the returned buttons are connected to the player (A7); until
    then they stay off and the card says why.
    """
    library = get_library() if library is None else library
    if start_cover is None:

        def start_cover(track: Track) -> object:
            return art.start_cover(track, library=library)

    gr.Markdown(HELP, elem_id="gen-help")
    with gr.Row():
        genre = gr.Dropdown(
            list(GENRES),
            value="pop",
            label="Style",
            info="The kind of music.",
            elem_id="gen-genre",
        )
        mood = gr.Dropdown(
            list(MOODS),
            value="upbeat",
            label="Mood",
            info="How the song should feel.",
            elem_id="gen-mood",
        )
    extra = gr.Textbox(
        label="Extra style tags (optional)",
        placeholder="e.g. synth, warm pads, 80s",
        info="Your own words, separated by commas. Artist names are removed.",
        max_length=MAX_EXTRA_CHARS,
        elem_id="gen-extra",
    )
    style_warning = gr.Markdown("", elem_id="gen-style-note")
    with gr.Row():
        duration = gr.Slider(
            MIN_DURATION_S,
            MAX_DURATION_S,
            value=DEFAULT_DURATION_S,
            step=DURATION_STEP_S,
            label="Length (seconds)",
            info="Vocal songs sound best at 30 seconds or more.",
            elem_id="gen-duration",
        )
        song_type = gr.Radio(
            [VOCAL, INSTRUMENTAL],
            value=VOCAL,
            label="Vocal or instrumental",
            info="Vocal songs get original lyrics.",
            elem_id="gen-type",
        )
    theme = gr.Textbox(
        label="Song idea (optional)",
        placeholder="e.g. a road trip with friends",
        info="What the song is about. It shapes the lyrics and the cover.",
        max_length=MAX_THEME_CHARS,
        elem_id="gen-theme",
    )
    theme_warning = gr.Markdown("", elem_id="gen-theme-note")
    with gr.Row():
        button = gr.Button("Generate", variant="primary", elem_id="gen-button")
        retry = gr.Button("Retry", visible=False, elem_id="gen-retry")
    status = gr.Markdown("", elem_id="gen-status")
    with gr.Group(visible=False, elem_id="gen-result") as result:
        title = gr.Markdown("", elem_id="gen-title")
        cover = gr.Image(
            label="Cover",
            type="filepath",
            interactive=False,
            height=240,
            buttons=["download", "fullscreen"],  # no share link
            elem_id="gen-cover",
        )
        cover_note = gr.Markdown("", visible=False, elem_id="gen-cover-note")
        lyrics = gr.Textbox(label="Lyrics", lines=8, interactive=False, visible=False, elem_id="gen-lyrics")
        with gr.Row():
            play_now = gr.Button("Play now", interactive=False, elem_id="gen-play-now")
            add_to_queue = gr.Button("Add to queue", interactive=False, elem_id="gen-add-to-queue")
        play_note = gr.Markdown(PLAYER_NOT_CONNECTED, visible=False, elem_id="gen-play-note")
    track_id = gr.State(None)
    timer = gr.Timer(TICK_S, active=False)

    inputs = [genre, extra, mood, duration, song_type, theme]
    outputs = [
        status,
        button,
        retry,
        result,
        title,
        lyrics,
        cover,
        cover_note,
        play_now,
        add_to_queue,
        track_id,
        timer,
        play_note,
    ]

    def on_generate(*form: object) -> Iterator[tuple[object, ...]]:
        for view in generate(*form, library=library, run=run, start_cover=start_cover):  # type: ignore[arg-type]
            yield updates(view, player_connected=player_connected)

    def on_cover_tick(current: str | None) -> tuple[object, ...]:
        return cover_updates(cover_view(current, library=library))

    for trigger in (button, retry):
        trigger.click(on_generate, inputs=inputs, outputs=outputs, show_progress="hidden")
    timer.tick(on_cover_tick, inputs=[track_id], outputs=[cover, cover_note, timer], show_progress="hidden")
    for box in (genre, extra):
        box.change(style_note, inputs=[genre, extra], outputs=[style_warning], show_progress="hidden")
    theme.change(theme_note, inputs=[theme], outputs=[theme_warning], show_progress="hidden")
    return GenerateTab(play_now, add_to_queue, track_id)


def _running(stage: str, elapsed_s: int) -> GenerateView:
    status = f"**{stage}** · {elapsed_s} s · usually about {USUAL_WAIT_S} s, longer when the class servers are busy"
    return GenerateView(status=status, running=True, elapsed_s=elapsed_s)


def _finished(job: Job | None, elapsed_s: int, library: Library) -> GenerateView:
    track = library.get(job.track_id) if job and job.status == "succeeded" and job.track_id else None
    if track is None:
        message = job.error if job and job.error else GENERIC_FAILURE
        offer = recovery_for(message)
        status = f"{message} {_NEXT_STEP[offer]}"
        return GenerateView(
            status=status, running=False, failed=True, retry=offer == "retry", elapsed_s=elapsed_s
        )
    return GenerateView(
        status=f"**{songs.STAGE_DONE}** in {elapsed_s} s.",
        running=False,
        elapsed_s=elapsed_s,
        track_id=track.id,
        title=track.title,
        lyrics=track.lyrics,
        cover=cover_view(track.id, library=library),
    )


def recovery_for(message: str) -> Recovery:
    """What 7.3 offers after this failure message: Retry, edit the inputs, or fix and restart.

    A Job keeps only the message, so it is matched against the messages errors.user_message() builds.
    Anything else (the generic failure, a stopped run) is worth retrying.
    """
    for prefix, offer in _recovery_prefixes():
        if message.startswith(prefix):
            return offer
    return "retry"


@functools.cache
def _recovery_prefixes() -> tuple[tuple[str, Recovery], ...]:
    found = []
    for service in get_args(Service):
        for kind in get_args(Kind):
            err = ServiceError(service, kind, reason=_PROBE)
            offer = errors.recovery(err) or "fix_and_restart"  # config: the settings are wrong
            if offer != "retry":
                found.append((errors.user_message(err).split(_PROBE)[0], offer))
    return tuple(found)


def _escape(text: str) -> str:
    """Generated text shown as Markdown, so a title can't add formatting or links."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)
