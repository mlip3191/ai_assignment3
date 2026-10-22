"""requirements-dev.txt pins the developer tools exactly (task A13, PROJECT.md section 4).

CI and scripts/setup_dev.py both install this file, so an unpinned tool lets a new release change ruff's
formatting or break the suite for one person or one OS. Runtime pins live in requirements.txt (lane D).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = {"pytest", "respx", "ruff"}
EXACT_PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==\d+(?:\.\d+)*$")


def requirement_lines(text: str) -> list[str]:
    """The requirement lines of a requirements file: no blanks, no comments."""
    lines = (line.split(" #", 1)[0].strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def not_exactly_pinned(text: str) -> list[str]:
    return [line for line in requirement_lines(text) if not EXACT_PIN.match(line)]


def tool_names(text: str) -> set[str]:
    return {line.split("==", 1)[0].lower() for line in requirement_lines(text)}


def test_every_dev_requirement_is_pinned_exactly() -> None:
    text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert requirement_lines(text), "requirements-dev.txt lists no tools"
    assert not_exactly_pinned(text) == []


def test_pytest_respx_and_ruff_are_all_listed() -> None:
    text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert REQUIRED_TOOLS <= tool_names(text)


def test_the_checker_rejects_unpinned_ranged_and_loose_lines() -> None:
    """The pin test must fail on a bad line, or it would pass for any file."""
    bad = [
        "pytest",
        "pytest>=9",
        "pytest~=9.1",
        "pytest==9.*",
        "pytest<10",
        "pytest==9.1.1; python_version >= '3.11'",
        "git+https://example.com/respx.git",
        "-e .",
        "ruff @ https://example.com/ruff.whl",
    ]
    assert not_exactly_pinned("\n".join(bad)) == bad


def test_the_checker_accepts_exact_pins_comments_and_blank_lines() -> None:
    text = "# tools\n\npytest==9.1.1\nrespx==0.23.1  # mock httpx\nruff==0.17.0\n"
    assert not_exactly_pinned(text) == []
    assert tool_names(text) == REQUIRED_TOOLS


def test_ci_installs_the_dev_requirements_in_every_job() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert ci.count("pip install -r requirements-dev.txt") >= 2  # the Ubuntu job and the Windows/macOS matrix


def test_setup_dev_installs_the_dev_requirements() -> None:
    setup = (ROOT / "scripts" / "setup_dev.py").read_text(encoding="utf-8")
    assert '"requirements-dev.txt"' in setup
