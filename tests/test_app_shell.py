"""E2 app shell: placeholder panels, loopback launch, no model clients."""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

import gradio as gr
import pytest

# The pytest console script does not put the repo root on sys.path.
# `python -m pytest` does, which is why this passed locally and failed in CI.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.ui.launch import (  # noqa: E402
    HOST,
    allowed_paths,
    choose_port,
    ensure_runtime,
    port_is_free,
    serve,
)
from jukebox.ui.layout import build_demo  # noqa: E402

UI_DIR = ROOT / "jukebox" / "ui"
SHELL_FILES = [ROOT / "app.py", *sorted(UI_DIR.glob("*.py"))]


def _ids(demo: gr.Blocks) -> set[str]:
    found: set[str] = set()
    for block in demo.blocks.values():
        elem_id = getattr(block, "elem_id", None)
        if elem_id:
            found.add(str(elem_id))
    return found


def _block(demo: gr.Blocks, elem_id: str) -> object:
    for block in demo.blocks.values():
        if getattr(block, "elem_id", None) == elem_id:
            return block
    raise AssertionError(f"missing elem_id {elem_id}")


def _event_bindings(demo: gr.Blocks) -> set[tuple[str, str]]:
    by_block_id: dict[int, str] = {}
    for block in demo.blocks.values():
        elem_id = getattr(block, "elem_id", None)
        block_id = getattr(block, "_id", None)
        if elem_id and block_id is not None:
            by_block_id[int(block_id)] = str(elem_id)

    found: set[tuple[str, str]] = set()
    raw = getattr(demo, "fns", None) or getattr(demo, "dependencies", None) or {}
    deps = raw.values() if isinstance(raw, dict) else list(raw)
    for dep in deps:
        targets = getattr(dep, "targets", None)
        if targets is None and isinstance(dep, dict):
            targets = dep.get("targets")
        if not targets:
            continue
        for target in targets:
            if isinstance(target, (list, tuple)) and len(target) >= 2:
                elem_id = by_block_id.get(int(target[0]))
                if elem_id:
                    found.add((elem_id, str(target[1])))
    return found


def test_build_demo_shows_how_to_and_four_regions() -> None:
    demo = build_demo()
    assert {
        "how-to",
        "generate-tab",
        "library-tab",
        "player-panel",
        "dj-settings",
    } <= _ids(demo)
    assert "gr.Blocks" not in (ROOT / "app.py").read_text(encoding="utf-8")


def test_how_to_covers_play_generate_voice_and_measured_waits() -> None:
    text = str(getattr(_block(build_demo(), "how-to"), "value", ""))
    assert "Play queue" in text
    assert "Generate a song" in text
    assert "DJ voice" in text
    assert "not connected" in text
    assert "1.5 seconds" in text
    assert "5 to 7 seconds" in text
    assert "2.3 seconds" in text
    assert "DJ wait has not been measured" in text
    assert "usually takes" not in text.lower()


def test_player_wires_one_audio() -> None:
    demo = build_demo()
    audios = [block for block in demo.blocks.values() if type(block).__name__ == "Audio"]
    assert len(audios) == 1
    audio = audios[0]
    assert audio.autoplay is True
    assert audio.interactive is False
    assert audio.elem_id == "now-playing"
    images = [block for block in demo.blocks.values() if type(block).__name__ == "Image"]
    cover = _block(demo, "now-cover")
    assert cover in images
    assert list(cover.buttons) == ["download"]
    for block in images + audios:
        assert "share" not in list(getattr(block, "buttons", []) or [])
    play = _block(demo, "play-queue")
    skip = _block(demo, "skip")
    assert play.interactive is True
    assert skip.interactive is True
    bindings = _event_bindings(demo)
    assert bindings >= {("now-playing", "stop"), ("play-queue", "click"), ("skip", "click")}


