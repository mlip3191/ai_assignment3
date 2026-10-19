"""Track and Job match PROJECT.md 6.1 / 6.2 exactly."""

from __future__ import annotations

import dataclasses
import typing

import pytest

from jukebox.models import Job, Track


def test_track_fields_match_spec():
    assert [f.name for f in dataclasses.fields(Track)] == [
        "id",
        "title",
        "style",
        "mood",
        "theme",
        "duration_s",
        "vocal",
        "lyrics",
        "audio_path",
        "cover_path",
        "cover_prompt",
        "source",
        "seed",
        "created_at",
    ]
    hints = typing.get_type_hints(Track)
    assert hints["theme"] == str | None
    assert hints["lyrics"] == str | None
    assert hints["cover_path"] == str | None
    assert hints["cover_prompt"] == str | None
    assert hints["seed"] == int | None
    assert hints["duration_s"] is int
    assert hints["vocal"] is bool
    assert typing.get_args(hints["source"]) == ("sample", "generated")


def test_job_fields_match_spec():
    assert [f.name for f in dataclasses.fields(Job)] == [
        "id",
        "kind",
        "status",
        "stage",
        "track_id",
        "error",
        "started_at",
        "finished_at",
    ]
    hints = typing.get_type_hints(Job)
    assert typing.get_args(hints["kind"]) == ("song", "cover", "dj")
    assert typing.get_args(hints["status"]) == ("queued", "running", "succeeded", "failed")
    assert hints["track_id"] == str | None
    assert hints["error"] == str | None
    assert hints["finished_at"] == str | None


def test_track_round_trips_through_dict(make_track):
    track = make_track(cover_path="runtime/generated/abc123.png", cover_prompt="a road at night")
    assert Track.from_dict(track.to_dict()) == track


def test_instrumental_track_round_trips_with_none_fields(make_track):
    track = make_track(vocal=False, lyrics=None, theme=None, seed=None)
    assert Track.from_dict(track.to_dict()) == track


def test_job_round_trips_through_dict():
    job = Job(
        id="j1",
        kind="song",
        status="queued",
        stage="Queued",
        track_id=None,
        error=None,
        started_at="2026-10-19T12:00:00+00:00",
        finished_at=None,
    )
    assert Job.from_dict(job.to_dict()) == job


def test_from_dict_rejects_missing_field(make_track):
    data = make_track().to_dict()
    del data["title"]
    with pytest.raises(ValueError, match="title"):
        Track.from_dict(data)


def test_from_dict_rejects_unknown_field(make_track):
    data = make_track().to_dict()
    data["bpm"] = 90
    with pytest.raises(ValueError, match="bpm"):
        Track.from_dict(data)


def test_from_dict_rejects_unknown_source(make_track):
    data = make_track().to_dict()
    data["source"] = "uploaded"
    with pytest.raises(ValueError, match="source"):
        Track.from_dict(data)


def test_from_dict_rejects_wrong_types(make_track):
    data = make_track().to_dict()
    data["duration_s"] = "sixty"
    with pytest.raises(ValueError, match="duration_s"):
        Track.from_dict(data)
    data = make_track().to_dict()
    data["vocal"] = "yes"
    with pytest.raises(ValueError, match="vocal"):
        Track.from_dict(data)


def test_from_dict_rejects_non_mapping():
    with pytest.raises(ValueError):
        Track.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]


# ---- values, not just types ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("id", "   "),
        ("audio_path", ""),
        ("audio_path", "  "),
        ("duration_s", 0),
        ("duration_s", -5),
        ("created_at", ""),
        ("created_at", "garbage"),
        ("created_at", "2026-13-45T99:00:00"),
    ],
)
def test_from_dict_rejects_bad_values(make_track, field, value):
    data = make_track().to_dict()
    data[field] = value
    with pytest.raises(ValueError, match=field):
        Track.from_dict(data)


def test_building_a_track_directly_rejects_bad_values_too(make_track):
    with pytest.raises(ValueError, match="id"):
        make_track(id="")
    with pytest.raises(ValueError, match="duration_s"):
        make_track(duration_s=-1)


@pytest.mark.parametrize(
    "stamp", ["2026-10-19T12:00:00+00:00", "2026-10-19T12:00:00Z", "2026-10-19T12:00:00"]
)
def test_iso_8601_timestamps_are_accepted(make_track, stamp):
    assert make_track(created_at=stamp).created_at == stamp


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_s", True),
        ("duration_s", 0.0),
        ("duration_s", -1.5),
        ("duration_s", "60"),
        ("id", None),
        ("audio_path", None),
        ("created_at", 5),
        ("cover_path", ""),
        ("cover_path", "   "),
    ],
)
def test_building_a_track_directly_checks_types_and_values_like_from_dict(make_track, field, value):
    with pytest.raises(ValueError, match=field):
        make_track(**{field: value})
    data = make_track().to_dict()
    data[field] = value
    with pytest.raises(ValueError, match=field):
        Track.from_dict(data)


def test_a_missing_cover_is_none_not_an_empty_string(make_track):
    assert make_track(cover_path=None).cover_path is None
