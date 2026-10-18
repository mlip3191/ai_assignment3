"""Tests for jukebox/clients/base.py: retries, error mapping, the URL guard, and redacted logging.

All HTTP is mocked with respx. No real class service is ever called.
"""

from __future__ import annotations

import inspect
import io
import logging
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.base as clients_base  # noqa: E402
from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import Config, load_config  # noqa: E402
from jukebox.errors import ServiceError, recovery, user_message  # noqa: E402

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
def test_a_pasted_v1_on_the_base_url_is_not_sent_twice(
    cfg: Config, tmp_path: Path, sleeps: list[float]
) -> None:
    """The config strips a pasted trailing /v1, so a client that passes the full path (/v1/chat/completions)
    reaches /v1/chat/completions once, not /v1/v1/chat/completions."""
    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}" + ("/v1" if service == "qwen" else "")
    c = ServiceClient("qwen", load_config(env=env, env_file=tmp_path / "x"), sleep=sleeps.append)
    doubled = respx.post(f"{base()}/v1/v1/chat/completions").respond(404)
    route = respx.post(f"{base()}/v1/chat/completions").respond(200, json={})
    c.request("POST", "/v1/chat/completions")
    assert route.call_count == 1
    assert doubled.call_count == 0
    assert c.base_url == base()


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
        (404, "config"),  # a wrong path or base URL, not something the user typed
        (405, "bad_request"),
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


# ---- the key is scrubbed from every jukebox.* logger, however a client gets its logger --------


