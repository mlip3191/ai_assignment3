"""Start the local Gradio shell. No share link and no class services."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from pathlib import Path

import gradio as gr

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


def allowed_paths(root: Path) -> list[str]:
    """Directories Gradio may serve: committed samples and session runtime files."""
    root = Path(root)
    return [str((root / "samples").resolve()), str((root / "runtime").resolve())]


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
    ensure_runtime(root)
    demo = build_demo()
    port = choose_port(HOST, PORT, FALLBACK_PORT, can_bind or port_is_free)
    print(f"Open http://{HOST}:{port}")
    opener = launch or _launch
    opener(
        demo,
        server_name=HOST,
        server_port=port,
        share=False,
        allowed_paths=allowed_paths(root),
    )
    return port


def _launch(demo: gr.Blocks, **kwargs: object) -> None:
    demo.launch(**kwargs)
