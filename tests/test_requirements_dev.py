"""requirements-dev.txt pins the developer tools exactly (task A13, PROJECT.md section 4).

CI and scripts/setup_dev.py both install this file, so an unpinned tool lets a new release change ruff's
formatting or break the suite for one person or one OS. Runtime pins live in requirements.txt (lane D).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = {"pytest", "respx", "ruff"}
EXACT_PIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==\d+(?:\.\d+)*$")
CI_INSTALL = "pip install -r requirements-dev.txt"
CI_JOBS = ("checks", "cross-platform")
CI_JOB_HEADING = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")


def ci_jobs(text: str) -> dict[str, str]:
    """Each job in a workflow file mapped to its live lines: nothing before `jobs:`, no comment lines."""
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    in_jobs = False
    for line in text.splitlines():
        if not in_jobs:
            in_jobs = line.rstrip() == "jobs:"
            continue
        heading = CI_JOB_HEADING.match(line)
        if heading:
            current = heading.group(1)
            jobs[current] = []
        elif current is not None and not line.strip().startswith("#"):
            jobs[current].append(line)
    return {name: "\n".join(lines) for name, lines in jobs.items()}


def runs_pip_install(source: str, requirements: str) -> bool:
    """True if the Python source has a run([... "install", "-r", <requirements> ...]) call."""
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run"):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.List):
                continue
            words = [item.value for item in arg.elts if isinstance(item, ast.Constant)]
            if any(words[i : i + 3] == ["install", "-r", requirements] for i in range(len(words))):
                return True
    return False


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


def test_each_ci_job_installs_the_dev_requirements() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    jobs = ci_jobs(ci)
    for job in CI_JOBS:  # the Ubuntu job and the Windows/macOS matrix
        assert job in jobs, f"ci.yml has no '{job}' job"
        assert CI_INSTALL in jobs[job], f"the '{job}' job does not run: {CI_INSTALL}"


def test_the_ci_checker_counts_only_live_lines_inside_each_job() -> None:
    """A comment, a line before `jobs:`, or another job's step must not count for a job."""
    ci = "\n".join(
        [
            f"# {CI_INSTALL}",
            "jobs:",
            "  checks:",
            "    steps:",
            f"      # - run: {CI_INSTALL}",
            "  cross-platform:",
            "    steps:",
            f"      - run: {CI_INSTALL}",
            f"      - run: {CI_INSTALL}",
        ]
    )
    jobs = ci_jobs(ci)
    assert set(jobs) == {"checks", "cross-platform"}
    assert CI_INSTALL not in jobs["checks"]
    assert CI_INSTALL in jobs["cross-platform"]


def test_setup_dev_pip_installs_the_dev_requirements() -> None:
    setup = (ROOT / "scripts" / "setup_dev.py").read_text(encoding="utf-8")
    assert runs_pip_install(setup, "requirements-dev.txt")


def test_the_setup_checker_ignores_comments_strings_and_other_commands() -> None:
    """Only a real run([... "install", "-r", <file> ...]) call counts, so the test can fail."""
    name = "requirements-dev.txt"
    install = f'run([PY, "-m", "pip", "install", "-r", "{name}", "--quiet"])'
    assert runs_pip_install(install, name)
    not_installs = [
        f"# {install}",
        f'DOC = """{install}"""',
        f'run([PY, "-m", "pip", "uninstall", "-r", "{name}"])',
        'run([PY, "-m", "pip", "install", "-r", "requirements.txt"])',
        f'print([PY, "-m", "pip", "install", "-r", "{name}"])',
    ]
    for source in not_installs:
        assert not runs_pip_install(source, name), source
