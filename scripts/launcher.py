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
    open_browser: Callable[[str], None]
    say: Callable[[str], None]


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

    if not env.exists():
        if (root / ".env.txt").exists():
            deps.say(
                "Found a settings file named .env.txt, but it must be named exactly .env\n"
                "(Notepad sometimes adds .txt). Rename it to .env, then run the launcher again.\n"
                f"It's in: {root}"
            )
            return EXIT_ACTION
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
            "Fill in each value from class-endpoints.txt: replace the placeholder text after each =\n"
            "with no spaces or quotes around it. Save the file, close the editor, and keep the name .env.\n"
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
            "delete .env and rename .env.txt to .env (Notepad sometimes adds .txt)."
        )
    deps.say("Copy each value from class-endpoints.txt, save the file, then run the launcher again.")
    deps.say(RULE)
    return EXIT_ACTION


def install_packages(root: Path, deps: Deps) -> int | None:
    requirements = root / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = root / ".venv" / STAMP_NAME
    if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == digest:
        return None
    deps.say(
        "Installing what the app needs. The first time takes a few minutes; lots of text will scroll by."
    )
    code = deps.run(
        [deps.python, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)], root
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
    deps.say("Opening the app. Keep this window open while you use it; close it or press Ctrl+C to stop.")
    process = deps.start([deps.python, "-u", str(app)], root)
    opened = False
    try:
        for line in process.stdout:
            deps.say(line.rstrip("\r\n"))
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
    else:
        deps.say(
            f"The app stopped with an error (exit code {code}). Read the messages above, then run the launcher again."
        )
    return code


def check_files(root: Path, deps: Deps) -> int | None:
    """The files the launcher needs from the ZIP. A partial extract gets a plain message, not a traceback."""
    missing = [name for name in (".env.example", "requirements.txt") if not (root / name).is_file()]
    if not missing:
        return None
    deps.say(
        f"Some app files are missing from {root}: {', '.join(missing)}.\n"
        "Extract the whole ZIP again into a new folder, then run the launcher from there.\n"
        "(On macOS, .env.example is hidden in Finder; press Cmd+Shift+. to see it.)"
    )
    return EXIT_ERROR


def main(*, root: Path = ROOT, deps: Deps | None = None) -> int:
    deps = deps or real_deps()
    steps: list[Callable[[], int | None]] = [
        lambda: check_python(deps),
        lambda: check_files(root, deps),
        lambda: check_settings(root, deps),
        lambda: install_packages(root, deps),
    ]
    for step in steps:  # stop at the first step that needs the user or failed
        code = step()
        if code is not None:
            return code
    check_services(root, deps)
    return run_app(root, deps)


if __name__ == "__main__":
    sys.exit(main())
