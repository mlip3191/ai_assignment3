"""Shared pytest setup for the whole suite."""

from __future__ import annotations

import pytest

# The variables that pin git to ONE repository (the same set `git rev-parse --local-env-vars` prints).
# git exports some of them to a hook, always when the push runs from a linked worktree, and the pre-push
# gate runs this suite from inside that hook. A test that builds its own temporary repo and inherits
# them would run `git init`, `git add`, `git commit` and `git switch` against the REAL repository.
LOCAL_GIT_ENV = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_QUARANTINE_PATH",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
)


@pytest.fixture(autouse=True)
def isolate_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with git free to find its own repository from the folder it runs in."""
    for name in LOCAL_GIT_ENV:
        monkeypatch.delenv(name, raising=False)
