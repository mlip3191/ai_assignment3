"""Tests for the Generate tab (task B7): jukebox/ui/generate_tab.py.

Most tests drive the handler with a fake song pipeline and a fake clock, so they are fast and call no
service. One end-to-end test runs the real pipeline with Qwen and ACE-Step mocked by respx.
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import gradio as gr
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.acestep as acestep  # noqa: E402
import jukebox.clients.qwen as qwen  # noqa: E402
import jukebox.services.songs as songs  # noqa: E402
import jukebox.ui.generate_tab as tab  # noqa: E402
from jukebox.clients.acestep import AceStepClient  # noqa: E402
from jukebox.clients.qwen import QwenClient  # noqa: E402
from jukebox.config import load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402
from jukebox.jobs import GENERIC_FAILURE, JobStore  # noqa: E402
from jukebox.library import Library  # noqa: E402
from jukebox.models import Job, Track  # noqa: E402
from jukebox.services import art  # noqa: E402

LYRICS = "[verse]\nWindows down and the radio on\n\n[chorus]\nKeep it rolling, keep it free"
FORM = {
    "genre": "pop",
    "extra": "synth, warm pads",
    "mood": "upbeat",
    "duration_s": 60,
    "song_type": tab.VOCAL,
    "theme": "a road trip",
}


class FakeRun:
    """Stands in for songs.generate_song: yields the real stages and adds a real Track to the library."""

    def __init__(
        self, library: Library, *, fail: object = None, title: str = "Open Road", track_id: str = "t1"
    ) -> None:
        self.library = library
        self.track_id = track_id
        self.fail = fail
        self.title = title
        self.calls: list[dict] = []
        self.jobs = JobStore()

    def __call__(self, **kwargs) -> Iterator[Job]:
        self.calls.append(kwargs)
        jobs = self.jobs
        job = jobs.create("song", songs.STAGE_QUEUED)
        yield job
        yield jobs.set_stage(job.id, songs.STAGE_LYRICS if kwargs["vocal"] else songs.STAGE_TITLE)
        yield jobs.set_stage(job.id, songs.STAGE_MUSIC)
        if self.fail is not None:
            yield jobs.fail(job.id, self.fail)
            return
        yield jobs.set_stage(job.id, songs.STAGE_SAVING)
        _audio(self.library, f"runtime/generated/{self.track_id}.mp3")
        track = self.library.add(
            Track(
                id=self.track_id,
                title=self.title,
                style=kwargs["style"],
                mood=kwargs["mood"],
                theme=kwargs["theme"],
                duration_s=kwargs["duration_s"],
                vocal=kwargs["vocal"],
                lyrics=LYRICS if kwargs["vocal"] else None,
                audio_path=f"runtime/generated/{self.track_id}.mp3",
                cover_path=None,
                cover_prompt=None,
                source="generated",
                seed=None,
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),  # just made, like the pipeline
            )
        )
        if kwargs.get("start_cover"):
            kwargs["start_cover"](track)
        yield jobs.succeed(job.id, track.id)


def _audio(library: Library, stored: str) -> None:
    path = library.resolve(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ID3fake")


def counting_clock(step: float = 1.0):
    """A clock that moves `step` seconds every time it is read."""
    now = [0.0]

    def clock() -> float:
        now[0] += step
        return now[0]

    return clock


def views(library: Library, run, **overrides) -> list[tab.GenerateView]:
    form = {**FORM, **overrides}
    return list(
        tab.generate(**form, library=library, run=run, clock=counting_clock(), tick_s=0.01, start_cover=None)
    )


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(root=tmp_path)


def _by_id(demo: gr.Blocks, elem_id: str):
    for block in demo.blocks.values():
        if getattr(block, "elem_id", None) == elem_id:
            return block
    raise AssertionError(f"missing elem_id {elem_id}")


def _demo(library: Library, **kwargs) -> tuple[gr.Blocks, tab.GenerateTab]:
    with gr.Blocks() as demo:
        handles = tab.render(library=library, **kwargs)
    return demo, handles


def _run_for(demo: gr.Blocks, elem_id: str):
    """The song run: the event chained after this button's click, which marks the run as running."""
    mark = _fn_for(demo, elem_id, "click")
    raw = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
    for fn in raw:
        if fn.trigger_after == mark._id:
            return fn
    raise AssertionError(f"no run chained after the {elem_id} click")


def _fn_for(demo: gr.Blocks, elem_id: str, event: str):
    """The registered event whose trigger is this element and event name."""
    target = _by_id(demo, elem_id)._id
    raw = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
    for fn in raw:
        if any(t[0] == target and t[1] == event for t in fn.targets):
            return fn
    raise AssertionError(f"no {event} handler on {elem_id}")


# ---- controls (8.1) and help text (R7) -----------------------------------------------------------


def test_controls_match_section_8_1(library: Library) -> None:
    demo, _ = _demo(library)
    genre = _by_id(demo, "gen-genre")
    assert 8 <= len(genre.choices) <= 12
    assert _by_id(demo, "gen-extra").max_length
    mood = _by_id(demo, "gen-mood")
    assert {"upbeat", "mellow", "dark", "triumphant", "dreamy", "melancholy"} <= {c[0] for c in mood.choices}
    duration = _by_id(demo, "gen-duration")
    assert (duration.minimum, duration.maximum, duration.value) == (10, 120, 60)
    kind = _by_id(demo, "gen-type")
    assert {c[0] for c in kind.choices} == {tab.VOCAL, tab.INSTRUMENTAL}
    assert _by_id(demo, "gen-theme").max_length
    for elem_id in ("gen-button", "gen-status", "gen-title", "gen-lyrics", "gen-cover"):
        _by_id(demo, elem_id)


