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

    def __call__(self, track, *, voice_ref_path=None, previous=None, out_dir=None):
        self.calls.append(
            {"track": track.id, "voice": voice_ref_path, "previous": getattr(previous, "id", None)}
        )
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


def _prefetcher(tmp_path: Path, voice_holder: list[str | None]) -> dj.Prefetcher:
    return dj.Prefetcher(voice=lambda: voice_holder[0], out_dir=tmp_path / "gen")


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


def test_a_failed_clip_is_tried_again_the_next_time_it_is_asked_for(
    tmp_path: Path, voice_holder, make
) -> None:
    fake = make(error=ServiceError("chatterbox", "unavailable", "The chatterbox service is unreachable."))
    prefetcher = _prefetcher(tmp_path, voice_holder)
    prefetcher.prefetch(ONE).result(timeout=5)
    fake.error = None
    prefetcher.prefetch(ONE).result(timeout=5)
    assert prefetcher.clips.get("t1") is not None
    assert len(fake.calls) == 2


def test_a_voice_recording_that_is_gone_skips_the_dj_clip(tmp_path: Path, voice_holder, make) -> None:
    """The voice was replaced (its old file deleted) between the click and the prefetch."""
    fake = make()
    voice_holder[0] = str(tmp_path / "uploads" / "voice_gone.wav")
    prefetcher = _prefetcher(tmp_path, voice_holder)
    assert prefetcher.clips.get("t1") is None
    assert prefetcher.prefetch(ONE) is None  # nothing to make an intro with, and no other voice
    assert fake.calls == []


# ---- the player's clip map ---------------------------------------------------------------------


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