def test_launch_is_loopback_and_share_is_refused(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_launch(demo: gr.Blocks, **kwargs: object) -> None:
        seen["demo"] = demo
        seen.update(kwargs)

    port = serve(tmp_path, launch=fake_launch, can_bind=lambda _host, _port: True)
    assert port == 7860
    assert seen["server_name"] == HOST == "127.0.0.1"
    assert seen["server_port"] == 7860
    assert seen["share"] is False
    assert seen["allowed_paths"] == allowed_paths(tmp_path)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("share=True must not launch")

    with pytest.raises(RuntimeError, match="share"):
        serve(tmp_path, share=True, launch=explode, can_bind=lambda _host, _port: True)


def test_gradio_keeps_uploads_inside_runtime_uploads(tmp_path: Path) -> None:
    """Gradio saves each upload (a DJ voice) before any handler runs; that copy must stay in
    runtime/uploads/, not the system temp folder (CLAUDE.md, H9)."""
    from gradio.utils import get_upload_folder

    seen: dict[str, object] = {}

    def fake_launch(demo: gr.Blocks, **_kwargs: object) -> None:
        seen["cache"] = demo.GRADIO_CACHE
        seen["folder"] = get_upload_folder()  # what the server uses for uploads, read at launch

    serve(tmp_path, launch=fake_launch, can_bind=lambda _host, _port: True)
    uploads = (tmp_path / "runtime" / "uploads").resolve()
    for key in ("cache", "folder"):
        assert Path(str(seen[key])).resolve().is_relative_to(uploads), key


def test_allowed_paths_are_samples_runtime_and_assets(tmp_path: Path) -> None:
    samples = (tmp_path / "samples").resolve()
    runtime = (tmp_path / "runtime").resolve()
    assets = (tmp_path / "jukebox" / "assets").resolve()
    assert allowed_paths(tmp_path) == [str(samples), str(runtime), str(assets)]
    source = (UI_DIR / "launch.py").read_text(encoding="utf-8")
    assert "C:\\Users" not in source
    assert "/Users/" not in source


def test_ensure_runtime_creates_runtime_dirs_only(tmp_path: Path) -> None:
    created = ensure_runtime(tmp_path)
    assert created == tmp_path / "runtime"
    assert (tmp_path / "runtime" / "generated").is_dir()
    assert (tmp_path / "runtime" / "uploads").is_dir()
    assert not (tmp_path / "samples").exists()


def test_a_listening_socket_is_not_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert port_is_free("127.0.0.1", port) is False


def test_port_is_free_after_the_server_closes_first() -> None:
    """A server that closes first leaves TIME_WAIT. Unix must still report the port free.

    Linux reuses that port only when the TIME_WAIT socket had SO_REUSEADDR set
    as well as the new bind. Gradio's listener sets it, so this socket does too.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        client.connect(("127.0.0.1", port))
        accepted, _addr = listener.accept()
        accepted.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        accepted.close()
        listener.close()
        client.close()
        deadline = time.monotonic() + 1
        while not port_is_free("127.0.0.1", port) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert port_is_free("127.0.0.1", port) is True
    finally:
        client.close()
        listener.close()


def test_busy_7860_uses_7861_and_both_busy_raises() -> None:
    def first_busy(host: str, port: int) -> bool:
        assert host == "127.0.0.1"
        return port != 7860

    assert choose_port("127.0.0.1", 7860, 7861, first_busy) == 7861

    with pytest.raises(RuntimeError, match="7860"):
        choose_port("127.0.0.1", 7860, 7861, lambda _host, _port: False)


def test_shell_imports_no_model_clients() -> None:
    banned = ("jukebox.clients", "import httpx", "from httpx", "import requests")
    for path in SHELL_FILES:
        text = path.read_text(encoding="utf-8")
        for snippet in banned:
            assert snippet not in text, f"{path.name} contains {snippet}"


# ---- A7: the tabs are connected to the player -----------------------------------------------------


def test_generate_and_library_buttons_are_connected_to_the_player() -> None:
    demo = build_demo()
    bindings = _event_bindings(demo)
    assert bindings >= {
        ("gen-play-now", "click"),
        ("gen-add-to-queue", "click"),
        ("lib-play-now", "click"),
        ("lib-add-to-queue", "click"),
    }


def test_the_library_buttons_read_the_list_itself_not_a_state_that_lags_behind_it() -> None:
    demo = build_demo()
    by_elem = {block.elem_id: block for block in demo.blocks.values() if getattr(block, "elem_id", None)}
    for button in ("lib-play-now", "lib-add-to-queue"):
        block_id = by_elem[button]._id
        wired = [
            fn for fn in demo.fns.values() if any(target == (block_id, "click") for target in fn.targets)
        ]
        assert len(wired) == 1
        first_input = wired[0].inputs[0]
        assert first_input is by_elem["lib-list"]  # the id the user can see, read at the click


def test_the_generate_tab_is_told_the_player_is_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    from jukebox.ui import generate_tab

    seen: list[dict] = []
    real = generate_tab.render

    def spy(**kwargs):
        seen.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(generate_tab, "render", spy)
    build_demo()
    assert seen and seen[0].get("player_connected") is True


def test_the_library_tab_is_a_real_list_not_the_placeholder() -> None:
    demo = build_demo()
    assert {"lib-list", "lib-play-now", "lib-add-to-queue"} <= _ids(demo)
    texts = " ".join(str(getattr(block, "value", "")) for block in demo.blocks.values())
    assert "No samples are loaded in this shell" not in texts
    assert "The library will list the sample songs here" not in texts


def test_how_to_no_longer_says_generate_is_not_connected() -> None:
    text = str(getattr(_block(build_demo(), "how-to"), "value", ""))
    assert "Generate and the DJ voice are not connected" not in text
    assert "Play now" in text
    assert "Add to queue" in text
    assert "DJ voice" in text and "not connected" in text  # DJ intros start playing with D5