def test_duration_bounds_come_from_the_b2_findings() -> None:
    assert tab.MIN_DURATION_S == acestep.MIN_DURATION_S == 10  # ACE-Step's documented minimum
    assert tab.MAX_DURATION_S == 120  # the brief: longer songs are untested and make large files
    assert tab.MAX_DURATION_S <= acestep.MAX_DURATION_S
    assert tab.DEFAULT_DURATION_S == 60


def test_help_text_explains_every_control(library: Library) -> None:
    demo, _ = _demo(library)
    help_text = str(_by_id(demo, "gen-help").value)
    for word in ("Style", "Mood", "Length", "Vocal", "Instrumental", "Song idea", "Generate"):
        assert word in help_text
    assert "real artist" in help_text
    for elem_id in ("gen-genre", "gen-extra", "gen-mood", "gen-duration", "gen-type", "gen-theme"):
        assert _by_id(demo, elem_id).info, f"{elem_id} has no help line"


# ---- the Generate handler: button, stages, elapsed time (R5) -----------------------------------------


def test_generate_disables_the_button_and_reenables_it_on_success(library: Library) -> None:
    result = views(library, FakeRun(library))
    assert result[0].running is True
    assert all(v.running for v in result[:-1])
    assert result[-1].running is False
    assert result[-1].failed is False
    button = tab.updates(result[0])[tab.OUT_BUTTON]
    assert button["interactive"] is False
    assert tab.updates(result[-1])[tab.OUT_BUTTON]["interactive"] is True


def test_surprise_me_is_off_while_a_song_is_made_and_back_on_after(library: Library) -> None:
    # Clicking it mid-run would change the form under a run that may fail and offer Retry.
    for run in (FakeRun(library), FakeRun(library, fail=ServiceError("acestep", "timeout", "slow"))):
        result = views(library, run)
        assert tab.updates(result[0])[tab.OUT_SURPRISE]["interactive"] is False
        assert tab.updates(result[-1])[tab.OUT_SURPRISE]["interactive"] is True


def test_status_names_each_stage_in_order(library: Library) -> None:
    result = views(library, FakeRun(library))
    stages = []
    for v in result:
        for stage in (songs.STAGE_QUEUED, songs.STAGE_LYRICS, songs.STAGE_MUSIC, songs.STAGE_SAVING):
            if stage in v.status and (not stages or stages[-1] != stage):
                stages.append(stage)
    assert stages == [songs.STAGE_QUEUED, songs.STAGE_LYRICS, songs.STAGE_MUSIC, songs.STAGE_SAVING]
    assert songs.STAGE_DONE in result[-1].status


def test_instrumental_status_says_naming_not_writing_lyrics(library: Library) -> None:
    result = views(library, FakeRun(library), song_type=tab.INSTRUMENTAL)
    text = " ".join(v.status for v in result)
    assert songs.STAGE_TITLE in text
    assert songs.STAGE_LYRICS not in text


def test_status_shows_elapsed_time_and_the_usual_wait(library: Library) -> None:
    """While ACE-Step works there are no new stages, so the line must keep ticking."""
    release = threading.Event()
    seen_music = threading.Event()

    def slow_run(**kwargs) -> Iterator[Job]:
        inner = FakeRun(library)(**kwargs)
        for job in inner:
            yield job
            if job.stage == songs.STAGE_MUSIC:
                seen_music.set()
                release.wait(5)

    gen = tab.generate(
        **FORM, library=library, run=slow_run, clock=counting_clock(), tick_s=0.01, start_cover=None
    )
    ticks = []
    for v in gen:
        if songs.STAGE_MUSIC in v.status:
            ticks.append(v)
            if len(ticks) == 4:
                release.set()
    assert seen_music.is_set()
    assert len(ticks) >= 4
    seconds = [v.elapsed_s for v in ticks]
    assert seconds == sorted(seconds) and seconds[-1] > seconds[0]
    assert f"{ticks[-1].elapsed_s} s" in ticks[-1].status
    assert f"usually about {tab.USUAL_WAIT_S} s" in ticks[-1].status


def test_usual_wait_matches_the_b1_and_b2_measurements() -> None:
    # B1: Qwen title + lyrics about 1 s; B2: ACE-Step 5 to 7 s from submit to saved file (empty queue).
    assert 8 <= tab.USUAL_WAIT_S <= 12


# ---- failures (R6) ----------------------------------------------------------------------------------


def test_a_failure_reenables_the_button_shows_the_7_3_message_and_offers_retry(library: Library) -> None:
    error = ServiceError("acestep", "timeout", "poll limit reached")
    result = views(library, FakeRun(library, fail=error))
    last = result[-1]
    assert last.running is False and last.failed is True
    assert "took too long to respond" in last.status
    assert "poll limit" not in last.status  # developer detail never reaches the page
    assert "kept" in last.status.lower()
    out = tab.updates(last)
    assert out[tab.OUT_BUTTON]["interactive"] is True
    assert out[tab.OUT_RETRY]["visible"] is True
    assert last.track_id is None
    assert out[tab.OUT_PLAY_NOW]["interactive"] is False


def test_retry_runs_again_with_the_same_inputs(library: Library) -> None:
    demo, _ = _demo(library)
    generate = _run_for(demo, "gen-button")
    retry = _run_for(demo, "gen-retry")
    assert [c._id for c in retry.inputs] == [c._id for c in generate.inputs]
    assert [c._id for c in retry.outputs] == [c._id for c in generate.outputs]


def test_a_pipeline_that_raises_still_reenables_the_button(library: Library) -> None:
    def broken(**_kwargs) -> Iterator[Job]:
        raise RuntimeError("secret detail")
        yield  # pragma: no cover

    last = views(library, broken)[-1]
    assert last.running is False and last.failed is True
    assert "secret detail" not in last.status


