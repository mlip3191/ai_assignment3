"""Tests for run.sh, run.bat and requirements.txt (task D6, PROJECT.md §0.4 and §4).

The launchers are thin: they find Python, make .venv, and hand off to scripts/launcher.py (tested in
test_launcher.py). These tests check the parts that only live in the two shell files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / "run.sh"
RUN_BAT = ROOT / "run.bat"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_lines(path: Path, comment: str) -> list[str]:
    lines = []
    for line in text(path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.lower().startswith(comment):
            lines.append(stripped)
    return lines


# ---- requirements.txt (§4: pin every direct dependency) ----------------------------------------


def requirement_lines() -> list[str]:
    return code_lines(ROOT / "requirements.txt", "#")


def test_every_requirement_is_pinned_exactly() -> None:
    lines = requirement_lines()
    assert lines
    for line in lines:
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,\-]+\])?==[0-9][A-Za-z0-9.]*", line), line


def test_the_app_dependencies_are_present() -> None:
    names = {line.split("==")[0].lower() for line in requirement_lines()}
    assert {"httpx", "gradio"} <= names
    assert "gradio==6.30.0" in requirement_lines()  # the version E1 tested playback on


# ---- run.bat (Windows) -------------------------------------------------------------------------


def test_run_bat_tries_python_3_12_then_3_11_then_python() -> None:
    body = text(RUN_BAT)
    positions = [body.find("py -3.12"), body.find("py -3.11"), body.find("python -c")]
    assert -1 not in positions, positions
    assert positions == sorted(positions)


def test_run_bat_uses_the_venv_python_directly_without_activation() -> None:
    body = text(RUN_BAT).lower()
    assert r".venv\scripts\python.exe" in body
    assert r"scripts\launcher.py" in body
    for banned in ("activate", "powershell", ".ps1", "ffmpeg", "winget", "choco"):
        assert banned not in body, banned


def test_run_bat_pauses_on_every_error_path() -> None:
    lines = [line.lower() for line in code_lines(RUN_BAT, "rem")]
    gotos = [line for line in lines if "goto" in line]
    assert gotos and all(":fail" in line or ":done" in line for line in gotos)
    fail = lines.index(":fail")
    assert "pause" in lines[fail : fail + 4]
    for line in lines:
        assert not re.search(r"exit /b [1-9]", line) or line.startswith("exit /b %"), line


def test_run_bat_passes_the_launcher_exit_code_on() -> None:
    body = text(RUN_BAT).lower()
    assert "errorlevel" in body
    assert "exit /b %code%" in body


def test_run_bat_is_checked_out_with_crlf_line_endings() -> None:
    assert re.search(r"^\*\.bat\s+text\s+eol=crlf", text(ROOT / ".gitattributes"), re.MULTILINE)


def archived(name: str) -> bytes | None:
    """The file as a GitHub 'Download ZIP' would contain it (git archive applies .gitattributes)."""
    import io
    import tarfile

    if shutil.which("git") is None:
        return None
    tracked = subprocess.run(["git", "ls-files", name], cwd=ROOT, capture_output=True, text=True).stdout
    if not tracked.strip():
        return None
    tar = subprocess.run(["git", "archive", "--format=tar", "HEAD", name], cwd=ROOT, capture_output=True)
    if tar.returncode != 0:
        return None
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as archive:
        return archive.extractfile(name).read()


def test_the_downloaded_run_bat_has_crlf_and_run_sh_has_lf() -> None:
    bat, sh = archived("run.bat"), archived("run.sh")
    if bat is None or sh is None:
        pytest.skip("run.bat / run.sh not committed yet")
    assert b"\r\n" in bat
    assert b"\r\n" not in sh


def test_run_bat_copes_with_network_folders_and_checks_the_zip_was_extracted() -> None:
    body = text(RUN_BAT).lower()
    assert 'pushd "%~dp0"' in body
    assert r'if not exist "scripts\launcher.py"' in body
    assert body.index(r'if not exist "scripts\launcher.py"') < body.index("-m venv")
    assert "extract" in body


def test_run_sh_checks_the_zip_was_extracted_before_making_the_venv() -> None:
    body = text(RUN_SH)
    assert "scripts/launcher.py" in body
    assert body.index('[ ! -f "scripts/launcher.py" ]') < body.index("-m venv")
    assert "Extract" in body


# ---- run.sh (macOS) ----------------------------------------------------------------------------


def test_run_sh_tries_python3_12_then_3_11_then_python3() -> None:
    body = text(RUN_SH)
    candidates = re.search(r"for candidate in ([^;]+);", body)
    assert candidates is not None
    assert candidates.group(1).split() == ["python3.12", "python3.11", "python3"]


def test_run_sh_uses_the_venv_python_without_activation() -> None:
    body = text(RUN_SH)
    assert ".venv/bin/python" in body
    assert "scripts/launcher.py" in body
    for banned in ("activate", "brew ", "ffmpeg", "sudo", "open -a", "xdg-open"):
        assert banned not in body, banned


def test_run_sh_starts_with_bash_and_stops_on_errors() -> None:
    body = text(RUN_SH)
    assert body.startswith("#!/usr/bin/env bash")
    assert "set -u" in body
    assert 'cd "$(dirname "$0")"' in body  # works when started from another folder (drag into Terminal)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_run_sh_has_valid_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(RUN_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_run_sh_is_checked_out_with_lf_line_endings() -> None:
    assert re.search(r"^\*\.sh\s+text\s+eol=lf", text(ROOT / ".gitattributes"), re.MULTILINE)
    assert b"\r\n" not in RUN_SH.read_bytes()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_run_sh_is_executable_in_git_when_tracked() -> None:
    result = subprocess.run(["git", "ls-files", "-s", "run.sh"], cwd=ROOT, capture_output=True, text=True)
    if not result.stdout.strip():
        pytest.skip("run.sh is not committed yet")
    assert result.stdout.startswith("100755"), result.stdout


# ---- both ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("script", [RUN_SH, RUN_BAT])
def test_both_launchers_hand_off_to_the_same_launcher_and_print_plain_messages(script: Path) -> None:
    body = text(script)
    assert "launcher.py" in body
    assert "python.org" in body  # the fix when Python is missing
    assert ".venv" in body
