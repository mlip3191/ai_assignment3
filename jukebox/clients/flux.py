"""FLUX.2 klein 4B on port 9006: cover-art images (PROJECT.md 7.0, 7.2).

The request and reply follow the FLUX row of PROJECT.md 7.1 and docs/spikes/C1-flux.md:
`POST /v1/images/generations` with a JSON body, reply image as base64 in `data[0].b64_json`.

This module does no logging of its own: the shared client logs one redacted line per request.
"""

from __future__ import annotations

import base64
import binascii
import threading
from typing import Any

from jukebox.clients.base import ServiceClient
from jukebox.config import Config, ConfigError
from jukebox.errors import ServiceError

PATH = "/v1/images/generations"
OUTPUT_FORMAT = "jpeg"
# For JPEG this is the encoder quality. 90 gives about 0.15 MB per 1024x1024 cover instead of
# about 1.4 MB as compressed PNG, at the same speed (C1 follow-up on #4; release lead's choice).
OUTPUT_COMPRESSION = 90
SIGNATURE = b"\xff\xd8\xff"  # every JPEG starts with an SOI marker followed by another marker


def generate_image(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    config: Config | None = None,
    client: ServiceClient | None = None,
) -> bytes:
    """Generate one image and return its JPEG bytes, or raise ServiceError(service="flux").

    `client` and `config` are for tests and callers that already hold one. By default the shared FLUX
    client is used, built from the app's settings on first use (the same pattern as the other clients)
    and built again after a failed call, so a fixed setting takes effect on the next try.
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt must not be empty")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if client is not None and client.service != "flux":
        raise ValueError(f"generate_image needs a flux client, not {client.service!r}")

    if client is not None:
        return _generate(client, prompt, width, height, seed)
    if config is not None:
        with ServiceClient("flux", config) as own_client:
            return _generate(own_client, prompt, width, height, seed)
    shared = _get_default()
    try:
        return _generate(shared, prompt, width, height, seed)
    except ServiceError:
        _forget(shared)  # the next call (Retry cover) reads the settings again (#74, TC-F5)
        raise


def _generate(flux_client: ServiceClient, prompt: str, width: int, height: int, seed: int | None) -> bytes:
    body = _request_body(prompt, width, height, seed, flux_client.model)
    response = flux_client.request("POST", PATH, json=body)
    return _image_bytes(flux_client.json_body(response))


# ---- the shared client --------------------------------------------------------------------------

_default: ServiceClient | None = None
_default_lock = threading.Lock()


def _make_default_client() -> ServiceClient:
    return ServiceClient("flux")


def _get_default() -> ServiceClient:
    """The shared client, created on first use. A settings problem becomes ServiceError(kind="config"),
    because feature code catches only ServiceError (PROJECT.md 7.3). Nothing is cached on failure, so
    fixing .env and retrying works. ConfigError lists variable names and problems, never values."""
    global _default
    with _default_lock:
        if _default is None:
            try:
                _default = _make_default_client()
            except ConfigError as e:
                raise ServiceError("flux", "config", "; ".join(e.problems)[:300]) from None
        return _default


def _forget(failed: ServiceClient) -> None:
    """Drop the shared client after a failed call, so the next call builds one from the settings as they
    are now: a FLUX address or key fixed in .env works on Retry cover without a restart. Only `failed` is
    dropped, never a newer client another call already built. It is not closed here, because another
    cover may still be using it; its connections are freed once nothing holds it any more."""
    global _default
    with _default_lock:
        if _default is failed:
            _default = None


def _request_body(
    prompt: str, width: int, height: int, seed: int | None, model: str | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"prompt": prompt}
    if model:
        body["model"] = model
    body.update(
        {
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
            "output_format": OUTPUT_FORMAT,
            "output_compression": OUTPUT_COMPRESSION,
        }
    )
    if seed is not None:
        body["seed"] = seed
    return body


def _image_bytes(payload: Any) -> bytes:
    try:
        encoded = payload["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError):
        raise _bad("reply has no data[0].b64_json") from None
    if not isinstance(encoded, str) or not encoded:
        raise _bad("data[0].b64_json is empty")
    try:
        # Line breaks are legal in base64; anything else outside the alphabet is still rejected.
        raw = base64.b64decode(encoded.replace("\r", "").replace("\n", ""), validate=True)
    except (binascii.Error, ValueError):
        raise _bad("data[0].b64_json is not valid base64") from None
    if not raw.startswith(SIGNATURE):
        raise _bad(f"image is not {OUTPUT_FORMAT.upper()}")
    return raw


def _bad(detail: str) -> ServiceError:
    return ServiceError("flux", "bad_response", detail)
