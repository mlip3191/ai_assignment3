"""Tests for scripts/launcher.py: the shared logic behind run.sh and run.bat (task D6, PROJECT.md §0.4).

Nothing here installs packages, opens an editor or browser, or calls a class service: every outside
effect goes through a fake passed in as `deps`.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts" / "launcher.py")
launcher = importlib.util.module_from_spec(_spec)
sys.modules["launcher"] = launcher
_spec.loader.exec_module(launcher)

KEY = "test-key-0123456789"
GOOD_ENV = "\n".join(
    [
        f"CLASS_API_KEY={KEY}",
        "QWEN_BASE_URL=http://class.example:9001",
        "FLUX_BASE_URL=http://class.example:9006",
        "ACESTEP_BASE_URL=http://class.example:9007",
        "CHATTERBOX_BASE_URL=http://class.example:9008",
    ]
)


class FakeProcess:
    def __init__(self, lines: list[str], code: int = 0, interrupt: bool = False) -> None:
        self._lines = lines
        self._code = code
        self._interrupt = interrupt
        self.terminated = False

    @property
    def stdout(self):
        yield from self._lines
        if self._interrupt:
            raise KeyboardInterrupt

    def wait(self, timeout: float | None = None) -> int:
        return self._code

    def terminate(self) -> None:
        self.terminated = True


@dataclass
class World:
    """Records every outside effect the launcher asks for."""

    root: Path
    platform: str = "windows"
    version: tuple[int, int] = (3, 12)
    run_codes: dict[str, int] = field(default_factory=dict)
    app_lines: list[str] = field(default_factory=lambda: ["Open http://127.0.0.1:7860\n"])
    app_code: int = 0
    app_interrupt: bool = False
    already_running: str | None = None  # an address if the app is already up
    interrupt_on: str | None = None  # raise KeyboardInterrupt when this command runs
    editor_ok: bool = True
    said: list[str] = field(default_factory=list)
    ran: list[list[str]] = field(default_factory=list)
    started: list[list[str]] = field(default_factory=list)
    edited: list[Path] = field(default_factory=list)
    browsed: list[str] = field(default_factory=list)
    process: FakeProcess | None = None

    def deps(self):
        def run(cmd: list[str], cwd: Path) -> int:
            self.ran.append([str(c) for c in cmd])
            joined = " ".join(str(c) for c in cmd)
            if self.interrupt_on and self.interrupt_on in joined:
                raise KeyboardInterrupt
            return next((code for key, code in self.run_codes.items() if key in joined), 0)

        def start(cmd: list[str], cwd: Path) -> FakeProcess:
            self.started.append([str(c) for c in cmd])
            self.process = FakeProcess(self.app_lines, self.app_code, self.app_interrupt)
            return self.process

        def open_editor(path: Path) -> bool:
            self.edited.append(path)
            return self.editor_ok

        return launcher.Deps(
            platform=self.platform,
            python="PYTHON",
            version=self.version,
            environ={},
            run=run,
            start=start,
            open_editor=open_editor,
            open_browser=self.browsed.append,
            say=self.said.append,
            running_app=lambda: self.already_running,
        )

    @property
    def text(self) -> str:
        return "\n".join(self.said)

    def main(self) -> int:
        return launcher.main(root=self.root, deps=self.deps())


@pytest.fixture
def world(tmp_path: Path) -> World:
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")
    (tmp_path / "requirements.txt").write_text("httpx==0.28.1\n", encoding="utf-8")
    (tmp_path / "constraints.txt").write_text("httpx==0.28.1\nh11==0.16.0\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_endpoints.py").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    return World(root=tmp_path)


def ready(world: World) -> World:
    (world.root / ".env").write_text(GOOD_ENV, encoding="utf-8")
    return world


# ---- Python version ----------------------------------------------------------------------------


def test_python_older_than_3_11_is_refused_with_the_fix(world: World) -> None:
    world.version = (3, 10)
    assert world.main() == launcher.EXIT_ERROR
    assert "3.11" in world.text and "python.org" in world.text
    assert world.ran == [] and world.started == []


# ---- first run: no settings file (§0.4.4) ------------------------------------------------------


def test_first_run_creates_env_opens_the_editor_and_stops(world: World) -> None:
    assert world.main() == launcher.EXIT_ACTION
    env = world.root / ".env"
    assert env.read_text(encoding="utf-8") == (world.root / ".env.example").read_text(encoding="utf-8")
    assert world.edited == [env]
    assert "class-endpoints.txt" in world.text
    assert "run the launcher again" in world.text.lower()
    assert world.ran == [] and world.started == []  # nothing installed, no app


@pytest.mark.parametrize(("platform", "editor"), [("windows", "Notepad"), ("macos", "TextEdit")])
def test_first_run_names_the_editor_for_the_os(world: World, platform: str, editor: str) -> None:
    world.platform = platform
    world.main()
    assert editor in world.text


def test_if_the_editor_cant_open_the_message_says_where_the_file_is(world: World) -> None:
    world.editor_ok = False
    assert world.main() == launcher.EXIT_ACTION
    assert str(world.root / ".env") in world.text


def test_a_notepad_env_txt_is_renamed_for_the_user(world: World) -> None:
    (world.root / ".env.txt").write_text(GOOD_ENV, encoding="utf-8")
    assert world.main() == 0  # carries straight on with the settings they filled in
    assert (world.root / ".env").read_text(encoding="utf-8") == GOOD_ENV
    assert not (world.root / ".env.txt").exists()
    assert ".env.txt" in world.text and "renamed" in world.text.lower()
    assert world.started  # the app ran
    assert KEY not in world.text


def test_the_first_run_message_says_which_lines_to_change(world: World) -> None:
    world.main()
    assert "CLASS_API_KEY" in world.text and "_BASE_URL" in world.text
    assert "leave" in world.text.lower()


def test_macos_second_run_repeats_the_hidden_file_tip(world: World) -> None:
    world.platform = "macos"
    example = (world.root / ".env.example").read_text(encoding="utf-8")
    (world.root / ".env").write_text(example, encoding="utf-8")
    world.main()
    assert "Cmd+Shift+." in world.text


def test_a_second_launch_reuses_the_running_app(world: World) -> None:
    world.already_running = "http://127.0.0.1:7860"
    # Not EXIT_OK: run.bat pauses on any other code, so a double-click user can read the message
    # instead of seeing a window flash and close (found in the Windows ZIP test).
    assert ready(world).main() == launcher.EXIT_ACTION
    assert "already running" in world.text.lower()
    assert world.browsed == ["http://127.0.0.1:7860"]
    assert world.ran == [] and world.started == []  # no install, no second app


def test_windows_says_to_stop_by_closing_the_window(world: World) -> None:
    # Ctrl+C in cmd asks "Terminate batch job (Y/N)?", which confuses a first-time user.
    ready(world).main()
    line = next(s for s in world.said if s.startswith("Opening the app"))
    assert "close this window" in line
    assert "Ctrl+C" not in line


def test_macos_still_offers_ctrl_c_to_stop(world: World) -> None:
    world.platform = "macos"
    ready(world).main()
    line = next(s for s in world.said if s.startswith("Opening the app"))
    assert "close" in line and "Ctrl+C" in line


@pytest.mark.parametrize("step", ["pip", "check_endpoints"])
def test_ctrl_c_during_install_or_check_stops_without_a_traceback(world: World, step: str) -> None:
    world.interrupt_on = step
    assert ready(world).main() == launcher.EXIT_ERROR
    assert "stopped" in world.text.lower()
    assert world.started == []


# ---- next run: placeholders still there --------------------------------------------------------


def test_placeholders_are_listed_by_name_only_and_the_launcher_stops(world: World) -> None:
    example = (world.root / ".env.example").read_text(encoding="utf-8")
    (world.root / ".env").write_text(example.replace("your-class-api-key-here", KEY), encoding="utf-8")

    assert world.main() == launcher.EXIT_ACTION
    for name in ("QWEN_BASE_URL", "FLUX_BASE_URL", "ACESTEP_BASE_URL", "CHATTERBOX_BASE_URL"):
        assert name in world.text
    assert "CLASS_API_KEY" not in world.text  # this one is filled in
    assert KEY not in world.text and "class.example" not in world.text  # never a value
    assert world.edited == [world.root / ".env"]  # reopened so they can fix it
    assert world.ran == [] and world.started == []


def test_a_port_9000_url_is_reported_as_a_problem(world: World) -> None:
    (world.root / ".env").write_text(GOOD_ENV.replace(":9001", ":9000"), encoding="utf-8")
    assert world.main() == launcher.EXIT_ACTION
    assert "QWEN_BASE_URL" in world.text


# ---- install, check, launch (§0.4.5) -----------------------------------------------------------


def test_a_good_env_installs_checks_then_starts_the_app(world: World) -> None:
    assert ready(world).main() == 0
    install = world.ran[0]
    assert install[:4] == ["PYTHON", "-m", "pip", "install"]
    assert install[install.index("-r") + 1].endswith("requirements.txt")
    # every package underneath gradio/httpx is held to the tested version (PROJECT.md §4)
    assert install[install.index("-c") + 1].endswith("constraints.txt")
    assert world.ran[1][-1].endswith("check_endpoints.py")
    assert world.started == [["PYTHON", "-u", str(world.root / "app.py")]]
    assert "http://127.0.0.1:7860" in world.text


def test_install_is_skipped_when_requirements_are_unchanged(world: World) -> None:
    ready(world).main()
    world.ran.clear()
    world.main()
    assert not any("pip" in cmd for cmd in world.ran)


@pytest.mark.parametrize("changed", ["requirements.txt", "constraints.txt"])
def test_install_runs_again_when_requirements_or_constraints_change(world: World, changed: str) -> None:
    ready(world).main()
    path = world.root / changed
    path.write_text(path.read_text(encoding="utf-8") + "anyio==4.15.1\n", encoding="utf-8")
    world.ran.clear()
    world.main()
    assert any("pip" in cmd for cmd in world.ran)


def test_a_file_blocked_by_windows_is_explained_in_plain_words(world: World) -> None:
    world.app_lines = [
        "ImportError: DLL load failed while importing tslib: An Application Control policy has blocked this file.\n"
    ]
    world.app_code = 1
    assert ready(world).main() == 1
    assert "Smart App Control" in world.text
    assert "delete the .venv folder" in world.text.lower()


def test_a_failed_install_stops_with_a_plain_message_and_retries_next_time(world: World) -> None:
    world.run_codes = {"pip": 1}
    assert ready(world).main() == launcher.EXIT_ERROR
    assert "internet" in world.text.lower()
    assert world.started == []
    world.run_codes = {}
    world.ran.clear()
    world.main()
    assert any("pip" in cmd for cmd in world.ran)  # no stamp was written for the failed install


def test_an_unreachable_service_only_warns_and_the_app_still_starts(world: World) -> None:
    world.run_codes = {"check_endpoints": 1}
    assert ready(world).main() == 0
    assert "couldn't reach" in world.text.lower()
    assert world.started  # never blocks the app


def test_the_browser_opens_once_at_the_address_the_app_prints(world: World) -> None:
    world.app_lines = ["loading\n", "Open http://127.0.0.1:7861\n", "Open http://127.0.0.1:7861\n"]
    ready(world).main()
    assert world.browsed == ["http://127.0.0.1:7861"]


def test_the_app_output_is_shown_in_the_window(world: World) -> None:
    world.app_lines = ["Running on local URL:  http://127.0.0.1:7860\n"]
    ready(world).main()
    assert any("Running on local URL" in line for line in world.said)


def test_a_missing_app_py_is_a_clear_error(world: World) -> None:
    (world.root / "app.py").unlink()
    assert ready(world).main() == launcher.EXIT_ERROR
    assert "app.py" in world.text
    assert world.started == []


def test_the_app_exit_code_is_passed_through(world: World) -> None:
    world.app_code = 3
    assert ready(world).main() == 3
    assert "stopped" in world.text.lower()


def test_ctrl_c_stops_the_app_cleanly(world: World) -> None:
    world.app_interrupt = True
    assert ready(world).main() == 0
    assert world.process is not None and world.process.terminated


# ---- the real helpers (no fakes) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("windows", ["notepad.exe"]), ("macos", ["open", "-e"]), ("linux", None)],
)
def test_editor_command_per_os(platform: str, expected: list[str] | None, tmp_path: Path) -> None:
    command = launcher.editor_command(platform, tmp_path / ".env")
    if expected is None:
        assert command is None
    else:
        assert command == [*expected, str(tmp_path / ".env")]


def test_the_browser_is_opened_from_python_not_an_os_command() -> None:
    source = (ROOT / "scripts" / "launcher.py").read_text(encoding="utf-8")
    assert "webbrowser.open" in source
    for banned in ("xdg-open", "start ", "explorer", "ffmpeg", "shell=True"):
        assert banned not in source, banned


def test_a_notepad_env_txt_is_mentioned_even_when_env_also_exists(world: World) -> None:
    example = (world.root / ".env.example").read_text(encoding="utf-8")
    (world.root / ".env").write_text(example, encoding="utf-8")
    (world.root / ".env.txt").write_text(GOOD_ENV, encoding="utf-8")
    assert world.main() == launcher.EXIT_ACTION
    assert ".env.txt" in world.text and "rename" in world.text.lower()
    assert "File name extensions" in world.text  # how to see the hidden .txt on Windows
    assert KEY not in world.text


def test_the_browser_waits_until_the_app_is_listening() -> None:
    import socket

    opened: list[str] = []
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        thread = launcher.open_when_ready(f"http://127.0.0.1:{port}", opener=opened.append, timeout_s=5)
        thread.join(5)
    assert opened == [f"http://127.0.0.1:{port}"]


def test_the_browser_is_not_opened_if_the_app_never_listens() -> None:
    import socket

    with socket.socket() as probe:  # a port nothing is listening on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    opened: list[str] = []
    thread = launcher.open_when_ready(
        f"http://127.0.0.1:{port}", opener=opened.append, timeout_s=0.6, poll_s=0.1
    )
    thread.join(5)
    assert opened == []


def test_the_app_can_print_any_unicode_on_windows(tmp_path: Path) -> None:
    script = tmp_path / "app.py"
    script.write_text(
        'print("\\u266a Neon Overdrive \\u2192 \\u6771\\u4eac \\U0001f3b8")\n', encoding="utf-8"
    )
    process = launcher._launch_process([sys.executable, "-u", str(script)], tmp_path)
    lines = list(process.stdout)
    assert process.wait() == 0, lines
    assert lines[0].rstrip() == "\u266a Neon Overdrive \u2192 \u6771\u4eac \U0001f3b8"


@pytest.mark.parametrize("missing", [".env.example", "requirements.txt", "constraints.txt"])
def test_a_missing_file_from_the_zip_is_a_plain_message(world: World, missing: str) -> None:
    if missing != ".env.example":
        ready(world)
    (world.root / missing).unlink()
    assert world.main() == launcher.EXIT_ERROR
    assert missing in world.text and "zip" in world.text.lower()
    assert "Traceback" not in world.text


def test_the_browser_trigger_matches_what_the_real_app_shell_prints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the contract with E2: serve() prints the address the launcher waits for."""
    import jukebox.ui.launch as ui_launch  # E2 is on main: a broken import must fail, not skip

    calls: list[dict] = []
    monkeypatch.setattr(ui_launch, "build_demo", lambda: object())  # no UI needed for this check
    port = ui_launch.serve(
        tmp_path, launch=lambda demo, **kwargs: calls.append(kwargs), can_bind=lambda h, p: True
    )
    printed = capsys.readouterr().out
    match = launcher.APP_URL.search(printed)
    assert match is not None, printed
    assert match.group(0) == f"http://127.0.0.1:{port}"
    assert calls and calls[0]["server_port"] == port


def _serve_once(body: bytes) -> tuple[int, threading.Thread]:
    """A one-shot local HTTP server that answers any request with `body`."""
    import socket

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def answer() -> None:
        with server:
            conn, _ = server.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n" + body)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    return server.getsockname()[1], thread


def test_find_running_app_recognises_a_gradio_page() -> None:
    port, thread = _serve_once(b"<html><script>window.gradio_config = {}</script></html>")
    assert launcher.find_running_app([port]) == f"http://127.0.0.1:{port}"
    thread.join(5)


def test_find_running_app_ignores_another_program_on_the_port() -> None:
    port, thread = _serve_once(b"<html>some other local tool</html>")
    assert launcher.find_running_app([port]) is None
    thread.join(5)


def test_find_running_app_with_nothing_listening() -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert launcher.find_running_app([port]) is None


def test_detect_platform() -> None:
    assert launcher.detect_platform("win32") == "windows"
    assert launcher.detect_platform("darwin") == "macos"
    assert launcher.detect_platform("linux") == "linux"
