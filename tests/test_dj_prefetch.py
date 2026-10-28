"""Tests for the DJ prefetch in jukebox/services/dj.py (task D5).

Each test builds its own Prefetcher, saving into tmp_path. Qwen and Chatterbox are faked, or mocked
at the HTTP level with respx; no real class service is ever called.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.chatterbox as chatterbox  # noqa: E402
import jukebox.clients.qwen as qwen  # noqa: E402
import jukebox.services.dj as dj  # noqa: E402
from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402
from jukebox.services.player import DJ_UNAVAILABLE, Player  # noqa: E402

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
ONE = SimpleNamespace(id="t1", title="Midnight Lanterns", style="acoustic folk", mood="mellow", theme="home")
TWO = SimpleNamespace(id="t2", title="Sunset Gearshift", style="synth-pop", mood="upbeat", theme=None)
GOOD = (
    "You're locked in to the AI Jukebox. We're slowing it down now with Midnight Lanterns, "
    "a mellow acoustic folk tune with gentle fingerpicked guitar about finding your way home. Settle in."
)


class FakeMake:
    """Stands in for dj.make_clip: writes a small file, optionally waits for a gate, or fails."""

    def __init__(
        self, tmp_path: Path, *, gate: threading.Event | None = None, error: Exception | None = None
    ):
        self.tmp_path = tmp_path
        self.gate = gate
        self.error = error
        self.calls: list[dict] = []
        self.started = threading.Event()  # set once the worker is inside a call

    def __call__(self, track, *, voice_ref_path=None, previous=None, out_dir=None):
        self.calls.append(
            {"track": track.id, "voice": voice_ref_path, "previous": getattr(previous, "id", None)}
        )
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(5), "the test never released the clip"
        if self.error is not None:
            raise self.error
        key = dj.voice_key(voice_ref_path)
        path = Path(out_dir) / f"dj_{track.id}_{key}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(MP3)
        return dj.DjClip(track_id=track.id, voice_key=key, script=GOOD, audio_path=path)


@pytest.fixture
def voice_holder() -> list[str | None]:
    """The voice the prefetcher sees: [None] is the default voice; tests swap the one entry."""
    return [None]


@pytest.fixture
def make(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def install(**kwargs) -> FakeMake:
        fake = FakeMake(tmp_path, **kwargs)
        monkeypatch.setattr(dj, "make_clip", fake)
        return fake

    return install


class Clock:
    """A clock the test moves by hand, for the cooldown after a failed intro."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _prefetcher(tmp_path: Path, voice_holder: list[str | None], **kwargs) -> dj.Prefetcher:
    return dj.Prefetcher(voice=lambda: voice_holder[0], out_dir=tmp_path / "gen", **kwargs)


