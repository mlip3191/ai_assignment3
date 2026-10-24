"""A7 integration: song -> cover -> library -> queue -> DJ clip, with the class services mocked.

Qwen and ACE-Step go through the real clients and respx, FLUX is a fake that can be held back, and every
file lives in a temporary folder. The page code is driven through its plain functions, the same ones the
buttons call, so this checks the wiring between the Generate tab, the Library tab and the player without
a browser. What it cannot show is sound: that needs a human (see the PR's manual smoke test).
"""

from __future__ import annotations

import itertools
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

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
from jukebox.jobs import JobStore  # noqa: E402
from jukebox.library import Library  # noqa: E402
from jukebox.services import art  # noqa: E402
from jukebox.services.player import DJ_UNAVAILABLE  # noqa: E402
from jukebox.ui.library_tab import choices, preview  # noqa: E402
from jukebox.ui.player_panel import (  # noqa: E402
    NOW_PLAYING,
    SPEAKING,
    on_add,
    on_end,
    on_play,
    on_play_now,
    open_player,
)

HOST = "class.example"
ACE = f"http://{HOST}:9007"
QWEN_URL = f"http://{HOST}:9001/v1/chat/completions"
AUDIO = b"ID3\x04fake-mp3-bytes" * 10
IMAGE = b"\xff\xd8\xff\xe0" + b"fake jpeg body"
FORM = {
    "genre": "lo-fi hip hop",
    "extra": "",
    "mood": "mellow",
    "duration_s": 30,
    "song_type": tab.INSTRUMENTAL,
    "theme": "a rainy evening",
}


class FakeFlux:
    """Paints a cover when released. `hold` keeps it waiting, to look at the page in between."""

    def __init__(self, *, fail: ServiceError | None = None, hold: bool = False) -> None:
        self.fail = fail
        self.release = threading.Event()
        if not hold:
            self.release.set()

    def __call__(self, prompt: str, *, seed: int | None = None) -> bytes:
        assert self.release.wait(timeout=10), "the test never released the cover"
        if self.fail:
            raise self.fail
        return IMAGE


def fake_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
    return "A quiet desk in the rain"


