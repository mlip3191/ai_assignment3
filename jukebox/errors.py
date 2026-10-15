"""The error model (PROJECT.md 7.3): ServiceError, user-facing messages, and secret redaction.

The UI shows `user_message(err)`, never a raw exception. `ServiceError.detail` is for logs and is
already redacted by whoever builds it (see `redact`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal, get_args

Service = Literal["qwen", "flux", "acestep", "chatterbox"]
Kind = Literal["config", "auth", "timeout", "unavailable", "bad_request", "bad_response"]
Recovery = Literal["retry", "fix_and_restart", "edit_inputs"]

SERVICE_NAMES: dict[str, str] = {
    "qwen": "Qwen",
    "flux": "FLUX",
    "acestep": "ACE-Step",
    "chatterbox": "Chatterbox",
}
MAX_REASON_CHARS = 200

_MESSAGES: dict[str, str] = {
    "config": "The {service} endpoint isn't configured. Check `.env` against `.env.example`.",
    "auth": "The {service} service rejected our credentials. Check the API key in `.env`.",
    "timeout": "The {service} service took too long to respond. The class servers may be busy.",
    "unavailable": "The {service} service is unreachable right now.",
    "bad_request": "{service} couldn't process that request: {reason}.",
    "bad_response": "{service} returned something unexpected.",
}
_RECOVERY: dict[str, Recovery | None] = {
    "config": None,  # the startup check catches this first
    "auth": "fix_and_restart",
    "timeout": "retry",
    "unavailable": "retry",
    "bad_request": "edit_inputs",
    "bad_response": "retry",
}


class ServiceError(Exception):
    """A failed call to one of the four class services.

    `detail` is developer text for logs. `reason` is a short, already-redacted explanation that is
    safe to show a user (only used for `bad_request`).
    """

    def __init__(self, service: Service, kind: Kind, detail: str = "", *, reason: str | None = None):
        if service not in get_args(Service):
            raise ValueError(f"unknown service {service!r}")
        if kind not in get_args(Kind):
            raise ValueError(f"unknown error kind {kind!r}")
        self.service = service
        self.kind = kind
        self.detail = detail
        self.reason = reason
        super().__init__(f"{service}: {kind}" + (f": {detail}" if detail else ""))


def user_message(err: ServiceError) -> str:
    """The sentence the UI shows for this error (PROJECT.md 7.3). Never includes `detail`."""
    reason = (err.reason or "the request was not accepted").strip()
    if len(reason) > MAX_REASON_CHARS:
        reason = reason[: MAX_REASON_CHARS - 3].rstrip() + "..."
    reason = reason.rstrip(".")
    return _MESSAGES[err.kind].format(service=SERVICE_NAMES[err.service], reason=reason)


def recovery(err: ServiceError) -> Recovery | None:
    """What the UI should offer: a Retry button, a fix-and-restart note, or editable inputs."""
    return _RECOVERY[err.kind]


# ---- redaction (H8) ---------------------------------------------------------------------------

MIN_SECRET_CHARS = 4  # shorter strings would mangle ordinary text
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:(?:bearer|basic|token)\s+)?[^\s,;'\"}]+")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]+")
_KEY_PAIR = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|secret|token|password|passwd)[\"']?\s*[:=]\s*[\"']?)[^\s,&;'\"}]+"
)


def redact(text: str, secrets: Iterable[str | None] = ()) -> str:
    """Remove known secrets, Authorization headers, bearer tokens, and key=value pairs from text."""
    for secret in secrets:
        if secret and len(secret) >= MIN_SECRET_CHARS:
            text = text.replace(secret, "****")
    text = _AUTH_HEADER.sub(r"\1****", text)
    text = _BEARER.sub(r"\1****", text)
    return _KEY_PAIR.sub(r"\1****", text)
