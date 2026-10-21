"""Queue ordering, skip, a missing DJ clip, and the end of the queue (PROJECT.md 8.4, E3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jukebox.services.player import DJ_UNAVAILABLE, FINISHED, Player, PlayerError, PlayItem

SONGS = {
    "s1": "samples/audio/s1.mp3",
    "s2": "samples/audio/s2.mp3",
    "s3": "samples/audio/s3.mp3",
}


def test_order_is_dj_then_song_for_each_track():
    dj = {track_id: f"runtime/dj/{track_id}.mp3" for track_id in SONGS}
    player = Player(SONGS, dj)
    player.enqueue("s1")
    player.enqueue("s2")
    player.enqueue("s3")
    assert player.queue == ["s1", "s2", "s3"]
    assert player.current is None

    assert [player.next_item() for _ in range(6)] == [
        PlayItem("dj", "s1", dj["s1"]),
        PlayItem("song", "s1", SONGS["s1"]),
        PlayItem("dj", "s2", dj["s2"]),
        PlayItem("song", "s2", SONGS["s2"]),
        PlayItem("dj", "s3", dj["s3"]),
        PlayItem("song", "s3", SONGS["s3"]),
    ]
    assert player.next_item() is None
    assert player.current is None
    assert player.queue == []
    assert player.notice == FINISHED


def test_skip_during_a_dj_clip_jumps_to_that_song():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3", "s2": "runtime/dj/s2.mp3"})
    player.enqueue("s1")
    player.enqueue("s2")
    assert player.next_item() == PlayItem("dj", "s1", "runtime/dj/s1.mp3")

    assert player.skip() == PlayItem("song", "s1", SONGS["s1"])
    assert player.queue == ["s2"]
    assert player.notice is None


def test_skip_during_a_song_moves_to_the_next_track():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3", "s2": "runtime/dj/s2.mp3"})
    player.enqueue("s1")
    player.enqueue("s2")
    player.next_item()
    player.next_item()

    assert player.skip() == PlayItem("dj", "s2", "runtime/dj/s2.mp3")
    assert player.current == PlayItem("dj", "s2", "runtime/dj/s2.mp3")


def test_skip_during_a_song_plays_the_next_song_when_its_dj_clip_is_missing():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3"})
    player.enqueue("s1")
    player.enqueue("s2")
    player.next_item()
    player.next_item()

    assert player.skip() == PlayItem("song", "s2", SONGS["s2"])
    assert player.notice == DJ_UNAVAILABLE


def test_a_missing_dj_clip_plays_the_song_immediately():
    player = Player(SONGS, {})
    player.enqueue("s1")

    assert player.next_item() == PlayItem("song", "s1", SONGS["s1"])
    assert player.notice == DJ_UNAVAILABLE
    assert player.queue == []


def test_a_blank_dj_path_counts_as_not_ready():
    player = Player(SONGS, {"s1": "  "})
    player.enqueue("s1")

    assert player.next_item() == PlayItem("song", "s1", SONGS["s1"])
    assert player.notice == DJ_UNAVAILABLE


def test_a_dj_clip_that_arrives_before_the_next_track_is_used():
    dj: dict[str, str] = {}
    player = Player(SONGS, dj)
    player.enqueue("s1")
    player.enqueue("s2")
    assert player.next_item() == PlayItem("song", "s1", SONGS["s1"])
    assert player.notice == DJ_UNAVAILABLE

    dj["s2"] = "runtime/dj/s2.mp3"
    assert player.next_item() == PlayItem("dj", "s2", "runtime/dj/s2.mp3")
    assert player.notice is None


def test_the_end_of_the_queue_stays_finished():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3"})
    player.enqueue("s1")
    player.next_item()
    player.next_item()

    assert player.next_item() is None
    assert player.notice == FINISHED
    assert player.skip() is None
    assert player.notice == FINISHED
    assert player.current is None


def test_enqueue_does_not_start_playback():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3"})
    player.enqueue("s1")

    assert player.current is None
    assert player.notice is None
    assert player.queue == ["s1"]


def test_skip_while_idle_leaves_the_queue():
    player = Player(SONGS, {})
    player.enqueue("s1")

    assert player.skip() is None
    assert player.queue == ["s1"]
    assert player.current is None


def test_clear_drops_the_current_item_and_the_queue():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3"})
    player.enqueue("s1")
    player.enqueue("s2")
    player.next_item()
    player.clear()

    assert player.current is None
    assert player.queue == []
    assert player.notice is None


def test_play_now_interrupts_and_starts_that_track():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3", "s2": "runtime/dj/s2.mp3"})
    player.enqueue("s1")
    player.enqueue("s2")
    player.next_item()

    assert player.play_now("s2") == PlayItem("dj", "s2", "runtime/dj/s2.mp3")
    assert player.queue == []
    assert player.current == PlayItem("dj", "s2", "runtime/dj/s2.mp3")


def test_play_now_without_a_dj_clip_starts_the_song():
    player = Player(SONGS, {})

    assert player.play_now("s2") == PlayItem("song", "s2", SONGS["s2"])
    assert player.notice == DJ_UNAVAILABLE


def test_play_now_pulls_one_queued_copy_out_and_leaves_another():
    player = Player(SONGS, {"s1": "runtime/dj/s1.mp3"})
    player.enqueue("s1")
    player.enqueue("s1")

    assert player.play_now("s1") == PlayItem("dj", "s1", "runtime/dj/s1.mp3")
    assert player.queue == ["s1"]


def test_unknown_or_blank_track_is_rejected():
    player = Player(SONGS, {})
    with pytest.raises(PlayerError, match="s9"):
        player.enqueue("s9")
    with pytest.raises(PlayerError, match="track id"):
        player.play_now("  ")
    assert player.queue == []
    assert player.current is None


def test_the_player_does_not_import_gradio_or_a_model_client():
    import jukebox.services.player as player

    text = Path(player.__file__).read_text(encoding="utf-8")
    assert "gradio" not in text
    assert "jukebox.clients" not in text
