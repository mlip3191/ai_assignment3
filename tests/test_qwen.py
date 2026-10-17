"""Tests for jukebox/clients/qwen.py: the Qwen chat client (task B3).

All HTTP is mocked with respx. No real class service is ever called. Request and reply shapes
follow the B1 spike (docs/spikes/B1-qwen.md) and PROJECT.md 7.1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.qwen as qwen  # noqa: E402
from jukebox.clients.qwen import QwenClient  # noqa: E402
from jukebox.config import Config, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
MODEL = "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit"
URL = f"http://{HOST}:9001/v1/chat/completions"
MESSAGES = [{"role": "user", "content": "Write a two-line poem about rain."}]


def make_config(tmp_path: Path, *, model: str | None = MODEL) -> Config:
    env = {"CLASS_API_KEY": KEY}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    if model:
        env["QWEN_MODEL"] = model
    return load_config(env=env, env_file=tmp_path / "missing-file")


@pytest.fixture
def client(tmp_path: Path):
    c = QwenClient(make_config(tmp_path), sleep=lambda _s: None)
    yield c
    c.close()


def reply(content: str | None, *, finish_reason: str = "stop", reasoning: str | None = None) -> dict:
    """An OpenAI-style chat completion body, shaped like the class server's (B1)."""
    message: dict = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return {
        "model": MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 15},
    }


def sent_body(route: respx.Route) -> dict:
    return json.loads(route.calls[0].request.content)


# ---- request shape ----------------------------------------------------------------------------


@respx.mock
def test_chat_posts_to_chat_completions_with_thinking_off(client: QwenClient) -> None:
    route = respx.post(URL).respond(200, json=reply("Silver rain."))
    client.chat(MESSAGES, max_tokens=300, temperature=0.5)
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {KEY}"
    body = sent_body(route)
    assert body["model"] == MODEL
    assert body["messages"] == MESSAGES
    assert body["max_tokens"] == 300
    assert body["temperature"] == 0.5
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "response_format" not in body


@respx.mock
def test_chat_uses_the_documented_defaults(client: QwenClient) -> None:
    route = respx.post(URL).respond(200, json=reply("ok"))
    client.chat(MESSAGES)
    body = sent_body(route)
    assert body["max_tokens"] == 600
    assert body["temperature"] == 0.8


@respx.mock
def test_chat_omits_model_when_not_configured(tmp_path: Path) -> None:
    route = respx.post(URL).respond(200, json=reply("ok"))
    with QwenClient(make_config(tmp_path, model=None)) as c:
        c.chat(MESSAGES)
    assert "model" not in sent_body(route)


# ---- reply text -------------------------------------------------------------------------------


@respx.mock
def test_chat_returns_content_and_ignores_reasoning_field(client: QwenClient) -> None:
    respx.post(URL).respond(
        200, json=reply("\n\nThe sky weeps silver tears.\n", reasoning="Thinking Process: ...")
    )
    assert client.chat(MESSAGES) == "The sky weeps silver tears."


@respx.mock
def test_chat_strips_think_block(client: QwenClient) -> None:
    respx.post(URL).respond(200, json=reply("<think>plan the poem</think>\nRain on the roof."))
    assert client.chat(MESSAGES) == "Rain on the roof."


@respx.mock
def test_chat_strips_orphan_closing_think_tag(client: QwenClient) -> None:
    respx.post(URL).respond(200, json=reply("first I will rhyme rain with pane</think>Rain on the pane."))
    assert client.chat(MESSAGES) == "Rain on the pane."


# ---- bad replies become bad_response ----------------------------------------------------------


@pytest.mark.parametrize("content", [None, "", "   \n", "<think>only thinking</think>"])
@respx.mock
def test_chat_null_or_empty_content_is_bad_response(client: QwenClient, content: str | None) -> None:
    respx.post(URL).respond(200, json=reply(content))
    with pytest.raises(ServiceError) as e:
        client.chat(MESSAGES)
    assert e.value.service == "qwen"
    assert e.value.kind == "bad_response"


@respx.mock
def test_chat_truncated_reply_is_bad_response(client: QwenClient) -> None:
    respx.post(URL).respond(200, json=reply('{"title": "Sunset", "lyr', finish_reason="length"))
    with pytest.raises(ServiceError) as e:
        client.chat(MESSAGES)
    assert e.value.kind == "bad_response"
    assert "max_tokens" in e.value.detail


@pytest.mark.parametrize(
    "body", [{}, {"choices": []}, {"choices": [{}]}, {"choices": "nope"}, ["not", "a", "dict"]]
)
@respx.mock
def test_chat_missing_choices_is_bad_response(client: QwenClient, body: object) -> None:
    respx.post(URL).respond(200, json=body)
    with pytest.raises(ServiceError) as e:
        client.chat(MESSAGES)
    assert e.value.kind == "bad_response"


@respx.mock
def test_chat_non_json_body_is_bad_response(client: QwenClient) -> None:
    respx.post(URL).respond(200, text="<html>gateway hiccup</html>")
    with pytest.raises(ServiceError) as e:
        client.chat(MESSAGES)
    assert e.value.kind == "bad_response"


