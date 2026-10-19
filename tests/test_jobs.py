"""The job store: stage, status and user-facing error per job (PROJECT.md 6.2, R5)."""

from __future__ import annotations

import itertools
import threading

import pytest

from jukebox.errors import ServiceError
from jukebox.jobs import JobError, JobStore

CLOCK = itertools.count()


@pytest.fixture
def store() -> JobStore:
    return JobStore(now=lambda: f"2026-10-19T12:00:{next(CLOCK)}+00:00")


def test_create_starts_queued(store):
    job = store.create("song")
    assert job.kind == "song"
    assert job.status == "queued"
    assert job.stage
    assert job.track_id is None
    assert job.error is None
    assert job.started_at
    assert job.finished_at is None
    assert store.get(job.id) == job


def test_job_ids_are_unique(store):
    assert len({store.create("song").id for _ in range(20)}) == 20


def test_create_rejects_unknown_kind(store):
    with pytest.raises(JobError, match="kind"):
        store.create("video")  # type: ignore[arg-type]


def test_lifecycle_stage_updates_then_success(store):
    job = store.create("song")
    running = store.set_stage(job.id, "Writing lyrics…")
    assert (running.status, running.stage) == ("running", "Writing lyrics…")
    assert store.set_stage(job.id, "Composing music…").stage == "Composing music…"
    done = store.succeed(job.id, track_id="t1")
    assert done.status == "succeeded"
    assert done.track_id == "t1"
    assert done.finished_at is not None
    assert done.error is None
    assert store.get(job.id) == done


def test_fail_with_service_error_stores_the_user_message_only(store):
    job = store.create("cover")
    err = ServiceError("flux", "timeout", "GET http://host:9006 Authorization: Bearer sk-secret-123")
    failed = store.fail(job.id, err)
    assert failed.status == "failed"
    assert failed.error == "The FLUX service took too long to respond. The class servers may be busy."
    assert "sk-secret-123" not in failed.error
    assert failed.finished_at is not None


def test_fail_with_text_is_redacted(store):
    job = store.create("song")
    failed = store.fail(job.id, "boom Authorization: Bearer sk-secret-123")
    assert "sk-secret-123" not in failed.error
    assert failed.error.startswith("boom")


def test_failure_keeps_the_last_stage_for_context(store):
    job = store.create("song")
    store.set_stage(job.id, "Composing music…")
    assert store.fail(job.id, "nope").stage == "Composing music…"


def test_finished_job_cannot_change(store):
    job = store.create("dj")
    store.succeed(job.id)
    with pytest.raises(JobError, match="finished"):
        store.set_stage(job.id, "again")
    with pytest.raises(JobError, match="finished"):
        store.fail(job.id, "late")
    assert store.get(job.id).status == "succeeded"


def test_unknown_job_id(store):
    assert store.get("nope") is None
    with pytest.raises(JobError, match="nope"):
        store.set_stage("nope", "x")
    with pytest.raises(JobError, match="nope"):
        store.succeed("nope")
    with pytest.raises(JobError, match="nope"):
        store.fail("nope", "x")


def test_returned_jobs_are_copies(store):
    job = store.create("song")
    store.get(job.id).stage = "changed outside the lock"
    assert store.get(job.id).stage == job.stage


def test_list_in_creation_order(store):
    ids = [store.create("song").id for _ in range(3)]
    assert [j.id for j in store.list()] == ids


def test_concurrent_jobs(store):
    count = 40
    start = threading.Barrier(count)
    created: list[str] = []
    lock = threading.Lock()

    def worker():
        start.wait()
        job = store.create("song")
        store.set_stage(job.id, "Composing music…")
        store.succeed(job.id, track_id=job.id)
        with lock:
            created.append(job.id)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.list()) == count
    assert all(j.status == "succeeded" and j.track_id == j.id for j in store.list())
