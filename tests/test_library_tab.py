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
    preview,
    refresh,
    render,
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


def test_a_refresh_keeps_the_selection_while_the_song_is_still_there(tmp_path: Path, make_track) -> None:
    library = Library(root=tmp_path)
    _add(library, make_track, tmp_path, "t1", "First Song")
    _add(library, make_track, tmp_path, "t2", "Second Song")
    found, selected = refresh(library, "t2")
    assert [track_id for _label, track_id in found] == ["t1", "t2"]
    assert selected == "t2"
    _found, selected = refresh(library, "gone")
    assert selected is None


def test_render_exposes_the_buttons_and_the_selected_id_for_the_player() -> None:
    with gr.Blocks():
        tab = render(library=Library(root=ROOT))
    assert isinstance(tab, LibraryTab)
    assert tab.play_now.elem_id == "lib-play-now"
    assert tab.add_to_queue.elem_id == "lib-add-to-queue"
    assert isinstance(tab.selected, gr.State)


def test_the_tab_imports_no_model_client() -> None:
    source = (ROOT / "jukebox" / "ui" / "library_tab.py").read_text(encoding="utf-8")
    assert "jukebox.clients" not in source
    assert "httpx" not in source