def test_inputs_are_never_handler_outputs(library: Library) -> None:
    """The form keeps the user's choices on success and on failure: no handler writes to it, except the
    Surprise me button, whose whole job is to fill the form when the user clicks it."""
    demo, _ = _demo(library)
    inputs = {
        _by_id(demo, i)._id
        for i in ("gen-genre", "gen-extra", "gen-mood", "gen-duration", "gen-type", "gen-theme")
    }
    surprise = _by_id(demo, "gen-surprise")._id
    raw = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
    for fn in raw:
        if any(t[0] == surprise for t in fn.targets):
            continue
        assert not inputs & {c._id for c in fn.outputs}


def test_a_style_that_is_only_an_artist_is_refused_before_any_service_call(library: Library) -> None:
    """Uses the real pipeline; respx fails the test if any request is made."""
    with respx.mock(assert_all_called=False) as mock:
        last = list(
            tab.generate(
                **{**FORM, "genre": "", "extra": "in the style of Taylor Swift"},
                library=library,
                run=songs.generate_song,
                clock=counting_clock(),
                tick_s=0.01,
                start_cover=None,
            )
        )[-1]
        assert not mock.calls
    assert last.failed is True
    assert "without naming real artists" in last.status
    assert last.retry is False  # the same inputs would fail again
    assert "Retry" not in last.status


@pytest.mark.parametrize(
    "error, retry, says",
    [
        (ServiceError("acestep", "timeout"), True, "press **Retry**"),
        (ServiceError("qwen", "unavailable"), True, "press **Retry**"),
        (ServiceError("acestep", "bad_response"), True, "press **Retry**"),
        (
            ServiceError("acestep", "bad_request", reason="Duration must be between 10 and 600 seconds"),
            False,
            "change them",
        ),
        (ServiceError("qwen", "auth"), False, "restart the app"),
        (ServiceError("flux", "config"), False, "restart the app"),
        ("something odd", True, "press **Retry**"),  # an unknown failure becomes the generic message
    ],
)
def test_retry_is_offered_only_where_7_3_offers_it(library: Library, error, retry: bool, says: str) -> None:
    """7.3: Retry for timeout, unavailable and bad_response; edit inputs for bad_request; fix and
    restart for auth and config."""
    last = views(library, FakeRun(library, fail=error))[-1]
    assert last.failed is True
    assert last.retry is retry
    assert says in last.status
    assert tab.updates(last)[tab.OUT_RETRY]["visible"] is retry
    assert tab.updates(last)[tab.OUT_BUTTON]["interactive"] is True
    if not retry:
        assert "Retry" not in last.status


# ---- the wiring: output order, and the registered handlers ------------------------------------------

EXPECTED_OUTPUTS = {
    tab.OUT_STATUS: "gen-status",
    tab.OUT_BUTTON: "gen-button",
    tab.OUT_RETRY: "gen-retry",
    tab.OUT_RESULT: "gen-result",
    tab.OUT_TITLE: "gen-title",
    tab.OUT_LYRICS: "gen-lyrics",
    tab.OUT_COVER: "gen-cover",
    tab.OUT_COVER_NOTE: "gen-cover-note",
    tab.OUT_PLAY_NOW: "gen-play-now",
    tab.OUT_ADD: "gen-add-to-queue",
    tab.OUT_PLAY_NOTE: "gen-play-note",
    tab.OUT_RETRY_COVER: "gen-retry-cover",
    tab.OUT_SURPRISE: "gen-surprise",
}


def test_generate_outputs_are_in_the_order_updates_returns(library: Library) -> None:
    demo, handles = _demo(library)
    for elem_id in ("gen-button", "gen-retry"):
        outputs = _run_for(demo, elem_id).outputs
        assert len(outputs) == len(tab.updates(tab.GenerateView(status="", running=True)))
        for index, expected in EXPECTED_OUTPUTS.items():
            assert outputs[index].elem_id == expected, f"output {index} is {outputs[index].elem_id}"
        assert outputs[tab.OUT_TRACK] is handles.track_id
        assert isinstance(outputs[tab.OUT_TIMER], gr.Timer)


def test_cover_check_outputs_are_in_the_order_cover_updates_returns(library: Library) -> None:
    demo, _ = _demo(library)
    timer = next(b for b in demo.blocks.values() if isinstance(b, gr.Timer))
    raw = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
    tick = next(fn for fn in raw if any(t[0] == timer._id and t[1] == "tick" for t in fn.targets))
    for outputs in (tick.outputs, _fn_for(demo, "gen-retry-cover", "click").outputs):
        assert len(outputs) == len(tab.cover_updates(tab.CoverView("x", "", True)))
        assert [outputs[0].elem_id, outputs[1].elem_id] == ["gen-cover", "gen-cover-note"]
        assert outputs[2] is timer
        assert outputs[3].elem_id == "gen-retry-cover"


def test_the_registered_generate_handler_uses_the_pipeline_render_was_given(library: Library) -> None:
    """render(run=...) must reach the click handler, so a stand-in never falls through to the class servers."""
    fake = FakeRun(library)
    covers: list[str] = []
    demo, _ = _demo(library, run=fake, start_cover=lambda track: covers.append(track.id))
    handler = _run_for(demo, "gen-button").fn
    with respx.mock(assert_all_called=False) as mock:
        last = list(handler("pop", "synth", "upbeat", 60, tab.VOCAL, "a road trip"))[-1]
        assert not mock.calls
    assert len(fake.calls) == 1
    assert fake.calls[0]["start_cover"] is not None
    assert last[tab.OUT_TRACK] == "t1"
    assert "Open Road" in last[tab.OUT_TITLE]["value"]


