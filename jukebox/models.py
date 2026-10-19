"""The shared data shapes (PROJECT.md 6.1 Track, 6.2 Job). Changes require a PR to PROJECT.md first."""

from __future__ import annotations

import dataclasses
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Source = Literal["sample", "generated"]
JobKind = Literal["song", "cover", "dj"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class Track:
    id: str  # uuid4 hex; samples use "sample_01".."sample_03"
    title: str
    style: str  # genre/style tags, e.g. "lo-fi hip hop, jazzy keys"
    mood: str  # e.g. "mellow", "triumphant"
    theme: str | None  # optional user idea, e.g. "road trip"; feeds lyrics, cover, and DJ
    duration_s: int  # requested duration
    vocal: bool
    lyrics: str | None  # None for instrumentals
    audio_path: str  # path under samples/ or runtime/generated/
    cover_path: str | None  # None until cover succeeds -> UI shows placeholder + retry
    cover_prompt: str | None  # the exact FLUX prompt used (for docs/evidence)
    source: Source
    seed: int | None
    created_at: str  # ISO 8601

    def __post_init__(self) -> None:
        """Values, not just types (from_dict checks types). Each check skips a wrong type so that
        from_dict reports it first, rather than failing here with an AttributeError."""
        for name in ("id", "audio_path"):
            value = getattr(self, name)
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"Track.{name} has an invalid value: {value!r} (must not be empty)")
        if isinstance(self.duration_s, int) and self.duration_s <= 0:
            raise ValueError(f"Track.duration_s has an invalid value: {self.duration_s!r} (must be > 0)")
        if isinstance(self.created_at, str):
            try:
                datetime.fromisoformat(self.created_at)
            except ValueError:
                raise ValueError(
                    f"Track.created_at has an invalid value: {self.created_at!r} (must be ISO 8601)"
                ) from None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Track:
        return cls(**_checked_fields(cls, data))


@dataclass
class Job:
    id: str
    kind: JobKind
    status: JobStatus
    stage: str  # human-readable, e.g. "Writing lyrics…", "Composing music…"
    track_id: str | None
    error: str | None  # user-facing message (7.3), never a raw traceback or secret
    started_at: str
    finished_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Job:
        return cls(**_checked_fields(cls, data))


def _checked_fields(cls: type, data: Mapping[str, Any]) -> dict[str, Any]:
    """Return `data` as constructor arguments, or raise ValueError naming the first problem."""
    if not isinstance(data, Mapping):
        raise ValueError(f"{cls.__name__} must be built from a mapping, got {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    names = [f.name for f in dataclasses.fields(cls)]
    missing = [n for n in names if n not in data]
    if missing:
        raise ValueError(f"{cls.__name__} is missing field(s): {', '.join(missing)}")
    unknown = sorted(set(data) - set(names))
    if unknown:
        raise ValueError(f"{cls.__name__} has unknown field(s): {', '.join(map(str, unknown))}")
    for name in names:
        if not _matches(hints[name], data[name]):
            raise ValueError(f"{cls.__name__}.{name} has an invalid value: {data[name]!r}")
    return {name: data[name] for name in names}


def _matches(hint: Any, value: Any) -> bool:
    if typing.get_origin(hint) is Literal:
        return value in typing.get_args(hint)
    if hint == str | None:
        return value is None or isinstance(value, str)
    if hint == int | None:
        return value is None or (isinstance(value, int) and not isinstance(value, bool))
    if hint is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, hint)
