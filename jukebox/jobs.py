"""Job tracking for long-running generations (PROJECT.md 6.2, R5).

Handlers create a job, move it through stages, and finish it as succeeded or failed. The UI reads
`stage`, `status` and `error` to show progress. `error` only ever holds a user-facing message.
"""

from __future__ import annotations

import dataclasses
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import get_args

from jukebox.errors import ServiceError, redact, user_message
from jukebox.models import Job, JobKind

FINISHED = ("succeeded", "failed")


class JobError(Exception):
    """A job is unknown, or was changed after it finished."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, *, now: Callable[[], str] = _utc_now) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}  # insertion order = creation order

    def create(self, kind: JobKind, stage: str = "Queued") -> Job:
        if kind not in get_args(JobKind):
            raise JobError(f"unknown job kind {kind!r}")
        job = Job(
            id=uuid.uuid4().hex,
            kind=kind,
            status="queued",
            stage=stage,
            track_id=None,
            error=None,
            started_at=self._now(),
            finished_at=None,
        )
        with self._lock:
            self._jobs[job.id] = job
            return dataclasses.replace(job)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dataclasses.replace(job) if job else None

    def list(self) -> list[Job]:
        with self._lock:
            return [dataclasses.replace(j) for j in self._jobs.values()]

    def set_stage(self, job_id: str, stage: str, track_id: str | None = None) -> Job:
        """Move to a new stage (the job is now running). `track_id` is kept once it is known."""
        with self._lock:
            job = self._open_job(job_id)
            job.status = "running"
            job.stage = stage
            if track_id is not None:
                job.track_id = track_id
            return dataclasses.replace(job)

    def succeed(self, job_id: str, track_id: str | None = None) -> Job:
        with self._lock:
            job = self._open_job(job_id)
            job.status = "succeeded"
            job.error = None
            if track_id is not None:
                job.track_id = track_id
            job.finished_at = self._now()
            return dataclasses.replace(job)

    def fail(self, job_id: str, error: ServiceError | str) -> Job:
        """Finish as failed. A ServiceError becomes its 7.3 message; text is redacted. The stage stays."""
        message = user_message(error) if isinstance(error, ServiceError) else redact(str(error))
        with self._lock:
            job = self._open_job(job_id)
            job.status = "failed"
            job.error = message
            job.finished_at = self._now()
            return dataclasses.replace(job)

    def _open_job(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobError(f"no job {job_id!r}")
        if job.status in FINISHED:
            raise JobError(f"job {job_id!r} already finished ({job.status})")
        return job
