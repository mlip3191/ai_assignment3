"""FLUX.2 klein 4B on port 9006: cover-art images (PROJECT.md 7.0, 7.2).

The request and reply follow the FLUX row of PROJECT.md 7.1 and docs/spikes/C1-flux.md:
`POST /v1/images/generations` with a JSON body, reply image as base64 in `data[0].b64_json`.

This module does no logging of its own: the shared client logs one redacted line per request.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from jukebox.clients.base import ServiceClient
from jukebox.config import Config
from jukebox.errors import ServiceError

PATH = "/v1/images/generations"
OUTPUT_FORMAT = "png"
# 1 is the strongest PNG compression: about 1.4 MB per 1024x1024 cover instead of 3.1 MB,
# lossless, for about 0.6 s extra (C1).
OUTPUT_COMPRESSION = 1
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def generate_image(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    config: Config | None = None,
    client: ServiceClient | None = None,
) -> bytes:
    """Generate one image and return its PNG bytes, or raise ServiceError(service="flux").

    `config` and `client` are for tests and callers that already hold one; by default a FLUX client
    is built from the app's settings and closed afterwards.
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt must not be empty")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if client is not None and client.service != "flux":
        raise ValueError(f"generate_image needs a flux client, not {client.service!r}")

    owned = client is None
    flux_client = client or ServiceClient("flux", config)
    try:
        body = _request_body(prompt, width, height, seed, flux_client.model)
        response = flux_client.request("POST", PATH, json=body)
        return _image_bytes(flux_client.json_body(response))
    finally:
        if owned:
            flux_client.close()


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
        raw = base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError):
        raise _bad("data[0].b64_json is not valid base64") from None
    if not raw.startswith(SIGNATURE):
        raise _bad(f"image is not {OUTPUT_FORMAT.upper()}")
    return raw


def _bad(detail: str) -> ServiceError:
    return ServiceError("flux", "bad_response", detail)
