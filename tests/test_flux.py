"""Tests for jukebox/clients/flux.py: the FLUX.2 klein 4B image client (task C2).

All HTTP is mocked with respx. No real class service is ever called. The request and reply
shapes follow docs/spikes/C1-flux.md and the FLUX row of PROJECT.md 7.1.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.clients import flux  # noqa: E402
from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import Config, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
MODEL = "black-forest-labs/FLUX.2-klein-4B"
FLUX_URL = f"http://{HOST}:{PORTS['flux']}/v1/images/generations"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 32


def _env(model: str | None = MODEL) -> dict[str, str]:
    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    if model:
        env["FLUX_MODEL"] = model
    return env


@pytest.fixture(scope="module")
def cfg(tmp_path_factory: pytest.TempPathFactory) -> Config:
    return load_config(env=_env(), env_file=tmp_path_factory.mktemp("cfg") / "missing-file")


# One shared client: building an httpx client takes about a second on Windows.
@pytest.fixture(scope="module")
def client(cfg: Config):
    c = ServiceClient("flux", cfg, sleep=lambda _s: None)
    yield c
    c.close()


def _reply(raw: bytes = PNG, **extra: object) -> dict:
    return {
        "created": 1,
        "data": [{"b64_json": base64.b64encode(raw).decode("ascii"), "url": None, "revised_prompt": None}],
        "output_format": "png",
        **extra,
    }


def _sent(route: respx.Route) -> dict:
    return json.loads(route.calls[0].request.content)


# ---- success and request format ---------------------------------------------------------------


@respx.mock
def test_success_returns_the_decoded_png_bytes(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(200, json=_reply())
    assert flux.generate_image("a calm lake", client=client) == PNG


@respx.mock
def test_sends_the_documented_fields(client: ServiceClient) -> None:
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    flux.generate_image("a calm lake", width=768, height=512, seed=42, client=client)
    assert _sent(route) == {
        "prompt": "a calm lake",
        "model": MODEL,
        "n": 1,
        "size": "768x512",
        "seed": 42,
        "response_format": "b64_json",
        "output_format": "png",
        "output_compression": 1,
    }
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {KEY}"


@respx.mock
def test_defaults_to_a_square_1024_cover_without_a_seed(client: ServiceClient) -> None:
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    flux.generate_image("a calm lake", client=client)
    body = _sent(route)
    assert body["size"] == "1024x1024"
    assert "seed" not in body


@respx.mock
def test_model_field_is_left_out_when_flux_model_is_not_set(tmp_path: Path) -> None:
    cfg = load_config(env=_env(model=None), env_file=tmp_path / "missing-file")
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    with ServiceClient("flux", cfg, sleep=lambda _s: None) as c:
        flux.generate_image("a calm lake", client=c)
    assert "model" not in _sent(route)


@respx.mock
def test_builds_its_own_flux_client_from_config(cfg: Config) -> None:
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    assert flux.generate_image("a calm lake", config=cfg) == PNG
    assert route.call_count == 1


# ---- only FLUX on port 9006 -------------------------------------------------------------------


def test_refuses_a_client_for_another_service(cfg: Config) -> None:
    with ServiceClient("qwen", cfg, sleep=lambda _s: None) as qwen_client:
        with pytest.raises(ValueError):
            flux.generate_image("a calm lake", client=qwen_client)


@respx.mock
def test_talks_only_to_the_flux_url(client: ServiceClient) -> None:
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    flux.generate_image("a calm lake", client=client)
    assert route.call_count == 1
    assert len(respx.calls) == 1
    assert respx.calls[0].request.url.port == 9006


# ---- input checks -----------------------------------------------------------------------------


@pytest.mark.parametrize("prompt", ["", "   "])
def test_empty_prompt_is_a_programming_error(client: ServiceClient, prompt: str) -> None:
    with pytest.raises(ValueError):
        flux.generate_image(prompt, client=client)


@pytest.mark.parametrize(("width", "height"), [(0, 1024), (1024, -1)])
def test_non_positive_size_is_a_programming_error(client: ServiceClient, width: int, height: int) -> None:
    with pytest.raises(ValueError):
        flux.generate_image("a calm lake", width=width, height=height, client=client)


# ---- each error kind --------------------------------------------------------------------------


@respx.mock
def test_timeout_becomes_a_flux_timeout_error(client: ServiceClient) -> None:
    respx.post(FLUX_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert (exc.value.service, exc.value.kind) == ("flux", "timeout")


@respx.mock
def test_401_becomes_an_auth_error(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(401, json={"error": "Unauthorized"})
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert (exc.value.service, exc.value.kind) == ("flux", "auth")


@respx.mock
def test_503_is_retried_once_then_unavailable(client: ServiceClient) -> None:
    route = respx.post(FLUX_URL).respond(503)
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "unavailable"
    assert route.call_count == 2


@respx.mock
def test_400_becomes_bad_request_with_the_server_reason(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(400, json={"detail": "size must be WIDTHxHEIGHT"})
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "bad_request"
    assert exc.value.reason == "size must be WIDTHxHEIGHT"


@respx.mock
def test_404_becomes_a_config_error(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(404, json={"detail": "Not Found"})
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert (exc.value.service, exc.value.kind) == ("flux", "config")


@respx.mock
def test_a_pasted_v1_base_url_still_calls_the_documented_path(tmp_path: Path) -> None:
    env = _env()
    env["FLUX_BASE_URL"] = f"http://{HOST}:{PORTS['flux']}/v1"
    cfg = load_config(env=env, env_file=tmp_path / "missing-file")
    route = respx.post(FLUX_URL).respond(200, json=_reply())
    assert flux.generate_image("a calm lake", config=cfg) == PNG
    assert route.call_count == 1


@respx.mock
def test_500_becomes_bad_response(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(500)
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "bad_response"


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        {"created": 1},
        {"data": []},
        {"data": [{"url": None}]},
        {"data": [{"b64_json": None}]},
        {"data": [{"b64_json": "%%% not base64 %%%"}]},
        {"data": "nope"},
        ["a list"],
    ],
)
def test_malformed_reply_becomes_bad_response(client: ServiceClient, body: object) -> None:
    with respx.mock:
        if isinstance(body, str):
            respx.post(FLUX_URL).respond(200, text=body)
        else:
            respx.post(FLUX_URL).respond(200, json=body)
        with pytest.raises(ServiceError) as exc:
            flux.generate_image("a calm lake", client=client)
    assert (exc.value.service, exc.value.kind) == ("flux", "bad_response")


@respx.mock
def test_bytes_that_are_not_a_png_become_bad_response(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(200, json=_reply(raw=b"\xff\xd8\xff\xe0 a jpeg"))
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "bad_response"


# ---- logging ----------------------------------------------------------------------------------


@respx.mock
def test_key_and_image_data_never_reach_the_logs(
    client: ServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(FLUX_URL).respond(200, json=_reply())
    with caplog.at_level(logging.DEBUG):
        flux.generate_image("a calm lake", client=client)
    text = caplog.text
    assert KEY not in text
    assert base64.b64encode(PNG).decode("ascii") not in text
    assert "flux -> class.example:9006 200" in text
