"""ACE-Step 1.5 XL Turbo on port 9007: the only music model the app uses (PROJECT.md 7.0, 7.2).

Request format (PROJECT.md 7.1, docs/spikes/B2-acestep.md): an asynchronous job API in three steps.

  1. `POST /release_task` submits the job and returns `data.task_id`. It is sent once, never retried:
     a submit that timed out may already be queued, and a retry would start a second job on the shared
     class GPU. `batch_size` is always 1 (the server's default of 2 makes two songs per request).
  2. `POST /query_result` with `{"task_id_list": [id]}` is polled once a second. `status` is 0 while the
     job runs, 1 when it succeeded, 2 when it failed. `result` is a JSON *string* holding a list of
     results with `file` and `dit_model`.
  3. `GET` the result's `file` value (`/v1/audio?path=...`) downloads the audio.

Every failure is a `ServiceError(service="acestep", ...)`. The server's `progress_text` and file paths
contain its private file system paths, so they never go into an error or a log line.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import PurePosixPath
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, urlsplit

from jukebox.clients.base import ServiceClient
from jukebox.config import Config, ConfigError
from jukebox.errors import ServiceError

SUBMIT_PATH = "/release_task"
POLL_PATH = "/query_result"
EXPECTED_MODEL = "acestep-v15-xl-turbo"  # what every result reports as dit_model (B2)
INSTRUMENTAL = "[Instrumental]"
MIN_DURATION_S, MAX_DURATION_S = 10, 600  # documented range (ACE-Step 1.5 API docs)
POLL_INTERVAL_S = 1.0
SUBMIT_TIMEOUT_S = 30.0
POLL_TIMEOUT_S = 10.0
DOWNLOAD_TIMEOUT_S = 60.0
AUDIO_EXTENSIONS = {"mp3", "wav", "flac", "opus", "aac"}

PENDING, SUCCEEDED, FAILED = 0, 1, 2
TRANSIENT = ("timeout", "unavailable")  # worth trying again while the job deadline allows


class AceStepClient:
    """A music client bound to the ACE-Step service and its configured base URL."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = ServiceClient("acestep", config, sleep=sleep, clock=clock)
        self._sleep = sleep
        self._clock = clock
        # ACESTEP_TIMEOUT_S limits the whole job (submit, polls, download), not one request.
        self._job_timeout_s = float(self._http.timeout.read or 300.0)

    @property
    def service(self) -> str:
        return self._http.service

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AceStepClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def generate_music(
        self, *, tags: str, lyrics: str | None, duration_s: int, seed: int | None = None
    ) -> tuple[bytes, str]:
        """Generate one song and return `(audio_bytes, file_extension)`.

        `lyrics` of None or blank makes an instrumental. `seed` is sent and logged by the server, but it
        does not reproduce the same audio (B2), so commit generated files instead of regenerating them.
        """
        if not MIN_DURATION_S <= duration_s <= MAX_DURATION_S:
            raise ServiceError(
                "acestep",
                "bad_request",
                f"duration_s={duration_s} is out of range",
                reason=f"Duration must be between {MIN_DURATION_S} and {MAX_DURATION_S} seconds.",
            )
        # ACESTEP_TIMEOUT_S limits the whole job. Every request gets at most the time that is left.
        deadline = self._clock() + self._job_timeout_s
        task_id = self._submit(self._job_body(tags, lyrics, duration_s, seed), deadline)
        file_ref = self._wait_for_result(task_id, deadline)
        return self._download(file_ref, deadline)

    # ---- the three steps -----------------------------------------------------------------------

    def _job_body(self, tags: str, lyrics: str | None, duration_s: int, seed: int | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": tags,
            "lyrics": lyrics if lyrics and lyrics.strip() else INSTRUMENTAL,
            "audio_duration": duration_s,
            "audio_format": "mp3",
            "inference_steps": 8,
            "batch_size": 1,
            "thinking": False,
            "vocal_language": "en",
            "use_random_seed": seed is None,
        }
        if seed is not None:
            body["seed"] = seed
        if self._http.model:
            body["model"] = self._http.model  # accepted; any value still runs the XL Turbo model (B2)
        return body

    def _submit(self, body: dict[str, Any], deadline: float) -> str:
        timeout = min(SUBMIT_TIMEOUT_S, self._time_left(deadline))
        try:
            response = self._http.request("POST", SUBMIT_PATH, json=body, retry=False, timeout=timeout)
        except ServiceError as e:
            # A 404 here does mean a wrong address, so `config` stays; the server's text is still dropped.
            raise _without_server_details(e, "submitting the job", keep_config=True) from None
        data = self._http.json_body(response)
        task = data.get("data") if isinstance(data, dict) else None
        task_id = task.get("task_id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise _bad_response("the submit reply had no task_id")
        return task_id

    def _wait_for_result(self, task_id: str, deadline: float) -> str:
        """Poll until the job finishes, then return its `file` value.

        The job is already running on the GPU, so a poll that times out or finds the server briefly
        unavailable is not the end of it: keep polling until the deadline. Giving up would make the user's
        Retry submit a second job.
        """
        while True:
            timeout = min(POLL_TIMEOUT_S, self._time_left(deadline))
            try:
                item = self._poll(task_id, timeout)
            except ServiceError as e:
                if e.kind not in TRANSIENT:
                    raise
                item = None
            status = item.get("status") if item else PENDING
            if status == SUCCEEDED:
                return _file_from_result(item.get("result"))
            if status == FAILED:
                raise _bad_response("the server reported that the job failed")
            if status != PENDING:
                raise _bad_response(f"unknown job status {status!r}"[:80])
            self._sleep(min(POLL_INTERVAL_S, max(0.0, deadline - self._clock())))

    def _poll(self, task_id: str, timeout: float) -> dict | None:
        """The job's entry from /query_result, or None if the server has not listed it yet.

        One attempt per poll (`retry=False`): the polling loop already retries, and the base client's own
        retry would let one poll run past the deadline.
        """
        try:
            response = self._http.request(
                "POST", POLL_PATH, json={"task_id_list": [task_id]}, retry=False, timeout=timeout
            )
        except ServiceError as e:
            raise _without_server_details(e, "polling the job") from None
        data = self._http.json_body(response)
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise _bad_response("the poll reply had no data list")
        for item in items:
            if isinstance(item, dict) and item.get("task_id") in (task_id, None):
                return item
        return None

    def _download(self, file_ref: str, deadline: float) -> tuple[bytes, str]:
        """Download the audio, retrying once on a timeout or outage while time is left."""
        for attempt in (1, 2):
            timeout = min(DOWNLOAD_TIMEOUT_S, self._time_left(deadline))
            try:
                response = self._http.request("GET", file_ref, retry=False, timeout=timeout)
                break
            except ServiceError as e:
                if e.kind not in TRANSIENT or attempt == 2:
                    raise _without_server_details(e, "downloading the audio") from None
        audio = response.content
        if not audio:
            raise _bad_response("the downloaded audio was empty")
        return audio, _extension(file_ref)

    def _time_left(self, deadline: float) -> float:
        """Seconds before the job deadline, or a timeout error if it has passed."""
        left = deadline - self._clock()
        if left <= 0:
            raise ServiceError(
                "acestep", "timeout", f"the job did not finish within {self._job_timeout_s:g} s"
            )
        return left


def _file_from_result(result: Any) -> str:
    """Parse the `result` JSON string, check which model ran, and return the audio `file` value."""
    try:
        entries = json.loads(result) if isinstance(result, str) else None
    except ValueError:
        entries = None
    first = entries[0] if isinstance(entries, list) and entries else None
    if not isinstance(first, dict):
        raise _bad_response("the job result could not be read")
    model = first.get("dit_model")
    if model != EXPECTED_MODEL:
        raise _bad_response(f"expected dit_model {EXPECTED_MODEL}, got {str(model)[:40]!r}")
    file_ref = first.get("file")
    if not isinstance(file_ref, str) or not file_ref.startswith("/"):
        raise _bad_response("the job result had no audio file")
    return file_ref


def _extension(file_ref: str) -> str:
    path = parse_qs(urlsplit(file_ref).query).get("path", [""])[0]
    ext = PurePosixPath(path).suffix.lstrip(".").lower()
    return ext if ext in AUDIO_EXTENSIONS else "mp3"


def _without_server_details(error: ServiceError, step: str, *, keep_config: bool = False) -> ServiceError:
    """The same failure without the server's reply text, which can hold its private file paths.

    A 404 while polling or downloading means the job or its audio is gone, not that the settings are wrong
    (PROJECT.md 7.2), so `config` becomes `bad_response` unless `keep_config`. A server reason is kept for
    the user only if it contains no path.
    """
    kind = "bad_response" if error.kind == "config" and not keep_config else error.kind
    status = error.detail.split(":", 1)[0] if error.detail.startswith("HTTP ") else error.kind
    reason = error.reason if kind == "bad_request" and error.reason and not _has_path(error.reason) else None
    return ServiceError("acestep", kind, f"{step} failed ({status})", reason=reason)


def _has_path(text: str) -> bool:
    return "/" in text or "\\" in text


def _bad_response(detail: str) -> ServiceError:
    return ServiceError("acestep", "bad_response", detail)


# ---- module-level API (PROJECT.md 7.2) ----------------------------------------------------------

_default: AceStepClient | None = None
_default_lock = threading.Lock()


def _make_default_client() -> AceStepClient:
    return AceStepClient()


def _get_default() -> AceStepClient:
    """The shared client, created on first use. A settings problem becomes ServiceError(kind="config"),
    because feature code catches only ServiceError (PROJECT.md 7.3). Nothing is cached on failure.
    ConfigError lists variable names and problems, never values."""
    global _default
    with _default_lock:
        if _default is None:
            try:
                _default = _make_default_client()
            except ConfigError as e:
                raise ServiceError("acestep", "config", "; ".join(e.problems)[:300]) from None
        return _default


def generate_music(
    *, tags: str, lyrics: str | None, duration_s: int, seed: int | None = None
) -> tuple[bytes, str]:
    """Generate one song with ACE-Step. Returns (audio_bytes, file_extension); raises ServiceError."""
    return _get_default().generate_music(tags=tags, lyrics=lyrics, duration_s=duration_s, seed=seed)
