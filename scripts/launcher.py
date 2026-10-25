#!/usr/bin/env python3
"""Get the AI Jukebox running: the shared steps behind run.sh (macOS) and run.bat (Windows).

PROJECT.md §0.4 (Path 1) is the spec. run.sh / run.bat only find Python and make `.venv`; then they
launch this file with the `.venv` Python, which does the rest, the same way on both systems:

  1. Settings: no `.env` yet -> copy `.env.example` to `.env`, open it in Notepad (Windows) or
     TextEdit (macOS), say what to fill in, and stop. A `.env` that still has placeholders or a bad
     value -> list the setting NAMES to fix (never a value), reopen it, and stop.
  2. Install the packages in requirements.txt, only when that file changed since the last install.
  3. Check the class services (scripts/check_endpoints.py). A problem is a warning; the app still runs.
  4. Run app.py, show its output, and open the browser (from Python) at the address it prints.

Exit codes: 0 the app ran and stopped, 1 something failed, 2 the user has to do something first.
Standard library only (plus jukebox/config.py, which is standard library only too).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.config import evaluate, read_values  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ACTION = 2
MIN_PYTHON = (3, 11)
STAMP_NAME = ".requirements.sha256"  # inside .venv, so a fresh .venv always reinstalls
APP_URL = re.compile(r"http://127\.0\.0\.1:\d+")
APP_PORTS = (7860, 7861)  # the app's port and its fallback (jukebox/ui/launch.py)
# gr.Blocks(title=...) in jukebox/ui/layout.py; tells our page from other Gradio apps.
APP_TITLE = "AI Jukebox"
BROWSER_WAIT_S = 5.0  # a second launch waits this long for the browser to open before exiting
EDITOR_NAMES = {"windows": "Notepad", "macos": "TextEdit"}
RULE = "-" * 68


class Process(Protocol):
    @property
    def stdout(self) -> Iterable[str]: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...


@dataclass
class Deps:
    """Everything that touches the outside world, so tests can replace it."""

    platform: str  # "windows", "macos" or "linux"
    python: str  # the .venv Python running this file
    version: tuple[int, int]
    environ: Mapping[str, str] | None  # None = the real environment (only the app's own variables)
    run: Callable[[Sequence[str], Path], int]
    start: Callable[[Sequence[str], Path], Process]
    open_editor: Callable[[Path], bool]
    open_browser: Callable[[str], object]  # may return the background thread that opens it
    say: Callable[[str], None]
    running_app: Callable[[], str | None]  # the address of an already-running AI Jukebox, if any


# ---- the real outside world ---------------------------------------------------------------------


def detect_platform(name: str = sys.platform) -> str:
    if name.startswith("win"):
        return "windows"
    if name == "darwin":
        return "macos"
    return "linux"


def editor_command(platform: str, path: Path) -> list[str] | None:
    """The plain-text editor §0.4.4 promises: Notepad on Windows, TextEdit on macOS."""
    if platform == "windows":
        return ["notepad.exe", str(path)]
    if platform == "macos":
        return ["open", "-e", str(path)]
    return None


def _open_editor(path: Path) -> bool:
    command = editor_command(detect_platform(), path)
    if command is None:
        return False
    try:
        subprocess.Popen(command)
    except OSError:
        return False
    return True


def _run(command: Sequence[str], cwd: Path) -> int:
    return subprocess.run(list(command), cwd=cwd).returncode


def _launch_process(command: Sequence[str], cwd: Path) -> Process:
    # The app's output goes through a pipe. On Windows a piped Python writes in the old code page
    # (cp1252) and crashes on a ♪, an emoji or a non-Latin song title, so force UTF-8 both ways.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def open_when_ready(
    url: str,
    *,
    opener: Callable[[str], object] = webbrowser.open,
    timeout_s: float = 120.0,
    poll_s: float = 0.25,
) -> threading.Thread:
    """Open `url` in the browser once something is listening on its port.

    The app prints its address just before the server starts, so opening straight away can show
    "can't connect". This waits (in the background, so the app's output keeps flowing) until the port
    accepts a connection, then opens it. If the app never starts listening, nothing is opened.
    """
    parts = urlsplit(url)
    host, port = parts.hostname or "127.0.0.1", parts.port or 80

    def wait_then_open() -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=1):
                    opener(url)
                    return
            except OSError:
                time.sleep(poll_s)

    thread = threading.Thread(target=wait_then_open, name="open-browser", daemon=True)
    thread.start()
    return thread


def _say(message: str) -> None:
    print(message, flush=True)


def find_running_app(ports: Sequence[int] = APP_PORTS) -> str | None:
    """The address of an AI Jukebox that's already running here (a second launch), or None.

    Only a Gradio page with our title counts, so another program or Gradio app on 7860 isn't mistaken
    for the app.
    This asks our own app on 127.0.0.1 for its page with a plain socket. It never contacts a class
    service or anything off this computer (AI calls stay in jukebox/clients/, PROJECT.md §7.0).
    """
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1) as conn:
                conn.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                page = b""
                while len(page) < 200_000:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    page += chunk
        except OSError:
            continue
        if b"gradio" in page.lower() and f'"title":"{APP_TITLE}"'.encode() in page:
            return f"http://127.0.0.1:{port}"
    return None


def real_deps() -> Deps:
    return Deps(
        platform=detect_platform(),
        python=sys.executable,
        version=sys.version_info[:2],
        environ=None,
        run=_run,
        start=_launch_process,
        open_editor=_open_editor,
        open_browser=open_when_ready,
        say=_say,
        running_app=find_running_app,
    )


# ---- the steps ----------------------------------------------------------------------------------


def check_python(deps: Deps) -> int | None:
    if deps.version >= MIN_PYTHON:
        return None
    found = ".".join(map(str, deps.version))
    deps.say(
        f"This app needs Python 3.11 or newer, but found Python {found}.\n"
        'Install Python 3.12 from python.org/downloads (Windows: tick "Add python.exe to PATH"),\n'
        "delete the .venv folder in the app folder, then run the launcher again."
    )
    return EXIT_ERROR


def check_settings(root: Path, deps: Deps) -> int | None:
    env = root / ".env"
    editor = EDITOR_NAMES.get(deps.platform, "a text editor")

    if not env.exists() and (root / ".env.txt").exists():
        # Notepad's "Save As" adds .txt, and Windows hides extensions, so renaming by hand often fails.
        os.replace(root / ".env.txt", env)
        deps.say(
            "Found your settings saved as .env.txt (Notepad adds .txt), so I renamed it to .env for you."
        )

    if not env.exists():
        shutil.copyfile(root / ".env.example", env)
        opened = deps.open_editor(env)
        deps.say(RULE)
        deps.say("First start: I created your settings file.")
        deps.say(f"  {env}")
        if opened:
            deps.say(f"It's open in {editor} now.")
        else:
            deps.say(
                "Open it in a plain-text editor (it may be hidden: on macOS press Cmd+Shift+. in Finder)."
            )
        deps.say(
            "Change only the first 5 settings: CLASS_API_KEY and the four lines ending in _BASE_URL.\n"
            "Copy each value from class-endpoints.txt over the placeholder text after the =, with no spaces\n"
            "or quotes around it. Leave everything else as it is.\n"
            "Save the file, close the editor, and keep the name exactly .env.\n"
            "This file stays on your computer. Never email it or upload it.\n"
            "Then run the launcher again."
        )
        deps.say(RULE)
        return EXIT_ACTION

    rows, _ = evaluate(read_values(deps.environ, env))
    problems = [row for row in rows if row.status != "OK"]
    if not problems:
        return None
    opened = deps.open_editor(env)
    deps.say(RULE)
    deps.say("Your settings file needs a few fixes before the app can start:")
    for row in problems:
        deps.say(f"  {row.var}: {row.note}")
    deps.say(f"The file is {env}" + (f" (open in {editor} now)." if opened else "."))
    if (root / ".env.txt").exists():
        deps.say(
            "There is also a file named .env.txt next to it. If that's where you saved your values,\n"
            "delete .env and rename .env.txt to .env (Notepad sometimes adds .txt). To see the .txt on\n"
            "Windows, open the folder in File Explorer and choose View > Show > File name extensions."
        )
    if deps.platform == "macos":
        deps.say("In Finder, press Cmd+Shift+. to see files whose names begin with a dot, like .env.")
    deps.say("Copy each value from class-endpoints.txt, save the file, then run the launcher again.")
    deps.say(RULE)
    return EXIT_ACTION


def install_packages(root: Path, deps: Deps) -> int | None:
    requirements = root / "requirements.txt"
    # constraints.txt holds every package underneath requirements.txt to the tested version, so a fresh
    # install on grading day gets what the team ran (and what Windows Smart App Control already trusts).
    constraints = root / "constraints.txt"
    digest = hashlib.sha256(requirements.read_bytes() + b"\0" + constraints.read_bytes()).hexdigest()
    stamp = root / ".venv" / STAMP_NAME
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == digest:
        return None
    deps.say(
        "Installing what the app needs. The first time takes a few minutes; lots of text will scroll by."
    )
    code = deps.run(
        [
            deps.python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements),
            "-c",
            str(constraints),
        ],
        root,
    )
    if code != 0:
        deps.say(RULE)
        deps.say(
            "The install didn't finish. Check your internet connection and run the launcher again.\n"
            "If it keeps failing, delete the .venv folder in the app folder and try once more."
        )
        deps.say(RULE)
        return EXIT_ERROR
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(digest, encoding="utf-8")
    return None


def check_services(root: Path, deps: Deps) -> None:
    deps.say("Checking the class servers...")
    code = deps.run([deps.python, str(root / "scripts" / "check_endpoints.py")], root)
    if code != 0:
        deps.say(
            "Warning: I couldn't reach every class service (see above). The app will still open,\n"
            "but songs, covers or the DJ may fail until the servers answer. You may need the campus\n"
            "network or VPN, or the servers may just be busy. You can keep going and use Retry in the app."
        )


def run_app(root: Path, deps: Deps) -> int:
    app = root / "app.py"
    if not app.is_file():
        deps.say(
            f"Can't find app.py in {root}. Make sure you extracted the whole ZIP and ran the launcher from that folder."
        )
        return EXIT_ERROR
    # On Windows, Ctrl+C makes cmd ask "Terminate batch job (Y/N)?", so only closing the window is offered.
    stop = "close this window" if deps.platform == "windows" else "close this window or press Ctrl+C"
    deps.say(f"Opening the app. Keep this window open while you use it. To stop it, {stop}.")
    process = deps.start([deps.python, "-u", str(app)], root)
    opened = False
    blocked_by_windows = False
    try:
        for line in process.stdout:
            deps.say(line.rstrip("\r\n"))
            if "Application Control policy has blocked" in line:
                blocked_by_windows = True
            match = APP_URL.search(line)
            if match and not opened:
                opened = True
                deps.say(
                    f"Your browser should open at {match.group(0)}. If it doesn't, type that address into it."
                )
                deps.open_browser(match.group(0))
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        deps.say("Stopped the app.")
        return EXIT_OK
    if code == 0:
        deps.say("The app has stopped.")
    elif blocked_by_windows:
        deps.say(RULE)
        deps.say(
            "Windows blocked one of the app's files (Smart App Control: \"An Application Control policy has\n"
            'blocked this file"). This happens when a package version is too new for Windows to recognise.\n'
            "Delete the .venv folder in the app folder and run the launcher again; it reinstalls the tested\n"
            "versions. If it happens again, tell the team which file was blocked (the line above)."
        )
        deps.say(RULE)
    else:
        deps.say(
            f"The app stopped with an error (exit code {code}). Read the messages above, then run the launcher again."
        )
    return code


def check_files(root: Path, deps: Deps) -> int | None:
    """The files the launcher needs from the ZIP. A partial extract gets a plain message, not a traceback."""
    shipped = (".env.example", "requirements.txt", "constraints.txt")
    missing = [name for name in shipped if not (root / name).is_file()]
    if not missing:
        return None
    deps.say(
        f"Some app files are missing from {root}: {', '.join(missing)}.\n"
        "Extract the whole ZIP again into a new folder, then run the launcher from there.\n"
        "(On macOS, .env.example is hidden in Finder; press Cmd+Shift+. to see it.)"
    )
    return EXIT_ERROR


def reuse_running_app(deps: Deps) -> int | None:
    """A second launch: open the app that's already running instead of a second copy on 7861."""
    url = deps.running_app()
    if url is None:
        return None
    deps.say(
        f"The app is already running in another window, at {url}. Opening it in your browser.\n"
        "For a fresh copy, close that other launcher window first, then run this one again."
    )
    opening = deps.open_browser(url)
    # open_when_ready opens it on a background thread, which exiting now would stop.
    if isinstance(opening, threading.Thread):
        opening.join(BROWSER_WAIT_S)
    return EXIT_ACTION  # not OK: run.bat pauses on any other code, so this message stays readable


def main(*, root: Path = ROOT, deps: Deps | None = None) -> int:
    deps = deps or real_deps()
    steps: list[Callable[[], int | None]] = [
        lambda: check_python(deps),
        lambda: check_files(root, deps),
        lambda: reuse_running_app(deps),
        lambda: check_settings(root, deps),
        lambda: install_packages(root, deps),
    ]
    try:
        for step in steps:  # stop at the first step that needs the user, failed, or finished
            code = step()
            if code is not None:
                return code
        check_services(root, deps)
    except KeyboardInterrupt:  # Ctrl+C before the app is up: a plain line, not a traceback
        deps.say("Stopped before the app opened. Run the launcher again when you're ready.")
        return EXIT_ERROR
    return run_app(root, deps)


if __name__ == "__main__":
    sys.exit(main())