# ---- what is sent to the pipeline -------------------------------------------------------------------


def test_the_form_is_sent_to_the_pipeline(library: Library) -> None:
    run = FakeRun(library)
    hook = object()
    list(
        tab.generate(**FORM, library=library, run=run, clock=counting_clock(), tick_s=0.01, start_cover=hook)
    )
    call = run.calls[0]
    assert call["style"] == "pop, synth, warm pads"
    assert (call["mood"], call["duration_s"], call["vocal"], call["theme"]) == (
        "upbeat",
        60,
        True,
        "a road trip",
    )
    assert call["library"] is library
    assert call["start_cover"] is hook


def test_an_empty_theme_is_sent_as_none_and_instrumental_as_not_vocal(library: Library) -> None:
    run = FakeRun(library)
    views(library, run, theme="   ", song_type=tab.INSTRUMENTAL)
    assert run.calls[0]["theme"] is None
    assert run.calls[0]["vocal"] is False


@pytest.mark.parametrize(
    "genre, extra, expected",
    [
        ("pop", "", "pop"),
        ("", "dreamy synths", "dreamy synths"),
        ("rock", " , gritty ", "rock, gritty"),
        (None, None, ""),
    ],
)
def test_compose_style(genre, extra, expected: str) -> None:
    assert tab.compose_style(genre, extra) == expected


# ---- the result card -------------------------------------------------------------------------------


def test_result_card_shows_title_and_lyrics_for_a_vocal_song(library: Library) -> None:
    last = views(library, FakeRun(library, title="Open Road"))[-1]
    assert last.track_id == "t1"
    assert last.title == "Open Road"
    assert last.lyrics == LYRICS
    out = tab.updates(last)
    assert out[tab.OUT_RESULT]["visible"] is True
    assert "Open Road" in out[tab.OUT_TITLE]["value"]
    assert out[tab.OUT_LYRICS]["visible"] is True and out[tab.OUT_LYRICS]["value"] == LYRICS


def test_result_card_hides_lyrics_for_an_instrumental(library: Library) -> None:
    last = views(library, FakeRun(library), song_type=tab.INSTRUMENTAL)[-1]
    assert last.lyrics is None
    assert tab.updates(last)[tab.OUT_LYRICS]["visible"] is False


def test_a_new_run_clears_the_previous_result(library: Library) -> None:
    first = views(library, FakeRun(library))[0]
    out = tab.updates(first)
    assert out[tab.OUT_RESULT]["visible"] is False
    assert out[tab.OUT_TRACK] is None
    assert out[tab.OUT_TIMER]["active"] is False


def test_play_now_and_add_to_queue_unlock_only_after_success(library: Library) -> None:
    result = views(library, FakeRun(library))
    for v in result[:-1]:
        out = tab.updates(v, player_connected=True)
        assert out[tab.OUT_PLAY_NOW]["interactive"] is False
        assert out[tab.OUT_ADD]["interactive"] is False
    out = tab.updates(result[-1], player_connected=True)
    assert out[tab.OUT_PLAY_NOW]["interactive"] is True
    assert out[tab.OUT_ADD]["interactive"] is True
    assert out[tab.OUT_PLAY_NOTE]["visible"] is False
    assert out[tab.OUT_TRACK] == "t1"
    assert out[tab.OUT_TIMER]["active"] is True  # the cover check starts


def test_play_now_and_add_to_queue_stay_off_until_the_player_is_connected(library: Library) -> None:
    """Until A7 connects them to the player, the buttons never light up and the card says why."""
    last = views(library, FakeRun(library))[-1]
    out = tab.updates(last)
    assert out[tab.OUT_PLAY_NOW]["interactive"] is False
    assert out[tab.OUT_ADD]["interactive"] is False
    assert out[tab.OUT_PLAY_NOTE]["visible"] is True
    assert out[tab.OUT_PLAY_NOTE]["value"] == tab.PLAYER_NOT_CONNECTED
    assert out[tab.OUT_TRACK] == "t1"  # A7 still gets the new song's id


def test_render_hands_play_now_add_to_queue_and_the_track_id_to_the_integration(library: Library) -> None:
    demo, handles = _demo(library)
    assert handles.play_now is _by_id(demo, "gen-play-now")
    assert handles.add_to_queue is _by_id(demo, "gen-add-to-queue")
    assert isinstance(handles.track_id, gr.State)
    assert _by_id(demo, "gen-play-note").visible is False
    generate = _run_for(demo, "gen-button")
    assert _by_id(demo, "gen-play-note")._id in {c._id for c in generate.outputs}


def test_the_cover_offers_download_and_fullscreen_but_no_share_link(library: Library) -> None:
    demo, _ = _demo(library)
    buttons = _by_id(demo, "gen-cover").buttons
    assert "share" not in buttons
    assert set(buttons) == {"download", "fullscreen"}


# ---- the cover, looked up by track_id ----------------------------------------------------------------


def _track(library: Library, make_track, **overrides) -> Track:
    _audio(library, "runtime/generated/abc123.mp3")
    return library.add(make_track(id="t1", **overrides))


SOON = datetime(2026, 10, 19, 12, 0, 5, tzinfo=UTC)  # make_track's song was made at 12:00:00
LATE = datetime(2026, 10, 19, 12, 2, 0, tzinfo=UTC)


def test_cover_shows_the_placeholder_while_it_is_painted(library: Library, make_track) -> None:
    _track(library, make_track)
    view = tab.cover_view("t1", library=library, jobs=JobStore(), now=SOON)
    assert Path(view.path) == art.placeholder_path()
    assert view.note == art.COVER_STAGE
    assert view.done is False
    assert view.failed is False


