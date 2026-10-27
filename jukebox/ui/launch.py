"""Start the local Gradio shell. No share link and no class services."""

from __future__ import annotations

import os
import shutil
import socket
from collections.abc import Callable
from pathlib import Path

import gradio as gr

from jukebox.services import dj
from jukebox.ui.layout import build_demo

HOST = "127.0.0.1"
PORT = 7860
FALLBACK_PORT = 7861

BindCheck = Callable[[str, int], bool]
Launcher = Callable[..., None]


def ensure_runtime(root: Path) -> Path:
    """Create the gitignored runtime folders. Does not create samples/."""
    root = Path(root)
    runtime = root / "runtime"
    for folder in (runtime, runtime / "generated", runtime / "uploads"):
        folder.mkdir(parents=True, exist_ok=True)
    return runtime


def clear_old_uploads(uploads: Path) -> None:
    """Delete DJ voice recordings and Gradio's copies left by an earlier run.

    The chosen voice is kept in memory, so after a restart none of them is in use (H9). A file that
    can't be deleted (Windows, still open) is left in the gitignored folder.
    """
    for recording in Path(uploads).glob("voice_*"):
        try:
            recording.unlink()
        except OSError:
            pass
    shutil.rmtree(Path(uploads) / "gradio", ignore_errors=True)


def allowed_paths(root: Path) -> list[str]:
    """Directories Gradio may serve: samples, session files, and the placeholder cover."""
    root = Path(root)
    return [
        str((root / "samples").resolve()),
        str((root / "runtime").resolve()),
        str((root / "jukebox" / "assets").resolve()),
    ]


def choose_port(host: str, port: int, fallback: int, can_bind: BindCheck) -> int:
    if can_bind(host, port):
        return port
    if can_bind(host, fallback):
        return fallback
    raise RuntimeError(f"Ports {port} and {fallback} are in use on {host}.")


def port_is_free(host: str, port: int) -> bool:
    """True when nothing is listening on host:port.

    macOS and Linux keep a just-closed port in TIME_WAIT, so a plain bind fails
    and a restart looks like both ports are busy. SO_REUSEADDR ignores that.
    Do not set it on Windows: there it lets a second process bind the same port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def serve(
    root: Path,
    *,
    share: bool = False,
    launch: Launcher | None = None,
    can_bind: BindCheck | None = None,
) -> int:
    """Launch on 127.0.0.1. share=True is refused. Returns the chosen port."""
    if share:
        raise RuntimeError("Gradio public share links are disabled.")
    root = Path(root)
    runtime = ensure_runtime(root)
    port = choose_port(HOST, PORT, FALLBACK_PORT, can_bind or port_is_free)
    if port == PORT:  # on the fallback port another copy may be running and using its recording
        clear_old_uploads(runtime / "uploads")
    # Gradio saves every upload (a DJ voice) here before a handler sees it; the default is the system
    # temp folder. It reads this when the page is built, so set it first.
    os.environ["GRADIO_TEMP_DIR"] = str((runtime / "uploads" / "gradio").resolve())
    demo = build_demo()
    print(f"Open http://{HOST}:{port}")
    opener = launch or _launch
    opener(
        demo,
        server_name=HOST,
        server_port=port,
        share=False,
        allowed_paths=allowed_paths(root),
        max_file_size=dj.MAX_VOICE_BYTES,  # refused before it's written to disk; the voice is the only upload
    )
    return port


def _launch(demo: gr.Blocks, **kwargs: object) -> None:
    demo.launch(**kwargs)
