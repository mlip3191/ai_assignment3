"""A7 Library tab: lists the songs in the library and sends one to the player by track id."""

from __future__ import annotations

import sys
from pathlib import Path

import gradio as gr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.library import Library  # noqa: E402
from jukebox.services.art import placeholder_path  # noqa: E402
from jukebox.ui.library_tab import (  # noqa: E402
    EMPTY_TEXT,
    LibraryTab,
    choices,
    pick,
    preview,
    render,
    snapshot,
    tick,
)
from jukebox.ui.player_panel import UNKNOWN_TRACK  # noqa: E402


def _add(library: Library, make_track, tmp_path: Path, track_id: str, title: str, **fields) -> None:
    audio = f"runtime/generated/{track_id}.mp3"
    (tmp_path / audio).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / audio).write_bytes(b"ID3 fake audio")
    library.add(make_track(id=track_id, title=title, audio_path=audio, **fields))


def test_choices_list_every_song_with_its_id_in_library_order(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song", source="sample")
    _add(library, make_track, tmp_path, "t2", "Second Song")
    found = choices(library)
    assert [track_id for _label, track_id in found] == ["t1", "t2"]
    assert "First Song" in found[0][0]
    assert "Second Song" in found[1][0]


def test_a_song_generated_later_shows_up_without_rebuilding_the_page(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song", source="sample")
    assert len(choices(library)) == 1
    _add(library, make_track, tmp_path, "t2", "Brand New")  # the Generate tab finishes a song
    assert [track_id for _label, track_id in choices(library)] == ["t1", "t2"]


def test_an_empty_library_says_so_instead_of_showing_a_blank_list(tmp_path: Path) -> None:
    library = Library(root=tmp_path)
    assert choices(library) == []
    shown = preview(library, None)
    assert shown.track_id is None
    assert shown.details == EMPTY_TEXT


def test_the_preview_is_looked_up_by_id_not_by_position(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song", style="jazz")
    _add(library, make_track, tmp_path, "t2", "Second Song", style="metal")
    before = preview(library, "t2")
    _add(library, make_track, tmp_path, "t0", "Newest Song")  # the list grows; positions shift
    after = preview(library, "t2")
    assert before.track_id == after.track_id == "t2"
    assert "Second Song" in after.details
    assert "metal" in after.details
    assert "First Song" not in after.details


def test_the_preview_shows_the_placeholder_until_the_cover_arrives(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song", cover_path=None)
    assert preview(library, "t1").cover == str(placeholder_path())
    cover = tmp_path / "runtime" / "generated" / "t1.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xe0cover")
    library.attach_cover("t1", "runtime/generated/t1.jpg", "a quiet scene")
    assert preview(library, "t1").cover == str(cover)  # no page reload: the next refresh picks it up


def test_a_song_that_is_not_in_the_library_gets_a_plain_message(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song")
    shown = preview(library, "nope")
    assert shown.track_id is None
    assert shown.cover == str(placeholder_path())
    assert shown.details == UNKNOWN_TRACK


def test_render_exposes_the_buttons_and_the_list_whose_value_is_the_chosen_id() -> None:
    with gr.Blocks():
        tab = render(library=Library(root=ROOT))
    assert isinstance(tab, LibraryTab)
    assert tab.play_now.elem_id == "lib-play-now"
    assert tab.add_to_queue.elem_id == "lib-add-to-queue"
    assert tab.more_like_this.elem_id == "lib-more-like-this"
    assert isinstance(tab.selected, gr.Radio)  # read at the click, so it can't lag a pick


def test_the_tab_imports_no_model_client() -> None:
    source = (ROOT / "jukebox" / "ui" / "library_tab.py").read_text(encoding="utf-8")
    assert "jukebox.clients" not in source
    assert "httpx" not in source


def _skips(out: tuple) -> bool:
    return len(out) == 4 and all(item == gr.skip() for item in out)


def test_the_preview_escapes_every_generated_field(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(
        library,
        make_track,
        tmp_path,
        "t1",
        "# Big *Title*",
        style="lo-fi\n# injected",
        mood="<b>calm</b>",
        theme="x\n- a list",
    )
    lines = preview(library, "t1").details.split("\n")
    assert lines[0] == "### \\# Big \\*Title\\*"
    assert not any(line.startswith(("# ", "- ", "<")) for line in lines)
    assert not any("injected" in line and line.startswith("\\#") for line in lines)
    assert "<b>" not in "\n".join(lines)


def test_pick_returns_the_cover_details_and_the_chosen_id(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song")
    cover, details, selected = pick(library, "t1")
    assert selected == "t1"
    assert "First Song" in details
    assert cover == preview(library, "t1").cover
    assert pick(library, None)[2] is None  # nothing chosen
    assert pick(library, "nope")[2] is None  # a song that is gone is not chosen


def test_a_tick_with_nothing_new_touches_nothing(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song")
    assert _skips(tick(library, "t1", snapshot(library)))
    assert _skips(tick(library, None, snapshot(library)))


def test_a_tick_adds_a_new_song_without_touching_the_choice(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song")
    seen = snapshot(library)
    _add(library, make_track, tmp_path, "t2", "Brand New")
    listing, _cover, details, now = tick(library, "t1", seen)
    assert [track_id for _label, track_id in listing["choices"]] == ["t1", "t2"]
    assert "value" not in listing  # a click made while the tick runs is never undone
    assert "First Song" in details  # the chosen song's details stay
    assert now == snapshot(library)
    assert now != seen


def test_a_tick_leaves_an_empty_choice_alone_too(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    seen = snapshot(library)
    _add(library, make_track, tmp_path, "t1", "First Song")
    listing, _cover, details, _now = tick(library, None, seen)
    assert len(listing["choices"]) == 1
    assert "value" not in listing  # the user may have just picked it
    assert details == preview(library, None).details


def test_a_tick_shows_the_cover_that_just_arrived_for_the_chosen_song(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song", cover_path=None)
    seen = snapshot(library)
    cover = tmp_path / "runtime" / "generated" / "t1.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xe0cover")
    library.attach_cover("t1", "runtime/generated/t1.jpg", "a quiet scene")
    _listing, shown_cover, details, now = tick(library, "t1", seen)
    assert shown_cover == str(cover)
    assert "First Song" in details
    assert now != seen


def test_the_pick_and_the_tick_run_one_at_a_time_so_a_slow_tick_cannot_overwrite_a_pick() -> None:
    with gr.Blocks() as demo:
        render(library=Library(root=ROOT))
    ids = {fn.concurrency_id for fn in demo.fns.values()}
    limits = {fn.concurrency_limit for fn in demo.fns.values()}
    assert len(ids) == 1  # both handlers share one lane
    assert limits == {1}