def test_cover_shows_the_cover_when_ready(library: Library, make_track, tmp_path: Path) -> None:
    _track(library, make_track)
    (tmp_path / "runtime" / "generated" / "t1.jpg").write_bytes(b"\xff\xd8fake")
    library.attach_cover("t1", "runtime/generated/t1.jpg", "a lake")
    view = tab.cover_view("t1", library=library, jobs=JobStore())
    assert Path(view.path) == tmp_path / "runtime" / "generated" / "t1.jpg"
    assert view.note == ""
    assert view.done is True


def test_a_failed_cover_keeps_the_song_and_says_so(library: Library, make_track) -> None:
    _track(library, make_track)
    jobs = JobStore()
    job = jobs.create("cover", art.COVER_STAGE)
    jobs.set_stage(job.id, art.COVER_STAGE, "t1")
    jobs.fail(job.id, ServiceError("flux", "unavailable", "connection refused"))
    view = tab.cover_view("t1", library=library, jobs=jobs)
    assert Path(view.path) == art.placeholder_path()
    assert "unreachable" in view.note
    assert "song is safe" in view.note
    assert view.done is True
    assert view.failed is True
    assert tab.cover_updates(view)[3]["visible"] is True  # Retry cover


def test_the_cover_check_stops_once_the_cover_is_settled(library: Library, make_track) -> None:
    _track(library, make_track)
    jobs = JobStore()
    out = tab.cover_updates(tab.cover_view("t1", library=library, jobs=jobs, now=SOON))
    assert out[2]["active"] is True
    job = jobs.create("cover", art.COVER_STAGE)
    jobs.set_stage(job.id, art.COVER_STAGE, "t1")
    jobs.fail(job.id, "boom")
    out = tab.cover_updates(tab.cover_view("t1", library=library, jobs=jobs))
    assert out[2]["active"] is False


def test_no_cover_job_after_a_minute_shows_a_failed_cover_with_retry(library: Library, make_track) -> None:
    """Felipe's and Dillon's reviews of #48: with no cover job at all, the card waited forever."""
    _track(library, make_track)
    view = tab.cover_view("t1", library=library, jobs=JobStore(), now=LATE)
    assert view.done is True and view.failed is True
    assert GENERIC_FAILURE in view.note and "song is safe" in view.note
    out = tab.cover_updates(view)
    assert out[2]["active"] is False
    assert out[3]["visible"] is True


def test_retry_cover_is_hidden_while_painting_and_once_the_cover_is_there(
    library: Library, make_track, tmp_path: Path
) -> None:
    _track(library, make_track)
    painting = tab.cover_view("t1", library=library, jobs=JobStore(), now=SOON)
    assert tab.cover_updates(painting)[3]["visible"] is False
    (tmp_path / "runtime" / "generated" / "t1.jpg").write_bytes(b"\xff\xd8fake")
    library.attach_cover("t1", "runtime/generated/t1.jpg", "a lake")
    assert tab.cover_updates(tab.cover_view("t1", library=library, jobs=JobStore()))[3]["visible"] is False


def test_retry_cover_restarts_the_cover_and_the_check(library: Library, make_track) -> None:
    """Felipe's review of #48: a failed cover needs a Retry cover button (7.3, 8.2)."""
    _track(library, make_track)
    started: list[str] = []
    demo, _ = _demo(library, start_cover=lambda track: started.append(track.id))
    retry_cover = _fn_for(demo, "gen-retry-cover", "click").fn
    out = retry_cover("t1")
    assert started == ["t1"]
    assert out[1]["value"] == art.COVER_STAGE
    assert out[2]["active"] is True
    assert out[3]["visible"] is False
    out = retry_cover(None)  # no song on the card: nothing to repaint
    assert started == ["t1"]
    assert out[2]["active"] is False