@pytest.mark.parametrize(
    "name", ["jukebox", "jukebox.clients", "jukebox.clients.flux", "jukebox.services.songs"]
)
def test_records_from_any_jukebox_logger_are_scrubbed(
    client: ServiceClient, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    with caplog.at_level(logging.DEBUG):
        logging.getLogger(name).info("sent key=%s and Authorization: Bearer %s", KEY, KEY)
    text = " ".join(r.getMessage() for r in caplog.records if r.name == name)
    assert text and KEY not in text


def test_a_handler_on_a_child_logger_never_sees_the_key(client: ServiceClient) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    log = logging.getLogger("jukebox.clients.flux")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("the key is %s", KEY)
    finally:
        log.removeHandler(handler)
        log.setLevel(logging.NOTSET)
    assert stream.getvalue().strip() and KEY not in stream.getvalue()


def test_only_jukebox_loggers_are_touched(client: ServiceClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("jukeboxer.other").info("hello %s", KEY)  # a name that merely starts with "jukebox"
        logging.getLogger("httpx").info("hello %s", KEY)
    seen = [r.getMessage() for r in caplog.records if r.name in ("jukeboxer.other", "httpx")]
    assert len(seen) == 2 and all(KEY in line for line in seen)


def test_malformed_log_arguments_neither_raise_nor_leak_the_key(client: ServiceClient) -> None:
    # "%d" with a string argument is a bad format. logging's own error report prints msg and args, so the
    # scrubber must clean those too, and must not turn a bad log call into an exception in the caller.
    factory = logging.getLogRecordFactory()
    record = factory("jukebox.clients.flux", logging.INFO, __file__, 1, "%d items", (KEY,), None)
    assert record.args in ((), None)
    assert KEY not in str(record.msg) and KEY not in record.getMessage()


def test_a_malformed_log_call_does_not_raise_or_leak_through_a_real_logger(
    client: ServiceClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("jukebox.clients.flux").info("%d items", KEY)
    text = " ".join(r.getMessage() for r in caplog.records if r.name == "jukebox.clients.flux")
    assert text and KEY not in text


class Unprintable:
    def __str__(self) -> str:
        raise RuntimeError("cannot be turned into text")

    __repr__ = __str__


@pytest.mark.parametrize("fmt", ["value: %s", "value: %d"])
def test_a_log_argument_that_cannot_be_printed_does_not_raise(client: ServiceClient, fmt: str) -> None:
    # stock logging defers formatting to the handler, which swallows the error; the scrubber must not
    # turn it into an exception inside the caller's logging call. WARNING, because INFO is off by default
    # and a disabled logger never even creates the record.
    logging.getLogger("jukebox.clients.flux").warning(fmt, Unprintable())


def test_installing_the_scrubber_twice_is_harmless() -> None:
    clients_base._install_log_redaction()
    first = logging.getLogRecordFactory()
    assert getattr(first, "_jukebox_redacting", False)
    clients_base._install_log_redaction()
    assert logging.getLogRecordFactory() is first


# ---- opting out of the retry: a timed-out job submit must never run twice ----------------------


def test_retry_defaults_to_true() -> None:
    assert inspect.signature(ServiceClient.request).parameters["retry"].default is True


@respx.mock
def test_retry_false_timeout_makes_exactly_one_call(client: ServiceClient, sleeps: list[float]) -> None:
    route = respx.post(f"{base()}/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x", retry=False)
    assert exc.value.kind == "timeout"
    assert route.call_count == 1
    assert sleeps == []  # no backoff when there is no second attempt


@pytest.mark.parametrize("status", [502, 503, 504])
@respx.mock
def test_retry_false_gateway_error_makes_exactly_one_call(client: ServiceClient, status: int) -> None:
    route = respx.post(f"{base()}/x").respond(status)
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x", retry=False)
    assert exc.value.kind == "unavailable"
    assert route.call_count == 1


@respx.mock
def test_retry_false_connection_error_makes_exactly_one_call(client: ServiceClient) -> None:
    route = respx.post(f"{base()}/x").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x", retry=False)
    assert exc.value.kind == "unavailable"
    assert route.call_count == 1


@respx.mock
def test_retry_false_success_is_unchanged(client: ServiceClient) -> None:
    route = respx.post(f"{base()}/x").respond(200, json={"ok": 1})
    assert client.request("POST", "/x", retry=False).json() == {"ok": 1}
    assert route.call_count == 1


# ---- a per-request timeout (ACE-Step: long total limit, short polls) ----------------------------


@respx.mock
def test_default_timeout_is_the_services(client: ServiceClient, cfg: Config) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", "/x")
    sent = route.calls[0].request.extensions["timeout"]
    assert sent["read"] == cfg.qwen.timeout_s
    assert sent["connect"] == clients_base.CONNECT_TIMEOUT_S


@respx.mock
def test_per_request_timeout_overrides_it_with_a_number(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", "/x", timeout=7)
    assert route.calls[0].request.extensions["timeout"] == {"connect": 7, "read": 7, "write": 7, "pool": 7}


@respx.mock
def test_per_request_timeout_accepts_an_httpx_timeout(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", "/x", timeout=httpx.Timeout(300, connect=5))
    sent = route.calls[0].request.extensions["timeout"]
    assert sent["read"] == 300 and sent["connect"] == 5


@respx.mock
def test_timeout_none_means_no_timeout_at_all(client: ServiceClient) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", "/x", timeout=None)
    sent = route.calls[0].request.extensions["timeout"]
    assert sent == {"connect": None, "read": None, "write": None, "pool": None}


@respx.mock
def test_a_per_request_timeout_does_not_stick(client: ServiceClient, cfg: Config) -> None:
    route = respx.get(f"{base()}/x").respond(200)
    client.request("GET", "/x", timeout=7)
    client.request("GET", "/x")
    assert route.calls[1].request.extensions["timeout"]["read"] == cfg.qwen.timeout_s


# ---- 404 means a wrong path or base URL: a settings problem, not something the user typed ------


@respx.mock
def test_404_user_message_points_at_the_settings_not_the_inputs(client: ServiceClient) -> None:
    respx.post(f"{base()}/x").respond(404, json={"detail": "Not Found"})
    with pytest.raises(ServiceError) as exc:
        client.request("POST", "/x")
    err = exc.value
    assert err.kind == "config"
    assert "isn't configured" in user_message(err)
    assert recovery(err) is None  # retrying or editing the prompt cannot fix it
    assert "HTTP 404" in err.detail  # developers still see the real status


# ---- the key is redacted before an error body is cut, so a half key cannot slip through -----------


LONG_KEY = "test-long-key-" + "".join(chr(97 + i % 26) for i in range(30))  # built at run time, 44 characters


@pytest.fixture
def long_key_client(tmp_path: Path, sleeps: list[float]):
    env = {"CLASS_API_KEY": LONG_KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    c = ServiceClient("qwen", load_config(env=env, env_file=tmp_path / "missing-file"), sleep=sleeps.append)
    yield c
    c.close()


def _longest_key_piece_in(text: str, key: str, shortest: int = 8) -> int:
    """Length of the longest piece of `key` (at least `shortest` characters) found in `text`, else 0."""
    for size in range(len(key), shortest - 1, -1):
        if any(key[i : i + size] in text for i in range(len(key) - size + 1)):
            return size
    return 0


@respx.mock
@pytest.mark.parametrize("offset", [0, 100, 240, 250, 262, 270, 280, 285, 290, 295, 299, 300, 310])
def test_a_key_echoed_around_the_cut_point_never_reaches_the_error(
    long_key_client: ServiceClient, offset: int
) -> None:
    """The error body is cut to MAX_DETAIL_CHARS. Cutting first would split a key that straddles the cut,
    and half a key no longer matches the redaction. A long key is used because the final cut of the detail
    hides the shorter half keys."""
    body = "x" * offset + LONG_KEY + "tail"
    respx.post(f"{base()}/x").respond(500, text=body)
    with pytest.raises(ServiceError) as err:
        long_key_client.request("POST", "/x", retry=False)
    shown = f"{err.value} {err.value.detail} {err.value!r}"
    assert _longest_key_piece_in(shown, LONG_KEY) == 0


@respx.mock
def test_a_key_echoed_in_a_4xx_body_never_reaches_detail_or_reason(long_key_client: ServiceClient) -> None:
    body = {"detail": "x" * 250 + LONG_KEY + " bad"}
    respx.post(f"{base()}/x").respond(422, json=body)
    with pytest.raises(ServiceError) as err:
        long_key_client.request("POST", "/x", retry=False)
    shown = f"{err.value.detail} {err.value.reason}"
    assert _longest_key_piece_in(shown, LONG_KEY) == 0


# ---- a file or multipart upload is sent in full again when the request is retried ---------------


@respx.mock
def test_a_file_object_upload_is_resent_in_full_on_retry(client: ServiceClient, sleeps: list[float]) -> None:
    payload = b"RIFF" + bytes(range(256)) * 20
    route = respx.post(f"{base()}/upload").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    resp = client.request(
        "POST",
        "/upload",
        files={"file": ("voice.wav", io.BytesIO(payload), "audio/wav")},
        data={"request": '{"voice": "default"}'},
    )
    assert resp.json() == {"ok": True}
    assert route.call_count == 2
    first, second = (call.request.content for call in route.calls)
    assert payload in first
    assert payload in second
    assert len(first) == len(second)
    assert sleeps  # it did back off once between the attempts
