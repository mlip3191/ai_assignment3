"""E1 playback spike: three local clips, one audio element, stale end events ignored."""

from __future__ import annotations

import struct
import sys
import wave
from importlib.metadata import version
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from playback_spike import (  # noqa: E402
    CLIP_SECONDS,
    LAUNCH,
    advance,
    build_demo,
    event_bindings,
    new_queue,
    play,
    serve_for_browser,
    stamp_playback_started,
    token_from_audio,
    write_clips,
)


def _duration_and_crossings(path: Path) -> tuple[float, int]:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        assert handle.getsampwidth() == 2
        duration = handle.getnframes() / handle.getframerate()
    samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    crossings = 0
    previous = 0
    for sample in samples:
        if previous <= 0 < sample or previous >= 0 > sample:
            crossings += 1
        previous = sample
    return duration, crossings


def test_three_clips_have_distinct_tones_and_known_duration(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    assert len(clips) == 3
    measured = [_duration_and_crossings(clip) for clip in clips]
    for duration, _crossings in measured:
        assert duration == pytest.approx(CLIP_SECONDS, abs=0.01)
    crossings = [item[1] for item in measured]
    assert crossings[0] < crossings[1] < crossings[2]


def test_advance_plays_in_order_then_stops(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    state, step = play(new_queue(clips))
    assert step.status == "playing"
    assert step.index == 0
    assert step.path == clips[0]
    heard = [step.path]
    token = step.token
    for expected in (1, 2):
        state, step = advance(state, token)
        assert step.status == "playing"
        assert step.index == expected
        assert step.path == clips[expected]
        heard.append(step.path)
        token = step.token
    assert heard == list(clips)
    state, step = advance(state, token)
    assert step.status == "finished"
    assert step.path is None
    assert "Queue finished" in step.message
    _state, extra = advance(state, None)
    assert extra.status == "finished"
    assert extra.path is None


def test_skip_during_clip_moves_to_next(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    state, first = play(new_queue(clips))
    state, skipped = advance(state, None)
    assert skipped.status == "playing"
    assert skipped.index == 1
    assert skipped.path == clips[1]
    assert skipped.token != first.token
    assert state.index == 1


def test_stale_end_event_does_not_double_advance(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    state, first = play(new_queue(clips))
    state, skipped = advance(state, None)
    state, stale = advance(state, first.token)
    assert stale.status == "ignored"
    assert stale.index == 1
    assert stale.path == clips[1]
    assert stale.token == skipped.token
    state, nxt = advance(state, skipped.token)
    assert nxt.status == "playing"
    assert nxt.index == 2
    assert nxt.path == clips[2]


def test_served_filename_carries_the_play_token(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    served = serve_for_browser(clips[0], 7)
    assert token_from_audio(str(served)) == 7
    assert token_from_audio({"path": str(served)}) == 7
    assert token_from_audio(clips[0]) is None


def test_option_a_wires_one_audio_autoplay_and_stop(tmp_path: Path) -> None:
    clips = write_clips(tmp_path)
    demo = build_demo(clips)
    audios = [block for block in demo.blocks.values() if type(block).__name__ == "Audio"]
    assert len(audios) == 1
    assert audios[0].autoplay is True
    assert audios[0].elem_id == "now-playing"
    bindings = event_bindings(demo)
    assert ("now-playing", "stop") in bindings
    assert ("skip", "click") in bindings
    assert ("play-queue", "click") in bindings
    assert LAUNCH == {"server_name": "127.0.0.1", "server_port": 7860, "share": False}


def _bound_fn(demo: object, elem_id: str, event_name: str):
    by_id: dict[int, str] = {}
    for block in demo.blocks.values():
        block_id = getattr(block, "_id", None)
        found = getattr(block, "elem_id", None)
        if block_id is not None and found:
            by_id[int(block_id)] = str(found)
    for dep in demo.fns.values():
        for target in dep.targets:
            if int(target[0]) in by_id and by_id[int(target[0])] == elem_id and target[1] == event_name:
                return dep.fn
    raise AssertionError(f"no {elem_id} {event_name} handler")


def test_play_event_stamps_start_without_advancing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clips = write_clips(tmp_path)
    demo = build_demo(clips)
    assert ("now-playing", "play") in event_bindings(demo)
    assert _bound_fn(demo, "now-playing", "play") is stamp_playback_started

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("queue moved")

    monkeypatch.setattr("playback_spike.advance", fail)
    monkeypatch.setattr("playback_spike.play", fail)
    served = serve_for_browser(clips[0], 1)
    prior = "2026-10-16T00:00:00.000+00:00 end: clip ended"
    logged = stamp_playback_started(str(served), prior)
    assert logged.startswith(prior + "\n")
    assert " playing: file=t1-clip-440hz.wav" in logged


def _requirement_pins(text: str) -> list[str]:
    """Non-comment, non-blank lines from a requirements file."""
    pins: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pins.append(line)
    return pins


def test_requirements_pin_is_exact_gradio() -> None:
    pins = _requirement_pins((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    assert pins
    assert all(pin.count("==") == 1 for pin in pins)
    gradio_pins = [pin for pin in pins if pin.startswith("gradio==")]
    assert gradio_pins == [f"gradio=={version('gradio')}"]
    _name, exact = gradio_pins[0].split("==")
    assert exact and all(part.isdigit() for part in exact.split("."))


def test_requirement_pins_ignore_comments_and_other_packages() -> None:
    pins = _requirement_pins(
        "# Runtime dependencies, pinned to exact versions.\n\nhttpx==0.28.1\ngradio==6.30.0\n"
    )
    assert pins == ["httpx==0.28.1", "gradio==6.30.0"]