def test_a_double_click_on_retry_cover_starts_one_cover(
    library: Library, make_track, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent review: the button hides only after the first reply, so a double click started two FLUX jobs."""
    jobs = JobStore()
    monkeypatch.setattr(art, "_cover_jobs", jobs)
    _track(library, make_track)
    started: list[str] = []

    def hook(track: Track) -> None:  # records a running job the way art.start_cover does
        started.append(track.id)
        job = jobs.create("cover", art.COVER_STAGE)
        jobs.set_stage(job.id, art.COVER_STAGE, track.id)

    demo, _ = _demo(library, start_cover=hook)
    retry_cover = _fn_for(demo, "gen-retry-cover", "click").fn
    first, second = retry_cover("t1"), retry_cover("t1")
    assert started == ["t1"]
    for out in (first, second):
        assert out[1]["value"] == art.COVER_STAGE
        assert out[2]["active"] is True


def test_the_result_card_offers_retry_cover_only_when_the_cover_failed() -> None:
    painting = tab.GenerateView(status="", running=False, track_id="t1", cover=tab.CoverView("p", "x", False))
    failed = tab.GenerateView(
        status="", running=False, track_id="t1", cover=tab.CoverView("p", "x", True, failed=True)
    )
    assert tab.updates(painting)[tab.OUT_RETRY_COVER]["visible"] is False
    assert tab.updates(failed)[tab.OUT_RETRY_COVER]["visible"] is True


def _wait_for(check, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def test_the_default_cover_hook_saves_the_cover_into_the_tabs_own_library(
    library: Library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Felipe's review of #48: nothing ran render()'s default start_cover through to a cover on the card."""
    monkeypatch.setattr(art, "_cover_jobs", JobStore())
    monkeypatch.setattr(art, "_paint", lambda track, **_kw: ("a lake at dusk", b"\xff\xd8fake-jpeg"))
    demo, _ = _demo(library, run=FakeRun(library, track_id="t-cover"))
    list(_run_for(demo, "gen-button").fn("pop", "", "upbeat", 60, tab.VOCAL, ""))
    assert _wait_for(lambda: bool(library.get("t-cover").cover_path))
    view = tab.cover_view("t-cover", library=library)
    assert Path(view.path) == tmp_path / "runtime" / "generated" / "t-cover.jpg"
    assert view.done is True and view.failed is False


def test_the_default_cover_hook_shows_a_failed_cover_on_the_card(
    library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(art, "_cover_jobs", JobStore())

    def unreachable(track, **_kw):
        raise ServiceError("flux", "unavailable", "connection refused")

    monkeypatch.setattr(art, "_paint", unreachable)
    demo, _ = _demo(library, run=FakeRun(library, track_id="t-nocover"))
    list(_run_for(demo, "gen-button").fn("pop", "", "upbeat", 60, tab.VOCAL, ""))
    assert _wait_for(lambda: tab.cover_view("t-nocover", library=library).failed)
    view = tab.cover_view("t-nocover", library=library)
    assert "unreachable" in view.note
    assert tab.cover_updates(view)[3]["visible"] is True


def test_a_refused_requests_reason_is_shown_as_plain_text(library: Library) -> None:
    """Felipe's nit on #48: the reason went into the Markdown status unescaped."""
    error = ServiceError("acestep", "bad_request", reason="use *this* [link](http://x)")
    last = views(library, FakeRun(library, fail=error))[-1]
    assert "\\*this\\*" in last.status
    assert "[link](http://x)" not in last.status
    assert "change them" in last.status  # still recognised as "edit your inputs"


def test_closing_the_page_mid_run_still_saves_the_song(library: Library) -> None:
    """Mike's question on #48: the worker must keep going after the browser stops listening."""
    release = threading.Event()

    def slow(**kwargs) -> Iterator[Job]:
        for job in FakeRun(library)(**kwargs):
            yield job
            if job.stage == songs.STAGE_MUSIC:
                release.wait(5)

    gen = tab.generate(
        **FORM, library=library, run=slow, clock=counting_clock(), tick_s=0.01, start_cover=None
    )
    next(gen)  # the first update reaches the page, then the tab is closed
    gen.close()
    release.set()
    assert _wait_for(lambda: library.get("t1") is not None)


def test_cover_for_an_unknown_track_stops_quietly(library: Library) -> None:
    view = tab.cover_view(None, library=library, jobs=JobStore())
    assert view.done is True


# ---- B8 warnings, before Generate is clicked -----------------------------------------------------------


def test_style_and_theme_warnings_show_before_generate() -> None:
    assert "Taylor Swift" in tab.style_note("pop", "in the style of Taylor Swift")
    assert "never imitate real artists" in tab.style_note("pop", "in the style of Taylor Swift")
    assert tab.style_note("pop", "warm pads") == ""
    assert "Adele" in tab.theme_note("a breakup song in the style of Adele")
    assert tab.theme_note("a road trip") == ""
    assert tab.theme_note(None) == ""


def test_the_warnings_update_as_the_user_types(library: Library) -> None:
    demo, _ = _demo(library)
    for elem_id in ("gen-genre", "gen-extra"):
        fn = _fn_for(demo, elem_id, "change")
        assert _by_id(demo, "gen-style-note")._id in {c._id for c in fn.outputs}
    fn = _fn_for(demo, "gen-theme", "change")
    assert _by_id(demo, "gen-theme-note")._id in {c._id for c in fn.outputs}


# ---- end to end, and the model rule ------------------------------------------------------------------

HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}


@pytest.fixture
def live_like(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    values = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in PORTS.items():
        values[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    config = load_config(env=values, env_file=tmp_path / "missing-file")
    q = QwenClient(config, sleep=lambda _s: None)
    a = AceStepClient(config, sleep=lambda _s: None)
    monkeypatch.setattr(qwen, "_default", q)
    monkeypatch.setattr(acestep, "_default", a)
    yield Library(root=tmp_path)
    q.close()
    a.close()


@respx.mock
def test_generate_end_to_end_with_mocked_services(live_like: Library, tmp_path: Path) -> None:
    reply = {"title": "Open Road", "lyrics": LYRICS}
    respx.post(f"http://{HOST}:9001/v1/chat/completions").respond(
        200,
        json={"choices": [{"index": 0, "message": {"content": json.dumps(reply)}, "finish_reason": "stop"}]},
    )
    ace = f"http://{HOST}:9007"
    file_ref = f"/v1/audio?path={quote('/srv/acestep/tmp/abc.mp3', safe='')}"
    result = json.dumps([{"file": file_ref, "status": 1, "dit_model": "acestep-v15-xl-turbo"}])
    respx.post(f"{ace}/release_task").respond(200, json={"data": {"task_id": "task-1"}})
    respx.post(f"{ace}/query_result").respond(
        200, json={"data": [{"task_id": "task-1", "status": 1, "result": result}]}
    )
    respx.get(url__startswith=f"{ace}/v1/audio").respond(200, content=b"ID3fake" * 10)

    covers: list[str] = []
    last = list(
        tab.generate(
            **{**FORM, "duration_s": 30},
            library=live_like,
            run=songs.generate_song,
            clock=counting_clock(),
            tick_s=0.01,
            start_cover=lambda track: covers.append(track.id),
        )
    )[-1]
    assert last.failed is False, last.status
    track = live_like.get(last.track_id)
    assert track.title == last.title == "Open Road"
    assert live_like.resolve(track.audio_path).is_file()
    assert covers == [track.id]


def test_tab_imports_no_model_client() -> None:
    source = (ROOT / "jukebox" / "ui" / "generate_tab.py").read_text(encoding="utf-8")
    assert "jukebox.clients" not in source
    assert "httpx" not in source


# ---- Surprise me: random form values (proposal on #3, lane C prototype) -----------------------------


def test_surprise_picks_only_values_the_form_accepts() -> None:
    rng = random.Random(7)
    for _ in range(200):
        genre, extra, mood, duration, song_type, theme = tab.surprise(rng)
        assert genre in tab.GENRES
        assert extra == ""  # fresh choices: the user's own extra tags are cleared
        assert mood in tab.MOODS
        assert tab.SURPRISE_MIN_S <= duration <= tab.SURPRISE_MAX_S
        assert duration % tab.DURATION_STEP_S == 0
        assert song_type in (tab.VOCAL, tab.INSTRUMENTAL)
        assert theme in tab.SURPRISE_IDEAS


def test_surprise_varies_and_includes_both_vocal_and_instrumental() -> None:
    rng = random.Random(11)
    picks = [tab.surprise(rng) for _ in range(60)]
    assert len({p[0] for p in picks}) > 3 and len({p[2] for p in picks}) > 3
    assert {p[4] for p in picks} == {tab.VOCAL, tab.INSTRUMENTAL}


def test_surprise_is_reproducible_with_the_same_seed() -> None:
    assert tab.surprise(random.Random(3)) == tab.surprise(random.Random(3))


def test_surprise_lengths_stay_where_vocal_songs_sound_good() -> None:
    assert tab.SURPRISE_MIN_S >= 30 and tab.SURPRISE_MAX_S <= tab.MAX_DURATION_S


def test_surprise_ideas_are_original_and_pass_the_artist_screen() -> None:
    assert len(tab.SURPRISE_IDEAS) >= 10
    for idea in tab.SURPRISE_IDEAS:
        assert len(idea) <= tab.MAX_THEME_CHARS
        assert songs.check_theme(idea).text == idea, idea  # B8 removes nothing


def test_the_surprise_button_fills_exactly_the_six_form_fields(library: Library) -> None:
    demo, _ = _demo(library)
    button = _by_id(demo, "gen-surprise")
    assert button.value == "Surprise me"
    fn = _fn_for(demo, "gen-surprise", "click")
    assert [o.elem_id for o in fn.outputs] == [
        "gen-genre", "gen-extra", "gen-mood", "gen-duration", "gen-type", "gen-theme",
        "gen-status", "gen-retry",
    ]  # fmt: skip
    assert fn.inputs == []  # it never reads or sends the user's text anywhere


def test_surprise_clears_an_old_failure_so_retry_cannot_use_the_new_choices() -> None:
    # After a failure the status says "your choices are kept: press Retry". Once Surprise me
    # replaces those choices, that line and the Retry button would be wrong, so both go.
    values = tab.on_surprise(random.Random(7))
    assert values[:6] == tab.surprise(random.Random(7))
    assert values[6] == ""
    assert values[7]["visible"] is False
    assert len(values) == 8


# ---- More like this: a Library song fills the form (proposal on #3) ---------------------------------


def _like(make_track, **fields) -> tuple:
    return tab.like(make_track(**fields))


def _song(library: Library, make_track, track_id: str = "m1", **fields) -> None:
    """A song in the library, with a stand-in audio file (the library checks that it exists)."""
    audio = f"runtime/generated/{track_id}.mp3"
    path = library.resolve(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    library.add(make_track(id=track_id, audio_path=audio, **fields))


def test_like_keeps_a_listed_style_and_moves_the_other_tags_to_extra(make_track) -> None:
    got = _like(
        make_track,
        style="lo-fi hip hop, jazzy keys, vinyl crackle",
        mood="mellow",
        theme="late-night study session",
        duration_s=60,
        vocal=False,
        lyrics=None,
    )
    assert got == (
        "lo-fi hip hop",
        "jazzy keys, vinyl crackle",
        "mellow",
        60,
        tab.INSTRUMENTAL,
        "late-night study session",
    )


@pytest.mark.parametrize(
    ("style", "genre", "extra"),
    [
        ("upbeat pop, summery, bright synths", "pop", "upbeat pop, summery, bright synths"),
        ("cinematic folk, acoustic guitar", "folk", "cinematic folk, acoustic guitar"),
        ("dreamy lo-fi hip hop beat, rain", "lo-fi hip hop", "dreamy lo-fi hip hop beat, rain"),
        ("Jazz, brushed drums", "jazz", "brushed drums"),
        ("synth, pop, bright", "pop", "synth, bright"),  # a tag that is the style itself is not repeated
        ("smooth r&b, late night", "R&B", "smooth r&b, late night"),
        ("strings, warm country guitar", "country", "strings, warm country guitar"),
        ("cinematic score, strings", None, "cinematic score, strings"),
        ("popcorn synth, bubbly", None, "popcorn synth, bubbly"),  # "pop" inside a word is not the style
    ],
)
def test_like_finds_the_listed_style_in_a_songs_tags(
    make_track, style: str, genre: str | None, extra: str
) -> None:
    got = _like(make_track, style=style)
    assert (got[0], got[1]) == (genre, extra)


def test_like_leaves_a_mood_that_is_not_in_the_list_unset(make_track) -> None:
    assert _like(make_track, mood="joyful")[2] is None
    assert _like(make_track, mood="Dreamy")[2] == "dreamy"


@pytest.mark.parametrize(("seconds", "expected"), [(3, 10), (62, 60), (63, 65), (300, 120)])
def test_like_fits_the_length_to_the_slider(make_track, seconds: int, expected: int) -> None:
    assert _like(make_track, duration_s=seconds)[3] == expected


def test_like_trims_long_tags_and_ideas_to_what_the_boxes_accept(make_track) -> None:
    tags = ", ".join(f"tag{n:03d}" for n in range(40))
    got = _like(make_track, style=f"pop, {tags}", theme="x" * 300)
    assert len(got[1]) <= tab.MAX_EXTRA_CHARS
    assert all(len(t.strip()) == 6 for t in got[1].split(","))  # whole tags only, never cut mid-tag
    assert len(got[5]) == tab.MAX_THEME_CHARS
    assert _like(make_track, theme=None)[5] == ""


def test_more_like_this_fills_the_form_says_so_and_opens_the_generate_tab(
    library: Library, make_track
) -> None:
    _song(
        library,
        make_track,
        title="Night *Drive*",
        style="jazz, brushes",
        mood="dreamy",
        theme="a city",
        duration_s=45,
    )
    out = tab.more_like_this(library, "m1", running=False)
    assert out[:6] == ("jazz", "brushes", "dreamy", 45, tab.VOCAL, "a city")
    assert r"Night \*Drive\*" in out[6]  # the title is shown as plain text
    assert "Generate" in out[6]
    assert out[7]["visible"] is False  # an old Retry would send these new choices
    assert out[8]["selected"] == tab.TAB_ID
    assert len(out) == 9


def test_more_like_this_keeps_the_mood_when_the_songs_mood_is_not_listed(
    library: Library, make_track
) -> None:
    _song(library, make_track, mood="joyful")
    out = tab.more_like_this(library, "m1", running=False)
    assert out[2] == gr.skip()
    assert "joyful" in out[6]


@pytest.mark.parametrize(("track_id", "running"), [("m1", True), (None, False), ("", False), ("gone", False)])
def test_more_like_this_changes_nothing_while_running_or_without_a_song(
    library: Library, make_track, monkeypatch: pytest.MonkeyPatch, track_id: str | None, running: bool
) -> None:
    _song(library, make_track)
    shown: list[str] = []
    monkeypatch.setattr(tab.gr, "Warning", lambda message, *a, **k: shown.append(message))
    out = tab.more_like_this(library, track_id, running=running)
    assert out == (gr.skip(),) * 9
    assert shown == [tab.LIKE_BUSY if running else tab.LIKE_PICK]


def test_generate_keeps_a_running_flag_for_more_like_this(library: Library) -> None:
    demo, handles = _demo(library)
    outputs = _run_for(demo, "gen-button").outputs
    assert outputs[tab.OUT_RUNNING] is handles.running
    assert tab.updates(tab.GenerateView(status="", running=True))[tab.OUT_RUNNING] is True
    assert tab.updates(tab.GenerateView(status="", running=False))[tab.OUT_RUNNING] is False


def test_more_like_this_is_wired_to_the_form_status_retry_and_tabs(library: Library) -> None:
    with gr.Blocks() as demo:
        with gr.Tabs() as tabs:
            with gr.Tab("Generate", id=tab.TAB_ID):
                handles = tab.render(library=library)
        pick = gr.Radio(["a"], elem_id="x-list")
        more = gr.Button("More", elem_id="x-more")
        handles.connect_more_like_this(more, pick, tabs)
    fn = _fn_for(demo, "x-more", "click")
    assert [getattr(o, "elem_id", None) for o in fn.outputs[:8]] == [
        "gen-genre", "gen-extra", "gen-mood", "gen-duration", "gen-type", "gen-theme", "gen-status", "gen-retry",
    ]  # fmt: skip
    assert fn.outputs[8] is tabs
    assert fn.inputs[0] is pick  # the id the user can see, read at the click
    assert fn.inputs[1] is handles.running


def test_more_like_this_with_no_tags_does_not_claim_they_were_kept(library: Library, make_track) -> None:
    _song(library, make_track, style=" ")
    out = tab.more_like_this(library, "m1", running=False)
    assert out[0] == gr.skip()
    assert "Extra style tags" not in out[6]


def test_a_generate_click_marks_the_run_at_once_even_while_it_waits_in_the_queue(library: Library) -> None:
    # The run's first update can wait behind other users' songs; More like this and Surprise me must
    # already see it as running, or a failed run would offer Retry with choices it did not use.
    demo, handles = _demo(library)
    for elem_id in ("gen-button", "gen-retry"):
        target = _by_id(demo, elem_id)._id
        raw = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
        clicks = [fn for fn in raw if (target, "click") in [tuple(t) for t in fn.targets]]
        assert len(clicks) == 1, elem_id  # only the mark; the run follows it, never alongside it
        assert not clicks[0].queue
        assert clicks[0].outputs[0] is handles.running
        assert clicks[0].outputs[1] is _by_id(demo, "gen-surprise")
    running, surprise_button = tab.mark_running()
    assert running is True
    assert surprise_button["interactive"] is False


def test_the_run_starts_only_after_the_mark_so_its_last_update_wins(library: Library) -> None:
    # Two independent listeners on one click finish in no fixed order: when the mark landed after the
    # run's last update, Surprise me and More like this stayed off for good (Mike's review of #61).
    demo, handles = _demo(library)
    for elem_id in ("gen-button", "gen-retry"):
        mark = _fn_for(demo, elem_id, "click")
        run = _run_for(demo, elem_id)
        assert run.trigger_after == mark._id
        assert run.queue  # the run still waits its turn; only the mark skips the queue
        assert handles.running in run.outputs and _by_id(demo, "gen-surprise") in run.outputs


def test_after_a_run_the_tab_is_no_longer_running(library: Library) -> None:
    demo, handles = _demo(library)
    run = _run_for(demo, "gen-button")
    last = list(run.fn("pop", "", "upbeat", 60, tab.VOCAL, ""))[-1]
    assert last[run.outputs.index(handles.running)] is False
    assert last[run.outputs.index(_by_id(demo, "gen-surprise"))]["interactive"] is True


def test_the_help_mentions_more_like_this() -> None:
    assert "More like this" in tab.HELP
