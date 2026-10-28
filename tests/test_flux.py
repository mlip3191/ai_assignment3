"""Tests for jukebox/clients/flux.py: the FLUX.2 klein 4B image client (task C2).

Covers are JPEG (release lead's decision on #4, 10/20). All HTTP is mocked with respx; no real
class service is ever called. The request and reply shapes follow docs/spikes/C1-flux.md and the
FLUX row of PROJECT.md 7.1.
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
from jukebox.config import Config, ConfigError, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
MODEL = "black-forest-labs/FLUX.2-klein-4B"
FLUX_URL = f"http://{HOST}:{PORTS['flux']}/v1/images/generations"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 32  # the wrong format now


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


def _reply(raw: bytes = JPEG, **extra: object) -> dict:
    return {
        "created": 1,
        "data": [{"b64_json": base64.b64encode(raw).decode("ascii"), "url": None, "revised_prompt": None}],
        "output_format": "jpeg",
        **extra,
    }


def _sent(route: respx.Route) -> dict:
    return json.loads(route.calls[0].request.content)


# ---- success and request format ---------------------------------------------------------------


@respx.mock
def test_success_returns_the_decoded_jpeg_bytes(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(200, json=_reply())
    assert flux.generate_image("a calm lake", client=client) == JPEG


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
        "output_format": "jpeg",
        "output_compression": 90,
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
    assert flux.generate_image("a calm lake", config=cfg) == JPEG
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
    assert flux.generate_image("a calm lake", config=cfg) == JPEG
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
def test_bytes_that_are_not_a_jpeg_become_bad_response(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(200, json=_reply(raw=PNG))
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
    assert base64.b64encode(JPEG).decode("ascii") not in text
    assert "flux -> class.example:9006 200" in text


@respx.mock
def test_base64_split_across_lines_is_still_decoded(client: ServiceClient) -> None:
    encoded = base64.b64encode(JPEG).decode("ascii")
    wrapped = "\n".join(encoded[i : i + 20] for i in range(0, len(encoded), 20)) + "\r\n"
    respx.post(FLUX_URL).respond(200, json={"data": [{"b64_json": wrapped}]})
    assert flux.generate_image("a calm lake", client=client) == JPEG


@pytest.mark.parametrize("junk", ["\t", "\u00a0", " "])
def test_other_whitespace_inside_the_base64_is_still_rejected(client: ServiceClient, junk: str) -> None:
    encoded = base64.b64encode(JPEG).decode("ascii")
    broken = encoded[:10] + junk + encoded[10:]
    with respx.mock:
        respx.post(FLUX_URL).respond(200, json={"data": [{"b64_json": broken}]})
        with pytest.raises(ServiceError) as exc:
            flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "bad_response"


@respx.mock
def test_a_reply_of_only_line_breaks_is_bad_response(client: ServiceClient) -> None:
    respx.post(FLUX_URL).respond(200, json={"data": [{"b64_json": "\r\n\n"}]})
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake", client=client)
    assert exc.value.kind == "bad_response"


# ---- the shared default client ----------------------------------------------------------------


@pytest.fixture
def fresh_default(monkeypatch: pytest.MonkeyPatch):
    """Start each of these tests with no shared client, and restore whatever was there."""
    monkeypatch.setattr(flux, "_default", None)
    yield


def test_missing_settings_become_a_flux_config_error(fresh_default, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_settings() -> ServiceClient:
        raise ConfigError(["FLUX_BASE_URL: (missing)"])

    monkeypatch.setattr(flux, "_make_default_client", broken_settings)
    with pytest.raises(ServiceError) as exc:
        flux.generate_image("a calm lake")
    assert (exc.value.service, exc.value.kind) == ("flux", "config")
    assert "FLUX_BASE_URL" in exc.value.detail


def test_a_settings_problem_is_not_cached_so_a_fix_and_retry_works(
    fresh_default, monkeypatch: pytest.MonkeyPatch, cfg: Config
) -> None:
    attempts = {"n": 0}

    def settings_fixed_on_second_try() -> ServiceClient:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConfigError(["FLUX_BASE_URL: (missing)"])
        return ServiceClient("flux", cfg, sleep=lambda _s: None)

    monkeypatch.setattr(flux, "_make_default_client", settings_fixed_on_second_try)
    with pytest.raises(ServiceError):
        flux.generate_image("a calm lake")
    with respx.mock:
        respx.post(FLUX_URL).respond(200, json=_reply())
        assert flux.generate_image("a calm lake") == JPEG


def test_the_shared_client_is_built_once_and_reused(
    fresh_default, monkeypatch: pytest.MonkeyPatch, cfg: Config
) -> None:
    built = {"n": 0}

    def make() -> ServiceClient:
        built["n"] += 1
        return ServiceClient("flux", cfg, sleep=lambda _s: None)

    monkeypatch.setattr(flux, "_make_default_client", make)
    with respx.mock:
        route = respx.post(FLUX_URL).respond(200, json=_reply())
        flux.generate_image("a calm lake")
        flux.generate_image("a quiet forest")
    assert built["n"] == 1
    assert route.call_count == 2


# ---- a failed call drops the shared client, so Retry cover reads the fixed settings (#74, TC-F5) ----

DEAD_HOST = "127.0.0.1"
DEAD_URL = f"http://{DEAD_HOST}:9006/v1/images/generations"


def _settings_file(path: Path, flux_host: str) -> None:
    """A settings file like the user's, with FLUX at `flux_host` and the other services on HOST."""
    env = _env()
    env["FLUX_BASE_URL"] = f"http://{flux_host}:{PORTS['flux']}"
    path.write_bytes("".join(f"{k}={v}\n" for k, v in env.items()).encode("utf-8"))


