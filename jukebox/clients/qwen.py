"""Qwen3.6-35B-A3B on port 9001: the only text model the app uses (PROJECT.md 7.0, 7.2).

Request format (PROJECT.md 7.1, docs/spikes/B1-qwen.md): `POST /v1/chat/completions`, OpenAI-compatible
and synchronous. Thinking is on by default on the class server, and it can use up the whole token
budget and return no reply at all, so every request turns it off with
`chat_template_kwargs: {"enable_thinking": false}`. The reply text is `choices[0].message.content`.
The separate `message.reasoning` field is ignored, and any `<think>` text that still appears in the
reply is stripped.

Feature code calls the module-level `chat()` / `chat_json()`, which share one client created on first
use from the app's configuration. Tests and scripts can build a `QwenClient` with their own config.
Every failure is a `ServiceError(service="qwen", ...)`.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any

from jukebox.clients.base import ServiceClient
from jukebox.config import Config
from jukebox.errors import ServiceError

CHAT_PATH = "/v1/chat/completions"
NO_THINKING = {"enable_thinking": False}
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


class QwenClient:
    """A chat client bound to the Qwen service and its configured base URL."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = ServiceClient("qwen", config, sleep=sleep, clock=clock)

    @property
    def service(self) -> str:
        return self._http.service

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> QwenClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def chat(self, messages: list[dict], *, max_tokens: int = 600, temperature: float = 0.8) -> str:
        """Send a chat and return the reply text, with any thinking removed."""
        return self._complete(messages, max_tokens=max_tokens, temperature=temperature)

    def chat_json(
        self,
        messages: list[dict],
        *,
        schema: dict | None = None,
        schema_name: str = "reply",
        max_tokens: int = 600,
        temperature: float = 0.8,
    ) -> dict:
        """Send a chat that should be answered with one JSON object, and return it parsed.

        With `schema`, the server is asked to follow it (`response_format`, a JSON schema). Either way
        the reply goes through `parse_json_reply`, which tolerates code fences or extra text around
        the object. Anything else raises `ServiceError(kind="bad_response")`.
        """
        response_format = None
        if schema is not None:
            response_format = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema}}
        text = self._complete(
            messages, max_tokens=max_tokens, temperature=temperature, response_format=response_format
        )
        return parse_json_reply(text)

    def _complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        response_format: dict | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": NO_THINKING,
        }
        if self._http.model:
            body["model"] = self._http.model
        if response_format is not None:
            body["response_format"] = response_format

        data = self._http.json_body(self._http.request("POST", CHAT_PATH, json=body))
        choice = _first_choice(data)
        if choice.get("finish_reason") == "length":
            raise _bad_response(f"the reply was cut off at max_tokens={max_tokens}")
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = strip_think(content) if isinstance(content, str) else ""
        if not text:
            raise _bad_response("the reply had no text")
        return text


def strip_think(text: str) -> str:
    """Remove `<think>...</think>` blocks and any thinking left before a stray `</think>`."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    if "<think>" in text:
        text = text.split("<think>", 1)[0]
    return text.strip()


def parse_json_reply(text: str) -> dict:
    """Parse a reply that should be one JSON object.

    Tries the reply as-is first. If that fails, strips thinking and code fences and parses the span from
    the first `{` to the last `}`, so "Here is your song: {...}" still works. Raises
    `ServiceError(kind="bad_response")` if no JSON object can be found.
    """
    for candidate in (text, _outer_object(text)):
        if candidate is None:
            continue
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise _bad_response("the reply was not a JSON object")


def _outer_object(text: str) -> str | None:
    cleaned = _CODE_FENCE.sub("", strip_think(text).strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    return cleaned[start : end + 1] if 0 <= start < end else None


def _first_choice(data: Any) -> dict:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise _bad_response("the reply had no choices")
    return choices[0]


def _bad_response(detail: str) -> ServiceError:
    return ServiceError("qwen", "bad_response", detail)


# ---- module-level API (PROJECT.md 7.2) ----------------------------------------------------------

_default: QwenClient | None = None
_default_lock = threading.Lock()


def _make_default_client() -> QwenClient:
    return QwenClient()


def _get_default() -> QwenClient:
    global _default
    with _default_lock:
        if _default is None:
            _default = _make_default_client()
        return _default


def chat(messages: list[dict], *, max_tokens: int = 600, temperature: float = 0.8) -> str:
    """Send a chat to Qwen and return the reply text. Raises ServiceError on any failure."""
    return _get_default().chat(messages, max_tokens=max_tokens, temperature=temperature)


def chat_json(
    messages: list[dict],
    *,
    schema: dict | None = None,
    schema_name: str = "reply",
    max_tokens: int = 600,
    temperature: float = 0.8,
) -> dict:
    """Send a chat to Qwen that should be answered with one JSON object, and return it parsed."""
    return _get_default().chat_json(
        messages, schema=schema, schema_name=schema_name, max_tokens=max_tokens, temperature=temperature
    )
