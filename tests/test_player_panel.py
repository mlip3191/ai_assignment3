"""E4 player panel: Option A wiring, covers and titles, sample tracks, placeholder DJ clips."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gradio as gr  # noqa: E402

from jukebox.library import Library  # noqa: E402
from jukebox.services.art import cover_for  # noqa: E402
from jukebox.services.player import DJ_UNAVAILABLE, FINISHED  # noqa: E402
from jukebox.ui.player_panel import (  # noqa: E402
    _CLIPS,
    _SESSIONS,
    NO_LYRICS,
    NOW_PLAYING,
    PRESS_PLAY,
    SPEAKING,
    UNKNOWN_TRACK,
    PlayerPanel,
    PlayerView,
    _gradio,
    download_name,
    on_add,
    on_end,
    on_play,
    on_play_now,
    on_skip,
    open_player,
    panel_text,
    player_for,
    render,
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
    assert Path(view.audio).name.startswith("t1-")
    assert Path(view.audio).name.endswith("-sample_01.wav")
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


def test_a_new_play_does_not_reuse_a_served_file(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    runtime = tmp_path / "served"
    first = on_play(open_player(library, {}), library, 0, runtime)
    stale = Path(first.audio)
    stale.write_bytes(b"stale")
    second = on_play(open_player(library, {}), library, 0, runtime)
    source = tmp_path / "samples" / "audio" / "sample_01.wav"
    assert second.audio != first.audio
    assert Path(second.audio).read_bytes() == source.read_bytes()
    assert stale.read_bytes() == b"stale"


def test_each_browser_session_has_its_own_player(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _SESSIONS.clear()
    first, first_id = player_for("", library)
    second, second_id = player_for("", library)
    same, same_id = player_for(first_id, library)
    runtime = tmp_path / "served"
    on_play(first, library, 0, runtime)
    other = on_play(second, library, 0, runtime)
    assert first is same
    assert same_id == first_id
    assert first is not second
    assert first_id != second_id
    assert other.ignored is False
    assert other.title == "One"
    assert first.current is not None
    assert first.current.track_id == "sample_01"
    assert second.current is not None
    assert second.current.track_id == "sample_01"
    _SESSIONS.clear()


def test_a_missing_song_file_shows_unavailable_and_skip_still_moves(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    (tmp_path / "samples" / "audio" / "sample_01.wav").unlink()
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    view = on_play(player, library, 0, runtime)
    assert view.label == SPEAKING
    view = on_end(player, library, view.token, view.audio, runtime)
    assert view.audio is None
    assert view.title == "One"
    assert view.notice == DJ_UNAVAILABLE
    assert DJ_UNAVAILABLE in panel_text(view)
    assert player.current is not None
    assert player.current.track_id == "sample_01"
    skipped = on_skip(player, library, view.token, runtime)
    assert skipped.title == "Two"
    assert skipped.audio is not None


def test_skip_with_nothing_playing_leaves_the_queue(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    player.enqueue("sample_01")
    view = on_skip(player, library, 0, tmp_path / "served")
    assert view.ignored is True
    assert player.current is None
    assert player.queue == ["sample_01"]


# ---- A7: Add to queue and Play now, from the Generate card and the Library tab --------------------


def _with_generated(
    library: Library, make_track, tmp_path: Path, track_id: str = "gen1", title: str = "Fresh Song"
):
    """A song generated this session: it has audio and no cover yet, like the moment after Generate."""
    audio_rel = f"runtime/generated/{track_id}.wav"
    _wav(tmp_path / audio_rel)
    library.add(
        make_track(id=track_id, title=title, audio_path=audio_rel, cover_path=None, source="generated")
    )


def test_add_puts_a_generated_song_in_up_next_without_starting_it(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, {})
    view = on_add(player, library, 0, "gen1", tmp_path / "served")
    assert view.keep_audio is True
    assert view.audio is None
    assert view.token == 0
    assert player.current is None
    assert player.queue == ["gen1"]
    assert [title for title, _cover in view.up_next] == ["Fresh Song"]
    assert view.up_next[0][1] == _cover(library, "gen1")  # the placeholder until the cover arrives
    assert "Fresh Song" in panel_text(view)


def test_add_while_a_song_plays_leaves_it_playing(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    before = player.current
    view = on_add(player, library, started.token, "gen1", runtime)
    assert player.current == before
    assert view.keep_audio is True
    assert view.token == started.token
    assert [title for title, _cover in view.up_next] == ["Two", "Three", "Fresh Song"]


@pytest.mark.parametrize("bad_id", [None, "", "   ", "nope"])
def test_add_with_no_such_song_says_so_and_changes_nothing(tmp_path: Path, make_track, bad_id) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    view = on_add(player, library, 3, bad_id, tmp_path / "served")
    assert view.notice == UNKNOWN_TRACK
    assert UNKNOWN_TRACK in panel_text(view)
    assert view.keep_audio is True
    assert view.token == 3
    assert player.queue == []
    assert player.current is None


def test_play_now_starts_that_song_and_moves_the_token_on(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, {})
    view = on_play_now(player, library, 4, "gen1", tmp_path / "served")
    assert view.keep_audio is False
    assert view.label == NOW_PLAYING
    assert view.title == "Fresh Song"
    assert view.token == 5
    assert view.notice == DJ_UNAVAILABLE  # no DJ clip yet: the song plays and says so
    assert Path(view.audio).name.startswith("t5-")
    assert Path(view.audio).name.endswith("-gen1.wav")
    assert view.cover == _cover(library, "gen1")


def test_play_now_with_a_dj_clip_plays_the_dj_first(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    clip = tmp_path / "dj" / "gen1.wav"
    _wav(clip)
    player = open_player(library, {"gen1": str(clip)})
    runtime = tmp_path / "served"
    view = on_play_now(player, library, 0, "gen1", runtime)
    assert view.label == SPEAKING
    assert Path(view.audio).name.endswith("-gen1.wav")
    after_dj = on_end(player, library, view.token, view.audio, runtime)
    assert after_dj.label == NOW_PLAYING
    assert after_dj.title == "Fresh Song"


def test_play_now_replaces_what_is_playing_and_the_queue_carries_on(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    jumped = on_play_now(player, library, started.token, "gen1", runtime)
    assert jumped.title == "Fresh Song"
    assert player.queue == ["sample_02", "sample_03"]
    after = on_end(player, library, jumped.token, jumped.audio, runtime)  # the generated song ends
    assert after.label == SPEAKING
    assert after.title == "Two"


def test_play_now_takes_a_queued_copy_out_of_the_queue(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, {})
    runtime = tmp_path / "served"
    on_add(player, library, 0, "gen1", runtime)
    on_play_now(player, library, 0, "gen1", runtime)
    assert player.queue == []


def test_a_late_end_event_cannot_advance_past_play_now(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    _with_generated(library, make_track, tmp_path)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    jumped = on_play_now(player, library, started.token, "gen1", runtime)
    late = on_end(player, library, jumped.token, started.audio, runtime)
    assert late.ignored is True
    assert player.current is not None
    assert player.current.track_id == "gen1"


def test_play_now_with_no_such_song_keeps_the_current_one_playing(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    player = open_player(library, clips)
    runtime = tmp_path / "served"
    started = on_play(player, library, 0, runtime)
    before = player.current
    view = on_play_now(player, library, started.token, "nope", runtime)
    assert view.notice == UNKNOWN_TRACK
    assert view.keep_audio is True
    assert view.token == started.token
    assert player.current == before


def test_play_now_with_a_missing_song_file_shows_unavailable_instead_of_failing(
    tmp_path: Path, make_track
) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    (tmp_path / "runtime" / "generated" / "gen1.wav").unlink()
    player = open_player(library, {})
    view = on_play_now(player, library, 0, "gen1", tmp_path / "served")
    assert view.audio is None
    assert view.notice == DJ_UNAVAILABLE
    assert DJ_UNAVAILABLE in panel_text(view)


def test_a_view_that_keeps_the_audio_updates_only_the_text_and_up_next() -> None:
    from jukebox.ui.player_panel import PlayerView

    view = PlayerView(None, "Now playing", "One", "cover.png", None, (("Two", "two.png"),), 7, False, True)
    out = _gradio(view)
    assert len(out) == 7
    assert out[0] == gr.skip()  # the audio keeps playing
    assert out[2] == gr.skip()  # and so does the cover
    assert out[4] == gr.skip()  # and the token stays
    assert "Two" in out[1]
    assert out[3] == [("two.png", "Two")]


def test_a_dj_clip_filled_in_after_the_song_was_queued_is_used(
    tmp_path: Path, make_track, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plug point for D5: whatever fills the shared clip map is picked up by every session's player."""
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _SESSIONS.clear()
    player, _session = player_for("", library)
    runtime = tmp_path / "served"
    on_add(player, library, 0, "sample_01", runtime)
    clip = tmp_path / "dj" / "later.wav"
    _wav(clip)
    monkeypatch.setitem(_CLIPS, "sample_01", str(clip))  # the prefetch finishes after the click
    view = on_play(player, library, 0, runtime)
    assert view.label == SPEAKING
    assert Path(view.audio).name.endswith("-later.wav")
    _SESSIONS.clear()