# ---- HTTP failures map to the 7.3 kinds (through the shared base client) -------------------------


@pytest.mark.parametrize(
    ("response", "kind", "calls"),
    [
        (httpx.Response(401, json={"error": "Unauthorized"}), "auth", 1),
        (httpx.Response(400, json={"detail": "bad messages"}), "bad_request", 1),
        (httpx.Response(404), "config", 1),
        (httpx.Response(500), "bad_response", 1),
        (httpx.Response(503), "unavailable", 2),
        (httpx.TimeoutException("slow"), "timeout", 2),
        (httpx.ConnectError("down"), "unavailable", 2),
    ],
)
@respx.mock
def test_chat_http_errors_map_to_kinds(client: QwenClient, response: object, kind: str, calls: int) -> None:
    route = respx.post(URL)
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    with pytest.raises(ServiceError) as e:
        client.chat(MESSAGES)
    assert e.value.service == "qwen"
    assert e.value.kind == kind
    assert route.call_count == calls  # one retry on timeout, connection errors, and 502/503/504 only


def test_chat_never_leaks_the_key_in_errors(client: QwenClient) -> None:
    with respx.mock:
        respx.post(URL).respond(400, json={"detail": f"bad key {KEY}"})
        with pytest.raises(ServiceError) as e:
            client.chat(MESSAGES)
    assert KEY not in str(e.value)
    assert KEY not in (e.value.reason or "")


# ---- JSON helper ------------------------------------------------------------------------------

SONG_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "lyrics": {"type": "string"}},
    "required": ["title", "lyrics"],
}


@respx.mock
def test_chat_json_sends_schema_as_response_format(client: QwenClient) -> None:
    route = respx.post(URL).respond(200, json=reply('{"title": "A", "lyrics": "B"}'))
    client.chat_json(MESSAGES, schema=SONG_SCHEMA, schema_name="song")
    body = sent_body(route)
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "song", "schema": SONG_SCHEMA},
    }
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


@respx.mock
def test_chat_json_without_schema_sends_no_response_format(client: QwenClient) -> None:
    route = respx.post(URL).respond(200, json=reply('{"title": "A"}'))
    assert client.chat_json(MESSAGES) == {"title": "A"}
    assert "response_format" not in sent_body(route)


@respx.mock
def test_chat_json_parses_clean_json(client: QwenClient) -> None:
    respx.post(URL).respond(200, json=reply('{"title": "Neon Horizon", "lyrics": "[verse]\\nWindows down"}'))
    assert client.chat_json(MESSAGES, schema=SONG_SCHEMA) == {
        "title": "Neon Horizon",
        "lyrics": "[verse]\nWindows down",
    }


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"title": "Neon Horizon", "lyrics": "la"}\n```',
        'Here is your song:\n{"title": "Neon Horizon", "lyrics": "la"}\nEnjoy!',
        '<think>hmm</think>{"title": "Neon Horizon", "lyrics": "la"}',
    ],
)
@respx.mock
def test_chat_json_falls_back_on_fenced_or_wrapped_json(client: QwenClient, content: str) -> None:
    respx.post(URL).respond(200, json=reply(content))
    assert client.chat_json(MESSAGES) == {"title": "Neon Horizon", "lyrics": "la"}


@pytest.mark.parametrize("content", ["Title: Neon Horizon\nLyrics: la la", '{"title": "Neon', "[1, 2, 3]"])
@respx.mock
def test_chat_json_malformed_raises_bad_response(client: QwenClient, content: str) -> None:
    respx.post(URL).respond(200, json=reply(content))
    with pytest.raises(ServiceError) as e:
        client.chat_json(MESSAGES)
    assert e.value.kind == "bad_response"
    assert e.value.service == "qwen"


def test_parse_json_reply_is_usable_on_its_own() -> None:
    assert qwen.parse_json_reply('noise {"a": {"b": 1}} more noise') == {"a": {"b": 1}}
    with pytest.raises(ServiceError):
        qwen.parse_json_reply("no json here")


# ---- module-level chat() (PROJECT.md 7.2 signature) -------------------------------------------


def test_module_chat_uses_lazy_default_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Config | None] = []
    cfg = make_config(tmp_path)

    def fake_client() -> QwenClient:
        built.append(cfg)
        return QwenClient(cfg)

    monkeypatch.setattr(qwen, "_default", None)
    monkeypatch.setattr(qwen, "_make_default_client", fake_client)
    with respx.mock:
        respx.post(URL).respond(200, json=reply("one"))
        assert qwen.chat(MESSAGES) == "one"
        assert qwen.chat(MESSAGES, max_tokens=50, temperature=0.1) == "one"
    assert len(built) == 1  # created once, on first use, then reused


def test_module_chat_json_uses_the_same_default_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = make_config(tmp_path)
    monkeypatch.setattr(qwen, "_default", QwenClient(cfg))
    with respx.mock:
        respx.post(URL).respond(200, json=reply('{"ok": true}'))
        assert qwen.chat_json(MESSAGES) == {"ok": True}


def test_client_is_bound_to_qwen_only(client: QwenClient) -> None:
    assert client.service == "qwen"
    assert client.base_url == f"http://{HOST}:9001"
