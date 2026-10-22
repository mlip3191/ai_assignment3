"""E4 player panel: Option A wiring, covers and titles, sample tracks, placeholder DJ clips."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.library import Library  # noqa: E402
from jukebox.services.art import cover_for  # noqa: E402
from jukebox.services.player import DJ_UNAVAILABLE, FINISHED  # noqa: E402
from jukebox.ui.player_panel import (  # noqa: E402
    NOW_PLAYING,
    SPEAKING,
    on_end,
    on_play,
    on_skip,
    open_player,
    panel_text,
)

PANEL = ROOT / "jukebox" / "ui" / "player_panel.py"


def _wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 80)


def _library(tmp_path: Path, make_track, *, clips_for: set[str] | None = None):
    library = Library(root=tmp_path)
    clips: dict[str, str] = {}
    for n, title in enumerate(("One", "Two", "Three"), start=1):
        track_id = f"sample_0{n}"
        audio_rel = f"samples/audio/{track_id}.wav"
        _wav(tmp_path / audio_rel)
        library.add(
            make_track(
                id=track_id,
                title=title,
                audio_path=audio_rel,
                source="sample",
                cover_path=None,
            )
        )
        if clips_for is None or track_id in clips_for:
            clip = tmp_path / "dj" / f"{track_id}.wav"
            _wav(clip)
            clips[track_id] = str(clip)
    return library, clips


def _cover(library: Library, track_id: str) -> str:
    return str(cover_for(track_id, library=library))


def test_panel_source_does_not_import_a_model_client() -> None:
    text = PANEL.read_text(encoding="utf-8")
    assert "jukebox.clients" not in text
    assert "make_clip" not in text


def test_play_with_no_samples_does_not_finish_the_queue(tmp_path: Path) -> None:
    library = Library(root=tmp_path)
    player = open_player(library, {})
    view = on_play(player, library, 0, tmp_path / "runtime")
    assert view.label == "No sample tracks are loaded."
    assert view.audio is None
    assert view.ignored is False
    assert player.current is None
    assert player.notice is None
    assert player.queue == []


def test_play_queues_the_three_samples_and_starts_the_first(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    view = on_play(player, library, 0, tmp_path / "served")
    assert view.ignored is False
    assert view.label == SPEAKING
    assert view.title == "One"
    assert view.cover == _cover(library, "sample_01")
    assert view.token == 1
    assert view.audio is not None
    assert Path(view.audio).name == "t1-sample_01.wav"
    assert [title for title, _cover in view.up_next] == ["Two", "Three"]
    assert "DJ speaking…" in panel_text(view)
    assert "One" in panel_text(view)
    assert "- Two" in panel_text(view)


def test_a_second_play_does_not_advance(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    first = on_play(player, library, 0, runtime)
    second = on_play(player, library, first.token, runtime)
    assert second.ignored is True
    assert second.token == first.token
    assert player.current is not None
    assert player.current.kind == "dj"
    assert player.current.track_id == "sample_01"


def test_end_events_play_dj_then_song_for_each_sample(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    view = on_play(player, library, 0, runtime)
    labels = [view.label]
    titles = [view.title]
    while view.label != FINISHED:
        view = on_end(player, library, view.token, view.audio, runtime)
        labels.append(view.label)
        titles.append(view.title)
    assert labels == [
        SPEAKING,
        NOW_PLAYING,
        SPEAKING,
        NOW_PLAYING,
        SPEAKING,
        NOW_PLAYING,
        FINISHED,
    ]
    assert titles == ["One", "One", "Two", "Two", "Three", "Three", ""]
    assert player.current is None
    assert player.notice == FINISHED
    assert view.audio is None


def test_skip_during_a_dj_clip_plays_that_song(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    skipped = on_skip(player, library, started.token, runtime)
    assert skipped.label == NOW_PLAYING
    assert skipped.title == "One"
    assert skipped.token == started.token + 1
    assert player.current is not None
    assert player.current.kind == "song"
    assert [title for title, _cover in skipped.up_next] == ["Two", "Three"]


def test_skip_during_a_song_moves_to_the_next_track(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    view = on_play(player, library, 0, runtime)
    view = on_end(player, library, view.token, view.audio, runtime)
    assert view.label == NOW_PLAYING
    skipped = on_skip(player, library, view.token, runtime)
    assert skipped.label == SPEAKING
    assert skipped.title == "Two"


def test_a_missing_clip_plays_the_song_and_says_so(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track, clips_for={"sample_01"})
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    view = on_play(player, library, 0, runtime)
    view = on_end(player, library, view.token, view.audio, runtime)
    assert view.label == NOW_PLAYING
    assert view.title == "One"
    view = on_end(player, library, view.token, view.audio, runtime)
    assert view.label == NOW_PLAYING
    assert view.title == "Two"
    assert view.notice == DJ_UNAVAILABLE
    assert DJ_UNAVAILABLE in panel_text(view)
    assert view.cover == _cover(library, "sample_02")


def test_a_stale_end_token_does_not_advance(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    skipped = on_skip(player, library, started.token, runtime)
    late = on_end(player, library, skipped.token, started.audio, runtime)
    assert late.ignored is True
    assert late.token == skipped.token
    assert player.current is not None
    assert player.current.kind == "song"
    assert player.current.track_id == "sample_01"


def test_skip_with_nothing_playing_leaves_the_queue(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    player.enqueue("sample_01")
    view = on_skip(player, library, 0, tmp_path / "served")
    assert view.ignored is True
    assert player.current is None
    assert player.queue == ["sample_01"]