def test_retry_after_fixing_the_flux_address_uses_the_new_address_without_a_restart(
    fresh_default, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TC-F5: a dead FLUX address fails, the user fixes the settings file, and the next call works."""
    from jukebox import config

    settings = tmp_path / "settings"
    _settings_file(settings, DEAD_HOST)
    monkeypatch.setattr(config, "DEFAULT_ENV_FILE", settings)
    for var in config.KNOWN_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(flux, "_make_default_client", lambda: ServiceClient("flux", sleep=lambda _s: None))
    with respx.mock:
        dead = respx.post(DEAD_URL).mock(side_effect=httpx.ConnectError("nothing listening"))
        good = respx.post(FLUX_URL).respond(200, json=_reply())
        with pytest.raises(ServiceError) as exc:
            flux.generate_image("a calm lake")
        assert (exc.value.service, exc.value.kind) == ("flux", "unavailable")

        _settings_file(settings, HOST)  # fixed by hand; the app is not restarted
        assert flux.generate_image("a calm lake") == JPEG
    assert dead.call_count == 2  # one try and one retry, then the client was dropped
    assert good.call_count == 1


@pytest.mark.parametrize("status", [401, 404, 500])
def test_any_failed_call_drops_the_shared_client(
    fresh_default, monkeypatch: pytest.MonkeyPatch, cfg: Config, status: int
) -> None:
    """A wrong key (401) or path (404) is also a settings problem, so every failure starts afresh."""
    built = {"n": 0}

    def make() -> ServiceClient:
        built["n"] += 1
        return ServiceClient("flux", cfg, sleep=lambda _s: None)

    monkeypatch.setattr(flux, "_make_default_client", make)
    with respx.mock:
        respx.post(FLUX_URL).mock(side_effect=[httpx.Response(status), httpx.Response(200, json=_reply())])
        with pytest.raises(ServiceError):
            flux.generate_image("a calm lake")
        assert flux.generate_image("a calm lake") == JPEG
    assert built["n"] == 2


def test_a_failure_on_an_old_client_keeps_the_newer_one(fresh_default, cfg: Config) -> None:
    """Two covers can fail at once: the second failure must not drop the client the first one rebuilt."""
    old = ServiceClient("flux", cfg, sleep=lambda _s: None)
    newer = ServiceClient("flux", cfg, sleep=lambda _s: None)
    try:
        flux._default = newer
        flux._forget(old)
        assert flux._default is newer
        flux._forget(newer)
        assert flux._default is None
    finally:
        old.close()
        newer.close()


def test_a_bad_prompt_does_not_drop_the_shared_client(
    fresh_default, monkeypatch: pytest.MonkeyPatch, cfg: Config
) -> None:
    """A programming error (empty prompt) never reaches the server, so the client stays."""
    built = {"n": 0}

    def make() -> ServiceClient:
        built["n"] += 1
        return ServiceClient("flux", cfg, sleep=lambda _s: None)

    monkeypatch.setattr(flux, "_make_default_client", make)
    with respx.mock:
        respx.post(FLUX_URL).respond(200, json=_reply())
        flux.generate_image("a calm lake")
        with pytest.raises(ValueError):
            flux.generate_image("   ")
        flux.generate_image("a quiet forest")
    assert built["n"] == 1
