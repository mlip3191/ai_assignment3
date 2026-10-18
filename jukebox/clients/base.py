"""Shared HTTP client for the class services (PROJECT.md 7.2).

One place for auth, timeouts, one retry, error mapping, and redacted logging. It knows nothing
about any service's request format: each service client (qwen.py, flux.py, ...) builds on it and
supplies paths and bodies from the documented format in PROJECT.md 7.1.

  - Only the service's own configured base URL can be called; anything else raises
    ServiceError(kind="config") before a request is sent.
  - One retry, with backoff, on timeouts, connection errors, and 502/503/504. Never on 4xx.
    `request(..., retry=False)` opts out for calls that start work on the server.
  - HTTP 404 is a wrong path or base URL, so it maps to ServiceError(kind="config").
  - One log line per attempt: `service -> host:port status duration` (TC-15 evidence). Never
    headers or bodies, and the key is scrubbed from every record on any `jukebox.*` logger.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

import httpx

from jukebox.config import SERVICES, Config, load_config
from jukebox.errors import MAX_REASON_CHARS, Kind, Service, ServiceError, redact

logger = logging.getLogger("jukebox.clients")

CONNECT_TIMEOUT_S = 10.0
BACKOFF_S = 0.5
RETRY_STATUSES = frozenset({502, 503, 504})
MAX_DETAIL_CHARS = 300
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


_SECRETS: set[str] = set()  # every API key a ServiceClient was built with
_REDACTING = "_jukebox_redacting"


def _install_log_redaction() -> None:
    """Scrub the API key and Authorization-like text from every log record under `jukebox` / `jukebox.*`.

    A logger's filters only see records logged on that exact logger, never records from its children, so a
    filter on `jukebox.clients` would miss `logging.getLogger("jukebox.clients.flux")`. A record factory runs
    for every record as it is created, so a plain `logging.getLogger(__name__)` in any client or service is
    safe by default. Installing it twice does not stack wrappers.

    Limits: only the formatted message is scrubbed, not `exc_info` tracebacks or `extra=` fields. The errors
    this package raises are redacted when they are built, so do not put the key in other exceptions.
    """
    current = logging.getLogRecordFactory()
    if getattr(current, _REDACTING, False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        if record.name == "jukebox" or record.name.startswith("jukebox."):
            secrets = tuple(_SECRETS)  # a snapshot: another client may register its key meanwhile
            try:
                record.msg = redact(record.getMessage(), secrets)
            except Exception:
                # A malformed log call (wrong number or type of arguments), or an argument that cannot be
                # printed. Stock logging would defer this to the handler, which swallows it; never raise
                # from here, and never leave the arguments for logging's own error report to print.
                try:
                    record.msg = redact(f"{record.msg} {record.args!r}", secrets)
                except Exception:
                    record.msg = "<unprintable log message>"
            record.args = ()
        return record

    setattr(factory, _REDACTING, True)
    logging.setLogRecordFactory(factory)


_install_log_redaction()


class ServiceClient:
    """A synchronous HTTP client bound to one class service and its configured base URL."""

    def __init__(
        self,
        service: Service,
        config: Config | None = None,
        *,
        auth_header: str = "Authorization",
        auth_scheme: str | None = "Bearer",
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if service not in SERVICES:
            raise ValueError(f"unknown service {service!r}")
        config = config or load_config()
        settings = getattr(config, service)
        self.service: Service = service
        self.base_url: str = settings.base_url
        self.model: str | None = settings.model
        self.timeout = httpx.Timeout(settings.timeout_s, connect=CONNECT_TIMEOUT_S)
        parts = urlsplit(self.base_url)
        self._origin = (parts.scheme, parts.hostname, parts.port)
        self._host_port = f"{parts.hostname}:{parts.port}"
        key = config.api_key.reveal()
        _SECRETS.add(key)
        self._auth = {auth_header: f"{auth_scheme} {key}" if auth_scheme else key}
        self._sleep = sleep
        self._clock = clock
        self._http = httpx.Client(timeout=self.timeout, follow_redirects=False)

    # ---- lifecycle ----------------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ServiceClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ---- requests -----------------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str = "",
        *,
        json: Any = None,
        data: Any = None,
        content: Any = None,
        files: Any = None,
        params: Any = None,
        headers: dict[str, str] | None = None,
        retry: bool = True,
        timeout: Any = httpx.USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
        """Send one request and return the 2xx response, or raise ServiceError.

        `retry=False` makes exactly one attempt. Use it for a call that starts work on the shared class
        servers (ACE-Step's `/release_task`): a request that times out may still have been accepted, and
        a retry would start a second job. `timeout` (seconds, or an `httpx.Timeout`) overrides the
        service's timeout for this request only, for example short polls inside a long job. `timeout=None`
        means no timeout at all (httpx semantics), so a hung server would block forever: avoid it.
        """
        url = self._resolve(path)
        sent_headers = {**self._auth, **(headers or {})}
        attempts = 2 if retry else 1
        for attempt in range(1, attempts + 1):
            started = self._clock()
            retryable = True
            try:
                response = self._http.request(
                    method,
                    url,
                    headers=sent_headers,
                    json=json,
                    data=data,
                    content=content,
                    files=files,
                    params=params,
                    timeout=timeout,
                )
            except httpx.TimeoutException as e:
                label, error = "timeout", self._error("timeout", type(e).__name__)
            except httpx.TransportError as e:
                label, error = "error", self._error("unavailable", type(e).__name__)
            except httpx.RequestError as e:
                label, error, retryable = "error", self._error("bad_response", type(e).__name__), False
            else:
                label = str(response.status_code)
                if 200 <= response.status_code < 300:
                    self._log(label, started)
                    return response
                error = self._status_error(response)
                retryable = response.status_code in RETRY_STATUSES
            self._log(label, started)
            if attempt == attempts or not retryable:
                raise error
            self._sleep(BACKOFF_S)
        raise AssertionError("unreachable")  # pragma: no cover

    def json_body(self, response: httpx.Response) -> Any:
        """Parse a JSON body, or raise ServiceError(kind="bad_response")."""
        try:
            return response.json()
        except ValueError:
            raise self._error("bad_response", "response body was not valid JSON") from None

    # ---- helpers ------------------------------------------------------------------------------

    def _resolve(self, path: str) -> str:
        """Join a path onto the base URL; refuse any URL that points anywhere else."""
        if path.startswith("//") or _SCHEME.match(path):
            target = path
        else:
            target = self.base_url.rstrip("/") + "/" + path.lstrip("/") if path else self.base_url
        try:
            parts = urlsplit(target)
            origin = (parts.scheme, parts.hostname, parts.port)
            userinfo = parts.username or parts.password
        except ValueError:
            origin, userinfo = None, None
        if origin != self._origin or userinfo:
            raise self._error("config", f"refused a URL outside the configured {self.service} endpoint")
        return target

    def _log(self, label: str, started: float) -> None:
        ms = round((self._clock() - started) * 1000)
        logger.info("%s -> %s %s %dms", self.service, self._host_port, label, ms)

    def _clean(self, text: str) -> str:
        return redact(text, tuple(_SECRETS))

    def _error(self, kind: Kind, detail: str, *, reason: str | None = None) -> ServiceError:
        return ServiceError(self.service, kind, self._clean(detail)[:MAX_DETAIL_CHARS], reason=reason)

    def _status_error(self, response: httpx.Response) -> ServiceError:
        status = response.status_code
        try:
            snippet = response.text[:MAX_DETAIL_CHARS]
        except Exception:
            snippet = ""
        detail = f"HTTP {status}: {snippet}"
        if status in (401, 403):
            return self._error("auth", detail)
        if status == 429 or status in RETRY_STATUSES:
            return self._error("unavailable", detail)
        if status == 404:
            # A wrong request path or server address (the config already strips a pasted /v1 from the base
            # URL), not something the user typed. A client that knows 404 means something else can catch
            # this and raise its own kind.
            return self._error("config", detail)
        if 400 <= status < 500:
            reason = _server_message(response)
            if reason:
                reason = self._clean(reason)[:MAX_REASON_CHARS]
            return self._error("bad_request", detail, reason=reason)
        return self._error("bad_response", detail)


def _server_message(response: httpx.Response) -> str | None:
    """The human-readable message in a JSON error body, if there is one."""
    try:
        body = response.json()
    except ValueError:
        return None
    return _find_message(body, depth=0)


def _find_message(value: Any, depth: int) -> str | None:
    if depth > 3:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list) and value:
        return _find_message(value[0], depth + 1)
    if isinstance(value, dict):
        for key in ("detail", "message", "error", "msg"):
            if key in value and (found := _find_message(value[key], depth + 1)):
                return found
    return None