def wait_for_cover(track_id: str, timeout: float = 10.0) -> None:
    """Block until the track's cover job has finished (the pipeline starts it on its own thread)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = art.cover_job_for(track_id)
        if job is not None and job.finished_at is not None:
            return
        time.sleep(0.01)
    raise AssertionError("the cover job never finished")


@pytest.fixture(autouse=True)
def fresh_cover_jobs(monkeypatch: pytest.MonkeyPatch) -> JobStore:
    store = JobStore()
    monkeypatch.setattr(art, "_cover_jobs", store)
    return store


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    values = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}.items():
        values[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    config = load_config(env=values, env_file=tmp_path / "missing-file")
    q = QwenClient(config, sleep=lambda _s: None)
    a = AceStepClient(config, sleep=lambda _s: None)
    monkeypatch.setattr(qwen, "_default", q)
    monkeypatch.setattr(acestep, "_default", a)
    (tmp_path / "runtime" / "generated").mkdir(parents=True)
    yield Library(root=tmp_path)
    q.close()
    a.close()


def mock_services(*, acestep_down: bool = False) -> None:
    reply = {"choices": [{"index": 0, "message": {"content": json.dumps({"title": "Rainy Desk"})}}]}
    respx.post(QWEN_URL).respond(200, json=reply)
    if acestep_down:
        respx.post(f"{ACE}/release_task").respond(503, json={"error": "down"})
        return
    file_ref = f"/v1/audio?path={quote('/srv/acestep/tmp/abc.mp3', safe='')}"
    result = json.dumps([{"file": file_ref, "status": 1, "dit_model": "acestep-v15-xl-turbo"}])
    respx.post(f"{ACE}/release_task").respond(200, json={"data": {"task_id": "task-1"}})
    respx.post(f"{ACE}/query_result").respond(
        200, json={"data": [{"task_id": "task-1", "status": 1, "result": result}]}
    )
    respx.get(url__startswith=f"{ACE}/v1/audio").respond(200, content=AUDIO)


def generate_one(library: Library, flux: FakeFlux):
    """Click Generate: returns the last thing the Generate tab shows and the cover threads it started."""
    threads: list[threading.Thread] = []

    def start_cover(track):
        thread = art.start_cover(
            track, library=library, root=library.resolve("."), chat=fake_chat, generate=flux
        )
        threads.append(thread)
        return thread

    counter = itertools.count()
    views = list(
        tab.generate(
            **FORM,
            library=library,
            run=songs.generate_song,
            start_cover=start_cover,
            clock=lambda: float(next(counter)),
            tick_s=0.01,
        )
    )
    return views[-1], threads


@respx.mock
def test_a_new_song_appears_in_the_library_and_can_be_queued_and_played(
    library: Library, tmp_path: Path
) -> None:
    mock_services()
    last, threads = generate_one(library, FakeFlux())
    assert last.failed is False, last.status
    track_id = last.track_id
    assert track_id in [found for _label, found in choices(library)]  # it is in the Library tab

    out = tab.updates(last, player_connected=True)
    assert out[tab.OUT_PLAY_NOW]["interactive"] is True  # the Generate card's buttons light up
    assert out[tab.OUT_ADD]["interactive"] is True

    player = open_player(library, {})
    runtime = tmp_path / "served"
    queued = on_add(player, library, 0, track_id, runtime)
    assert [title for title, _cover in queued.up_next] == ["Rainy Desk"]
    started = on_play(player, library, 0, runtime)
    assert started.label == NOW_PLAYING
    assert started.title == "Rainy Desk"
    assert Path(started.audio).read_bytes() == AUDIO  # the song file that was generated
    wait_for_cover(last.track_id)


@respx.mock
def test_the_cover_shows_up_later_everywhere_without_a_reload(library: Library, tmp_path: Path) -> None:
    mock_services()
    flux = FakeFlux(hold=True)
    last, threads = generate_one(library, flux)
    track_id = last.track_id
    placeholder = str(art.placeholder_path())

    waiting = tab.cover_view(track_id, library=library)
    assert waiting.path == placeholder
    assert waiting.note == art.COVER_STAGE  # "Painting cover…"
    assert waiting.done is False
    assert preview(library, track_id).cover == placeholder
    player = open_player(library, {})
    queued = on_add(player, library, 0, track_id, tmp_path / "served")
    assert queued.up_next[0][1] == placeholder  # the song is queued and playable before its cover exists

    flux.release.set()  # FLUX answers
    wait_for_cover(last.track_id)

    ready = tab.cover_view(track_id, library=library)
    assert ready.done is True
    assert Path(ready.path).is_file()
    assert Path(ready.path) != Path(placeholder)
    assert preview(library, track_id).cover == ready.path  # the Library tab picks it up on its next refresh
    now = on_play_now(player, library, 0, track_id, tmp_path / "served")
    assert now.cover == ready.path  # and so does the player, looked up by the track id


@respx.mock
def test_a_cover_failure_never_takes_the_song_away(library: Library, tmp_path: Path) -> None:
    mock_services()
    flux = FakeFlux(fail=ServiceError("flux", "unavailable", "down"))
    last, threads = generate_one(library, flux)
    wait_for_cover(last.track_id)
    track_id = last.track_id

    view = tab.cover_view(track_id, library=library)
    assert view.failed is True  # the card offers Retry cover
    assert view.path == str(art.placeholder_path())
    assert track_id in [found for _label, found in choices(library)]  # the song is still in the library
    played = on_play_now(open_player(library, {}), library, 0, track_id, tmp_path / "served")
    assert played.title == "Rainy Desk"
    assert Path(played.audio).read_bytes() == AUDIO


@respx.mock
def test_a_failed_song_adds_nothing_and_keeps_the_player_buttons_off(library: Library) -> None:
    mock_services(acestep_down=True)
    last, _threads = generate_one(library, FakeFlux())
    assert last.failed is True
    assert last.track_id is None
    assert choices(library) == []
    out = tab.updates(last, player_connected=True)
    assert out[tab.OUT_PLAY_NOW]["interactive"] is False
    assert out[tab.OUT_ADD]["interactive"] is False
    assert out[tab.OUT_BUTTON]["interactive"] is True  # Generate can be pressed again


@respx.mock
def test_a_dj_clip_plays_before_the_new_song_and_a_missing_one_does_not_stop_it(
    library: Library, tmp_path: Path
) -> None:
    mock_services()
    last, threads = generate_one(library, FakeFlux())
    wait_for_cover(last.track_id)
    track_id = last.track_id
    runtime = tmp_path / "served"

    clip = tmp_path / "dj" / "intro.mp3"
    clip.parent.mkdir()
    clip.write_bytes(b"ID3 dj clip")
    with_dj = open_player(library, {track_id: str(clip)})
    on_add(with_dj, library, 0, track_id, runtime)
    first = on_play(with_dj, library, 0, runtime)
    assert first.label == SPEAKING  # DJ first
    second = on_end(with_dj, library, first.token, first.audio, runtime)
    assert second.label == NOW_PLAYING  # then the song
    assert second.title == "Rainy Desk"

    without_dj = open_player(library, {})
    on_add(without_dj, library, 0, track_id, runtime)
    only_song = on_play(without_dj, library, 0, runtime)
    assert only_song.label == NOW_PLAYING  # no clip: the song still plays
    assert only_song.notice == DJ_UNAVAILABLE