def _recording(tmp_path: Path, name: str, content: bytes) -> str:
    path = tmp_path / "uploads" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def _real_clients(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://class.example:{port}"
    cfg = load_config(env=env, env_file=tmp_path / "missing-file")
    monkeypatch.setattr(qwen, "_default", qwen.QwenClient(cfg, sleep=lambda s: None))
    monkeypatch.setattr(
        chatterbox, "_new_client", lambda: ServiceClient("chatterbox", cfg, sleep=lambda s: None)
    )


def _qwen_reply(text: str) -> httpx.Response:
    choice = {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
    return httpx.Response(200, json={"choices": [choice]})


# ---- background, no waiting --------------------------------------------------------------------


def test_prefetch_returns_at_once_and_the_clip_appears_in_the_background(
    tmp_path: Path, voice_holder, make
) -> None:
    gate = threading.Event()
    fake = make(gate=gate)
    prefetcher = _prefetcher(tmp_path, voice_holder)
    started = time.monotonic()
    job = prefetcher.prefetch(ONE)
    assert time.monotonic() - started < 0.5  # the caller (a player event) never waits for the DJ
    assert prefetcher.clips.get("t1") is None
    gate.set()
    job.result(timeout=5)
    assert Path(prefetcher.clips["t1"]).read_bytes() == MP3
    assert fake.calls == [{"track": "t1", "voice": None, "previous": None}]


def test_the_player_plays_a_prefetched_clip_without_waiting(tmp_path: Path, voice_holder, make) -> None:
    make()
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE, previous=TWO).result(timeout=5)
    player = Player({"t1": str(tmp_path / "t1.wav")}, prefetcher.clips)
    player.enqueue("t1")
    item = player.next_item()
    assert (item.kind, item.audio_path) == ("dj", prefetcher.clips["t1"])
    assert player.notice is None


# ---- cache by (track_id, voice) ----------------------------------------------------------------


def test_the_cache_is_keyed_by_track_and_voice(tmp_path: Path, voice_holder, make) -> None:
    fake = make()
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    default_clip = prefetcher.clips["t1"]

    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", b"voice A")
    assert prefetcher.clips.get("t1") is None  # a new voice invalidates the old clip
    prefetcher.prefetch(ONE).result(timeout=5)
    custom_clip = prefetcher.clips["t1"]
    assert custom_clip != default_clip

    voice_holder[0] = None
    assert prefetcher.clips["t1"] == default_clip  # back to the default: the old clip is reused
    assert prefetcher.prefetch(ONE) is None  # and nothing new is made
    assert [c["voice"] for c in fake.calls] == [None, _recording(tmp_path, "voice_a.mp3", b"voice A")]


def test_the_same_clip_is_never_made_twice(tmp_path: Path, voice_holder, make) -> None:
    gate = threading.Event()
    fake = make(gate=gate)
    prefetcher = _prefetcher(tmp_path, voice_holder)
    first = prefetcher.prefetch(ONE)
    assert prefetcher.prefetch(ONE) is None  # already being made
    gate.set()
    first.result(timeout=5)
    assert prefetcher.prefetch(ONE) is None  # already made
    assert len(fake.calls) == 1


# ---- failures skip the DJ clip -----------------------------------------------------------------


@respx.mock
def test_a_qwen_failure_skips_the_dj_clip_and_the_song_plays_with_a_notice(
    tmp_path: Path, voice_holder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_clients(monkeypatch, tmp_path)
    respx.post("http://class.example:9001/v1/chat/completions").mock(return_value=httpx.Response(500))
    speech = respx.post("http://class.example:9008/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=MP3)
    )
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)  # never raises into the player
    assert prefetcher.clips.get("t1") is None
    assert not speech.called  # no script, so nothing is spoken
    player = Player({"t1": str(tmp_path / "t1.wav")}, prefetcher.clips)
    player.enqueue("t1")
    item = player.next_item()
    assert item.kind == "song"
    assert player.notice == DJ_UNAVAILABLE


@respx.mock
def test_a_chatterbox_failure_never_falls_back_to_another_voice(
    tmp_path: Path, voice_holder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_clients(monkeypatch, tmp_path)
    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", MP3)
    chat = respx.post("http://class.example:9001/v1/chat/completions").mock(return_value=_qwen_reply(GOOD))
    speech = respx.post("http://class.example:9008/v1/audio/speech").mock(return_value=httpx.Response(500))
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    assert prefetcher.clips.get("t1") is None
    assert chat.called and speech.called
    bodies = [json.loads(call.request.content) for call in speech.calls]
    assert all("ref_audio" in body for body in bodies)  # never retried with the default voice
    assert {body["model"] for body in bodies} == {"chatterbox-v3"}  # never another model
    assert not any((tmp_path / "gen").glob("*"))  # nothing half-written


def test_a_disk_error_skips_the_dj_clip(tmp_path: Path, voice_holder, make) -> None:
    make(error=OSError("disk full"))
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    assert prefetcher.clips.get("t1") is None


def test_a_failed_clip_is_tried_again_once_the_cooldown_has_passed(
    tmp_path: Path, voice_holder, make
) -> None:
    fake = make(error=ServiceError("chatterbox", "unavailable", "The chatterbox service is unreachable."))
    clock = Clock()
    prefetcher = _prefetcher(tmp_path, voice_holder, clock=clock, cooldown_s=30)
    prefetcher.prefetch(ONE).result(timeout=5)
    fake.error = None
    clock.now += 31
    prefetcher.prefetch(ONE).result(timeout=5)
    assert prefetcher.clips.get("t1") is not None
    assert len(fake.calls) == 2


def test_a_failed_clip_is_not_asked_for_again_within_the_cooldown(tmp_path: Path, voice_holder, make) -> None:
    """A reload or a skip against a broken class server must not queue the same failing calls again."""
    fake = make(error=ServiceError("qwen", "timeout", "The qwen service took too long to respond."))
    clock = Clock()
    prefetcher = _prefetcher(tmp_path, voice_holder, clock=clock, cooldown_s=30)
    prefetcher.prefetch(ONE).result(timeout=5)
    clock.now += 29
    assert prefetcher.prefetch(ONE) is None  # still cooling down: no new job, no Qwen or TTS call
    assert len(fake.calls) == 1
    clock.now += 2
    assert prefetcher.prefetch(ONE) is not None  # cooldown over


def test_a_failure_only_cools_down_that_song_and_that_voice(tmp_path: Path, voice_holder, make) -> None:
    fake = make(error=ServiceError("chatterbox", "unavailable", "The chatterbox service is unreachable."))
    clock = Clock()
    prefetcher = _prefetcher(tmp_path, voice_holder, clock=clock, cooldown_s=30)
    prefetcher.prefetch(ONE).result(timeout=5)
    fake.error = None
    prefetcher.prefetch(TWO).result(timeout=5)  # another song is not held back
    assert prefetcher.clips.get("t2") is not None
    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", b"voice A")
    assert prefetcher.prefetch(ONE) is not None  # the same song in another voice is a different intro


def test_a_voice_recording_that_is_gone_skips_the_dj_clip(tmp_path: Path, voice_holder, make) -> None:
    """The voice was replaced (its old file deleted) between the click and the prefetch."""
    fake = make()
    voice_holder[0] = str(tmp_path / "uploads" / "voice_gone.wav")
    prefetcher = _prefetcher(tmp_path, voice_holder)
    assert prefetcher.clips.get("t1") is None
    assert prefetcher.prefetch(ONE) is None  # nothing to make an intro with, and no other voice
    assert fake.calls == []


def test_a_voice_change_during_prefetch_never_files_the_old_voice_under_the_new_one(
    tmp_path: Path, make
) -> None:
    """The voice is read once per prefetch, so the job's recording and its cache key always match."""
    fake = make()
    old = _recording(tmp_path, "voice_old.mp3", b"old voice")
    new = _recording(tmp_path, "voice_new.mp3", b"new voice")
    reads = iter([old])  # the first read sees the old voice; every later read sees the new one
    prefetcher = dj.Prefetcher(voice=lambda: next(reads, new), out_dir=tmp_path / "gen")
    prefetcher.prefetch(ONE).result(timeout=5)
    # The job belongs to the old voice, which is no longer in use: it's skipped, not filed under the
    # new voice (before the fix, the old recording was spoken and cached as the new voice's intro).
    assert fake.calls == []
    assert prefetcher.clips.get("t1") is None


def test_an_intro_queued_for_a_voice_no_longer_in_use_is_skipped(tmp_path: Path, voice_holder, make) -> None:
    gate = threading.Event()
    fake = make(gate=gate)
    prefetcher = _prefetcher(tmp_path, voice_holder)
    busy = prefetcher.prefetch(TWO)
    assert fake.started.wait(5)  # the worker is inside this one before the voice changes
    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", b"voice A")
    stale = prefetcher.prefetch(ONE)  # queued for voice A
    voice_holder[0] = None  # the user resets before it starts
    gate.set()
    busy.result(timeout=5)
    assert stale.result(timeout=5) is None
    assert [c["track"] for c in fake.calls] == ["t2"]  # no Qwen or Chatterbox call for a voice gone
    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", b"voice A")
    assert prefetcher.prefetch(ONE) is not None  # and it can be asked for again later


def test_an_unexpected_error_is_logged_and_the_next_intro_still_gets_made(
    tmp_path: Path, voice_holder, make, caplog: pytest.LogCaptureFixture
) -> None:
    fake = make(error=ValueError("a bug"))
    prefetcher = _prefetcher(tmp_path, voice_holder)
    with caplog.at_level("WARNING", logger="jukebox.services.dj"):
        assert prefetcher.prefetch(ONE).result(timeout=5) is None
    assert "DJ intro skipped: ValueError" in caplog.text
    assert "a bug" not in caplog.text  # the type only, never the message
    fake.error = None
    prefetcher.prefetch(TWO).result(timeout=5)
    assert prefetcher.clips.get("t2") is not None


def test_an_error_while_checking_the_voice_never_stops_the_worker(tmp_path: Path, make) -> None:
    """Something unexpected in the worker's voice check fails that job only; later intros still come."""
    fake = make()
    reads = {"n": 0}

    def voice() -> str | None:
        reads["n"] += 1
        if reads["n"] == 2:  # the worker's check, after prefetch's own read
            raise RuntimeError("a bug")
        return None

    prefetcher = dj.Prefetcher(voice=voice, out_dir=tmp_path / "gen")
    with pytest.raises(RuntimeError):
        prefetcher.prefetch(ONE).result(timeout=5)
    assert prefetcher.prefetch(ONE).result(timeout=5) is None  # not stuck as "being made"
    assert prefetcher.clips.get("t1") is not None
    assert [c["track"] for c in fake.calls] == ["t1"]


def test_an_error_in_the_worker_outside_the_clip_is_logged_by_type_only(
    tmp_path: Path, make, caplog: pytest.LogCaptureFixture
) -> None:
    """The job's Future is thrown away by the caller, so the worker must log what it caught."""
    make()
    reads = {"n": 0}

    def voice() -> str | None:
        reads["n"] += 1
        if reads["n"] == 2:  # the worker's check, after prefetch's own read
            raise RuntimeError("a secret path /home/x")
        return None

    prefetcher = dj.Prefetcher(voice=voice, out_dir=tmp_path / "gen")
    with caplog.at_level("WARNING", logger="jukebox.services.dj"):
        with pytest.raises(RuntimeError):
            prefetcher.prefetch(ONE).result(timeout=5)
    assert "DJ prefetch failed: RuntimeError" in caplog.text
    assert "secret path" not in caplog.text


# ---- songs that are no longer next -------------------------------------------------------------


def test_an_intro_for_a_song_that_is_no_longer_next_is_skipped(tmp_path: Path, voice_holder, make) -> None:
    """Skips pile up while a slow call runs; an intro nobody needs any more must not use the server."""
    gate = threading.Event()
    fake = make(gate=gate)
    prefetcher = _prefetcher(tmp_path, voice_holder)
    busy = prefetcher.prefetch(TWO)
    assert fake.started.wait(5)
    next_up = {"t1": True}
    stale = prefetcher.prefetch(ONE, still_wanted=lambda: next_up["t1"])
    next_up["t1"] = False  # the listener skipped past it while it waited
    gate.set()
    busy.result(timeout=5)
    assert stale.result(timeout=5) is None
    assert [c["track"] for c in fake.calls] == ["t2"]  # no Qwen or Chatterbox call for t1
    assert prefetcher.clips.get("t1") is None
    assert prefetcher.prefetch(ONE) is not None  # a skipped job is not "being made" or a failure


def test_an_intro_for_a_song_that_is_still_next_is_made(tmp_path: Path, voice_holder, make) -> None:
    gate = threading.Event()
    fake = make(gate=gate)
    prefetcher = _prefetcher(tmp_path, voice_holder)
    busy = prefetcher.prefetch(TWO)
    assert fake.started.wait(5)
    wanted = prefetcher.prefetch(ONE, still_wanted=lambda: True)
    gate.set()
    busy.result(timeout=5)
    wanted.result(timeout=5)
    assert [c["track"] for c in fake.calls] == ["t2", "t1"]
    assert prefetcher.clips.get("t1") is not None


def test_a_job_without_a_still_wanted_check_always_runs(tmp_path: Path, voice_holder, make) -> None:
    """The page-load warm-up has no 'next in the queue' to compare with."""
    fake = make()
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    assert [c["track"] for c in fake.calls] == ["t1"]


def test_the_still_wanted_check_runs_without_the_prefetchers_lock(tmp_path: Path, voice_holder, make) -> None:
    """The check reads the player (its own lock); holding ours there could deadlock the two."""
    make()
    prefetcher = _prefetcher(tmp_path, voice_holder)
    could_take_it: list[bool] = []

    def wanted() -> bool:
        # The lock is not reentrant: if this worker thread were already holding it, taking it here
        # would block until the timeout. (Another thread may briefly hold it, so wait a moment.)
        got = prefetcher._lock.acquire(timeout=2)
        could_take_it.append(got)
        if got:
            prefetcher._lock.release()
        return True

    prefetcher.prefetch(ONE, still_wanted=wanted).result(timeout=5)
    assert could_take_it == [True]


# ---- the player's clip map ---------------------------------------------------------------------


def test_the_clip_map_lists_only_the_current_voices_clips(tmp_path: Path, voice_holder, make) -> None:
    make()
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    assert list(prefetcher.clips) == ["t1"]
    assert len(prefetcher.clips) == 1
    voice_holder[0] = _recording(tmp_path, "voice_a.mp3", b"voice A")
    assert list(prefetcher.clips) == []  # t1's intro is in the old voice
    assert len(prefetcher.clips) == 0


def test_the_clip_map_takes_a_clip_set_by_hand_for_the_current_voice(tmp_path: Path, voice_holder) -> None:
    """The player panel's tests fill clips by hand; that must keep working."""
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.clips["t1"] = "dj.wav"
    assert prefetcher.clips["t1"] == "dj.wav"
    del prefetcher.clips["t1"]
    assert "t1" not in prefetcher.clips


def test_the_app_has_one_prefetcher_that_follows_the_app_wide_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setting = dj.VoiceSetting()
    monkeypatch.setattr(dj, "VOICE", setting)
    assert isinstance(dj.PREFETCH, dj.Prefetcher)
    assert dj.PREFETCH.voice_path() is None
    setting._path = _recording(tmp_path, "voice_a.mp3", b"voice A")
    assert dj.PREFETCH.voice_path() == setting._path
