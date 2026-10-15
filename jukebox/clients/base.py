"""Shared HTTP client for the class services (PROJECT.md 7.2).

One place for auth, timeouts, one retry, error mapping, and redacted logging. It knows nothing
about any service's request format: each service client (qwen.py, flux.py, ...) builds on it and
supplies paths and bodies from the documented format in PROJECT.md 7.1.

  - Only the service's own configured base URL can be called; anything else raises
    ServiceError(kind="config") before a request is sent.
  - One retry, with backoff, on timeouts, connection errors, and 502/503/504. Never on 4xx.
  - One log line per attempt: `service -> host:port status duration` (TC-15 evidence). Never
    headers or bodies, and the key is scrubbed from every record on the logger.
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


class _RedactFilter(logging.Filter):
    """Scrubs the API key and Authorization-like text from every record on the clients logger."""

    def __init__(self) -> None:
        super().__init__()
        self.secrets: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self.secrets)
        record.args = ()
        return True


_redactor = _RedactFilter()
logger.addFilter(_redactor)


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
        _redactor.secrets.add(key)
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
    ) -> httpx.Response:
        """Send one request and return the 2xx response, or raise ServiceError."""
        url = self._resolve(path)
        sent_headers = {**self._auth, **(headers or {})}
        for attempt in (1, 2):
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
            if attempt == 2 or not retryable:
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
        return redact(text, _redactor.secrets)

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