def test_render_returns_a_panel_that_binds_buttons_to_this_players_outputs() -> None:
    with gr.Blocks() as demo:
        panel = render()
        selected = gr.State("sample_01")
        add = gr.Button("Add", elem_id="x-add")
        now = gr.Button("Now", elem_id="x-now")
        panel.connect_add(add, selected)
        panel.connect_play_now(now, selected)
    assert isinstance(panel, PlayerPanel)
    assert len(panel.outputs) == 8  # audio, status, cover, up next, token, lyrics, download, session
    clicks = {
        target[0]
        for dep in demo.get_config_file()["dependencies"]
        for target in dep["targets"]
        if target[1] == "click"
    }
    assert {add._id, now._id} <= clicks


def test_panel_text_escapes_generated_titles_so_they_stay_plain_text() -> None:
    view = PlayerView(
        None,
        NOW_PLAYING,
        "# Hello *world*\nMix <b>1</b>",
        None,
        None,
        (("1. Intro", "cover.jpg"), ("- Sneaky\n> quote", "cover.jpg")),
        1,
        False,
    )
    lines = panel_text(view).split("\n")
    assert "\\# Hello \\*world\\* Mix \\<b\\>1\\</b\\>" in lines  # one plain line, nothing formatted
    assert "- 1\\. Intro" in lines  # the list item is ours, the song's own number is text
    assert "- \\- Sneaky \\> quote" in lines
    assert not any(line.startswith(("#", ">")) for line in lines)
    assert "<b>" not in panel_text(view)


