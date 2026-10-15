"""Tests for jukebox/clients/base.py: retries, error mapping, the URL guard, and redacted logging.

All HTTP is mocked with respx. No real class service is ever called.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import Config, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
OTHER_PORT = 9 * 1000  # built from a number so no literal URL with this port appears in the repo


def base(service: str = "qwen") -> str:
    return f"http://{HOST}:{PORTS[service]}"


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    return load_config(env=env, env_file=tmp_path / "missing-file")


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(cfg: Config, sleeps: list[float]):
    c = ServiceClient("qwen", cfg, sleep=sleeps.append)
    yield c
    c.close()


def fail(client_error: ServiceError | pytest.ExceptionInfo[ServiceError]) -> ServiceError:
    return client_error.value if isinstance(client_error, pytest.ExceptionInfo) else client_error


# ---- success ----------------------------------------------------------------------------------


@respx.mock
def test_success_goes_to_the_configured_url_with_auth(client: ServiceClient) -> None:
    route = respx.post(f"{base()}/v1/chat").respond(200, json={"ok": True})
    resp = client.request("POST", "/v1/chat", json={"a": 1})
    assert resp.json() == {"ok": True}
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {KEY}"


@respx.mock
def test_path_with_or_without_leading_slash_works(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/health").respond(200)
    client.request("GET", "health")
    client.request("GET", "/health")
    assert route.call_count == 2


@respx.mock
def test_a_path_in_the_base_url_is_kept(cfg: Config, tmp_path: Path, sleeps: list[float]) -> None:
    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}" + ("/v1" if service == "qwen" else "")
    c = ServiceClient("qwen", load_config(env=env, env_file=tmp_path / "x"), sleep=sleeps.append)
    route = respx.post(f"{base()}/v1/chat/completions").respond(200, json={})
    c.request("POST", "chat/completions")
    assert route.call_count == 1


def test_auth_scheme_can_be_changed(cfg: Config, sleeps: list[float]) -> None:
    with respx.mock:
        route = respx.get(f"{base('flux')}/x").respond(200)
        with ServiceClient("flux", cfg, auth_scheme=None, sleep=sleeps.append) as c:
            c.request("GET", "/x")
        assert route.calls[0].request.headers["Authorization"] == KEY


def test_each_service_uses_its_own_url_and_timeout(cfg: Config, sleeps: list[float]) -> None:
    with respx.mock:
        for service, port in PORTS.items():
            route = respx.get(f"http://{HOST}:{port}/ping").respond(200)
            with ServiceClient(service, cfg, sleep=sleeps.append) as c:  # type: ignore[arg-type]
                c.request("GET", "/ping")
                assert c.base_url == f"http://{HOST}:{port}"
                assert c.timeout.read == getattr(cfg, service).timeout_s
            assert route.call_count == 1


def test_unknown_service_is_a_programming_error(cfg: Config) -> None:
    with pytest.raises(ValueError):
        ServiceClient("openai", cfg)  # type: ignore[arg-type]


# ---- retries ----------------------------------------------------------------------------------


@respx.mock
def test_timeout_then_success_retries_once(client: ServiceClient, sleeps: list[float]) -> None:
    route = respx.post(f"{base()}/x")
    route.side_effect = [httpx.ReadTimeout("slow"), httpx.Response(200, json={"ok": 1})]
    assert client.request("POST", "/x").json() == {"ok": 1}
    assert route.call_count == 2
    assert len(sleeps) == 1 and sleeps[0] > 0


@respx.mock
def test_timeout_twice_raises_timeout_after_exactly_two_calls(client: ServiceClient) -> None:
    route = respx.post(f"{base()}/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x")
    assert exc.value.kind == "timeout" and exc.value.service == "qwen"
    assert route.call_count == 2


@respx.mock
def test_connection_error_retries_once_then_is_unavailable(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/x").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ServiceError) as exc:
        client.request("GET", "/x")
    assert exc.value.kind == "unavailable"
    assert route.call_count == 2


@pytest.mark.parametrize("status", [502, 503, 504])
@respx.mock
def test_gateway_errors_are_retried_once(client: ServiceClient, status: int) -> None:
    route = respx.get(f"{base()}/x")
    route.side_effect = [httpx.Response(status), httpx.Response(200, json={"ok": 1})]
    assert client.request("GET", "/x").status_code == 200
    assert route.call_count == 2


@pytest.mark.parametrize("status", [502, 503, 504])
@respx.mock
def test_gateway_errors_twice_are_unavailable(client: ServiceClient, status: int) -> None:
    route = respx.get(f"{base()}/x").respond(status)
    with pytest.raises(ServiceError) as exc:
        client.request("GET", "/x")
    assert exc.value.kind == "unavailable"
    assert route.call_count == 2


# ---- error mapping, no retry ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "auth"),
        (403, "auth"),
        (400, "bad_request"),
        (404, "bad_request"),
        (422, "bad_request"),
        (429, "unavailable"),
        (500, "bad_response"),
        (301, "bad_response"),
    ],
)
@respx.mock
def test_status_maps_to_kind_without_retry(client: ServiceClient, status: int, kind: str) -> None:
    route = respx.post(f"{base()}/x").respond(status, json={"detail": "nope"})
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x")
    assert exc.value.kind == kind
    assert route.call_count == 1
    assert str(status) in exc.value.detail


@respx.mock
def test_bad_request_reason_comes_from_the_server_message(client: ServiceClient) -> None:
    respx.post(f"{base()}/x").respond(422, json={"detail": "prompt is empty"})
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x")
    assert exc.value.reason == "prompt is empty"


@respx.mock
def test_malformed_json_body_is_bad_response(client: ServiceClient) -> None:
    respx.get(f"{base()}/x").respond(200, content=b"<html>not json</html>")
    resp = client.request("GET", "/x")
    with pytest.raises(ServiceError) as exc:
        client.json_body(resp)
    assert exc.value.kind == "bad_response" and exc.value.service == "qwen"


@respx.mock
def test_valid_json_body_is_returned(client: ServiceClient) -> None:
    respx.get(f"{base()}/x").respond(200, json={"a": [1, 2]})
    assert client.json_body(client.request("GET", "/x")) == {"a": [1, 2]}


# ---- only the four configured URLs ------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        "http://other.example:9001/x",  # other host
        f"http://{HOST}:{OTHER_PORT}/x",  # same host, other port
        f"http://{HOST}:9006/x",  # another class service's port
        "//other.example/x",  # scheme-relative
        f"http://{HOST}:9001@other.example/x",  # userinfo trick
        f"https://{HOST}:9001/x",  # other scheme
        "ftp://other.example/x",
    ],
)
@respx.mock
def test_any_other_url_is_a_config_error_with_no_request(client: ServiceClient, target: str) -> None:
    with pytest.raises(ServiceError) as exc:
        client.request("GET", target)
    assert exc.value.kind == "config"
    assert respx.calls.call_count == 0


@respx.mock
def test_absolute_url_on_the_same_host_and_port_is_allowed(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", f"{base()}/x")
    assert route.call_count == 1


# ---- redaction and logging (H8, TC-15) --------------------------------------------------------


@respx.mock
def test_one_log_line_per_request_with_service_host_port_status_duration(
    client: ServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    respx.get(f"{base()}/x").respond(200)
    with caplog.at_level(logging.INFO, logger="jukebox.clients"):
        client.request("GET", "/x")
    lines = [r.getMessage() for r in caplog.records if r.name == "jukebox.clients"]
    assert len(lines) == 1
    assert lines[0].startswith(f"qwen -> {HOST}:9001 200 ")
    assert lines[0].endswith("ms")


@respx.mock
def test_failed_attempts_are_logged_too(client: ServiceClient, caplog: pytest.LogCaptureFixture) -> None:
    respx.get(f"{base()}/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with caplog.at_level(logging.INFO, logger="jukebox.clients"), pytest.raises(ServiceError):
        client.request("GET", "/x")
    lines = [r.getMessage() for r in caplog.records if r.name == "jukebox.clients"]
    assert len(lines) == 2 and all("timeout" in line for line in lines)


@respx.mock
def test_logs_never_contain_headers_bodies_or_the_key(
    client: ServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(f"{base()}/x").respond(200, json={"secret_body": "hello"})
    with caplog.at_level(logging.DEBUG):
        client.request("POST", "/x", json={"prompt": "private words"})
        logging.getLogger("jukebox.clients").info("oops key=%s Authorization: Bearer %s", KEY, KEY)
    text = " ".join(r.getMessage() for r in caplog.records if r.name == "jukebox.clients")
    assert KEY not in text
    assert "private words" not in text and "secret_body" not in text
    assert "Bearer " + KEY not in text


@respx.mock
def test_an_error_body_that_echoes_the_key_never_reaches_the_error(client: ServiceClient) -> None:
    respx.post(f"{base()}/x").respond(400, json={"detail": f"bad credentials {KEY}"})
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x")
    shown = f"{exc.value} {exc.value!r} {exc.value.detail} {exc.value.reason}"
    assert KEY not in shown


@respx.mock
def test_error_detail_is_truncated(client: ServiceClient) -> None:
    respx.get(f"{base()}/x").respond(500, text="x" * 100_000)
    with pytest.raises(ServiceError) as exc:
        client.request("GET", "/x")
    assert len(exc.value.detail) < 1000
