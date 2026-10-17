"""E2 app shell: placeholder panels, loopback launch, no model clients."""

from __future__ import annotations

import socket
import sys
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


def test_player_has_one_unwired_audio() -> None:
    demo = build_demo()
    audios = [block for block in demo.blocks.values() if type(block).__name__ == "Audio"]
    assert len(audios) == 1
    audio = audios[0]
    assert audio.autoplay is False
    assert audio.interactive is False
    assert audio.elem_id == "now-playing"
    play = _block(demo, "play-queue")
    skip = _block(demo, "skip")
    assert play.interactive is False
    assert skip.interactive is False
    bindings = _event_bindings(demo)
    assert ("now-playing", "stop") not in bindings
    assert ("play-queue", "click") not in bindings
    assert ("skip", "click") not in bindings


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


def test_allowed_paths_are_samples_and_runtime(tmp_path: Path) -> None:
    samples = (tmp_path / "samples").resolve()
    runtime = (tmp_path / "runtime").resolve()
    assert allowed_paths(tmp_path) == [str(samples), str(runtime)]
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
    """A server that closes first leaves TIME_WAIT. Unix must still report the port free."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        client.connect(("127.0.0.1", port))
        accepted, _addr = listener.accept()
        accepted.close()
        listener.close()
        client.close()
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