# ---- Lyrics while playing, and Download song with the song's name (proposal on #3) -----------------


def test_a_vocal_song_shows_its_lyrics_while_it_plays(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    view = on_play_now(open_player(library, {}), library, 0, "gen1", tmp_path / "served")
    assert view.lyrics == "[verse]\nLights ahead"


def test_an_instrumental_says_it_has_no_lyrics(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _wav(tmp_path / "runtime/generated/inst.wav")
    library.add(
        make_track(id="inst", title="Calm", vocal=False, lyrics=None, audio_path="runtime/generated/inst.wav")
    )
    view = on_play_now(open_player(library, {}), library, 0, "inst", tmp_path / "served")
    assert view.lyrics == NO_LYRICS


def test_the_lyrics_follow_the_song_on_skip_and_clear_when_the_queue_ends(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path)
    library.add(
        make_track(id="inst", title="Calm", vocal=False, lyrics=None, audio_path="runtime/generated/gen1.wav")
    )
    player = open_player(library, {})
    runtime = tmp_path / "served"
    on_add(player, library, 0, "gen1", runtime)
    on_add(player, library, 0, "inst", runtime)
    first = on_play(player, library, 0, runtime)
    assert first.lyrics == "[verse]\nLights ahead"
    second = on_skip(player, library, first.token, runtime)
    assert second.lyrics == NO_LYRICS
    done = on_skip(player, library, second.token, runtime)
    assert done.lyrics == ""
    assert done.download is None


def test_download_is_a_copy_named_after_the_song(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path, title="Fresh Song")
    view = on_play_now(open_player(library, {}), library, 0, "gen1", tmp_path / "served")
    download = Path(view.download)
    assert download.name == "Fresh Song.wav"
    assert download.read_bytes() == (tmp_path / "runtime/generated/gen1.wav").read_bytes()
    assert (tmp_path / "served") in download.parents  # under the runtime folder, never next to the song


def test_two_songs_with_the_same_title_get_separate_downloads(tmp_path: Path, make_track) -> None:
    library, _clips = _library(tmp_path, make_track, clips_for=set())
    _with_generated(library, make_track, tmp_path, track_id="a", title="Same")
    _with_generated(library, make_track, tmp_path, track_id="b", title="Same")
    player = open_player(library, {})
    first = on_play_now(player, library, 0, "a", tmp_path / "served")
    second = on_play_now(player, library, first.token, "b", tmp_path / "served")
    assert Path(first.download).name == Path(second.download).name == "Same.wav"
    assert first.download != second.download


def test_a_dj_intro_already_offers_the_songs_download(tmp_path: Path, make_track) -> None:
    library, clips = _library(tmp_path, make_track)
    view = on_play(open_player(library, clips), library, 0, tmp_path / "served")
    assert view.label == SPEAKING
    assert Path(view.download).name == "One.wav"
    assert view.lyrics == "[verse]\nLights ahead"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Fresh Song", "Fresh Song"),
        ('Rock/Roll: "Live"?', "RockRoll Live"),
        ("  Dots and spaces. . ", "Dots and spaces"),
        ("Café Noir", "Café Noir"),
        ("CON", "song CON"),  # a reserved name on Windows
        ("***", "song"),
        ("x" * 200, "x" * 80),
    ],
)
def test_download_names_are_safe_on_macos_and_windows(title: str, expected: str) -> None:
    assert download_name(title) == expected


def test_a_view_shows_the_lyrics_and_the_download_button() -> None:
    view = PlayerView(
        "a.wav", NOW_PLAYING, "One", "c.png", None, (), 2, False, lyrics="la", download="One.wav"
    )
    out = _gradio(view)
    assert out[5] == "la"
    assert out[6]["value"] == "One.wav"
    assert out[6]["visible"] is True
    idle = _gradio(PlayerView(None, PRESS_PLAY, "", None, None, (), 2, False))
    assert idle[5] == ""
    assert idle[6]["visible"] is False


def test_a_view_that_keeps_the_audio_keeps_the_lyrics_and_download() -> None:
    view = PlayerView(None, NOW_PLAYING, "One", "c.png", None, (), 7, False, True)
    out = _gradio(view)
    assert out[5] == gr.skip()
    assert out[6] == gr.skip()


def test_the_panel_has_a_lyrics_box_and_a_download_button() -> None:
    with gr.Blocks():
        panel = render()
    ids = [getattr(o, "elem_id", None) for o in panel.outputs]
    assert ids[5:7] == ["now-lyrics", "now-download"]
    assert isinstance(panel.outputs[6], gr.DownloadButton)
    assert panel.outputs[5].interactive is False
