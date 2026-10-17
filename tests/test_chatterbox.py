"""Tests for jukebox/clients/chatterbox.py: speak() against the D1 request format.

All HTTP is mocked with respx. No real class service is ever called, and no real voice recording is
used: reference "recordings" are a few bytes written to pytest's tmp_path.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.chatterbox as chatterbox  # noqa: E402
from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import Config, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
SPEECH_URL = f"http://{HOST}:9008/v1/audio/speech"
VOICES_URL = f"http://{HOST}:9008/v1/voices"
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
TEXT = "You're locked in to the AI Jukebox. Next up is Midnight Lanterns, a mellow acoustic track."


def make_config(tmp_path: Path, **extra: str) -> Config:
    env = {"CLASS_API_KEY": KEY, **extra}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    return load_config(env=env, env_file=tmp_path / "missing-file")


@pytest.fixture
def use_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point speak() at a test config. Call it again with extra env vars to change the config."""

    def apply(**extra: str) -> Config:
        cfg = make_config(tmp_path, **extra)
        monkeypatch.setattr(
            chatterbox, "_new_client", lambda: ServiceClient("chatterbox", cfg, sleep=lambda s: None)
        )
        return cfg

    apply()
    return apply


@pytest.fixture
def ref_file(tmp_path: Path):
    def write(name: str, data: bytes = b"RIFF\x24\x00\x00\x00WAVEfmt fake reference") -> Path:
        path = tmp_path / name
        path.write_bytes(data)
        return path

    return write


def sent_json(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


# ---- default voice (F3a) -----------------------------------------------------------------------


@respx.mock
def test_default_voice_sends_the_documented_request(use_config) -> None:
    route = respx.post(SPEECH_URL).mock(
        return_value=httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})
    )

    audio, ext = chatterbox.speak(TEXT)

    assert (audio, ext) == (MP3, "mp3")
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert sent_json(route) == {
        "model": "chatterbox-v3",
        "input": TEXT,
        "voice": "default",
        "language_id": "en",
        "response_format": "mp3",
    }


@respx.mock
def test_text_is_trimmed_before_sending(use_config) -> None:
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
    chatterbox.speak(f"  {TEXT}\n")
    assert sent_json(route)["input"] == TEXT


@respx.mock
def test_configured_model_name_is_sent(use_config) -> None:
    use_config(CHATTERBOX_MODEL="chatterbox-v3-custom")
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
    chatterbox.speak(TEXT)
    assert sent_json(route)["model"] == "chatterbox-v3-custom"


@respx.mock
def test_language_is_passed_through(use_config) -> None:
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
    chatterbox.speak("Hola a todos.", language="es")
    assert sent_json(route)["language_id"] == "es"


@respx.mock
def test_an_mp3_frame_header_without_id3_is_accepted(use_config) -> None:
    frame = b"\xff\xfb\x90\x64" + b"\x00" * 100
    respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=frame))
    assert chatterbox.speak(TEXT) == (frame, "mp3")


# ---- custom voice reference (F3b) -------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("name", ["voice.wav", "voice.mp3", "VOICE.WAV", "Voice.Mp3"])
def test_reference_recording_is_sent_as_base64(use_config, ref_file, name: str) -> None:
    data = b"reference-bytes-for-" + name.encode()
    path = ref_file(name, data)
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))

    assert chatterbox.speak(TEXT, voice_ref_path=str(path)) == (MP3, "mp3")

    body = sent_json(route)
    assert body["voice"] == "default"
    assert base64.b64decode(body["ref_audio"]) == data
    assert route.call_count == 1


@respx.mock
def test_reference_path_can_be_a_path_object(use_config, ref_file) -> None:
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
    chatterbox.speak(TEXT, voice_ref_path=ref_file("voice.wav"))  # type: ignore[arg-type]
    assert "ref_audio" in sent_json(route)


# ---- local validation: rejected before any request ---------------------------------------------


@respx.mock
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_text_is_rejected_without_a_request(use_config, text: str) -> None:
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(text)
    assert (err.value.service, err.value.kind) == ("chatterbox", "bad_request")
    assert "empty" in (err.value.reason or "")
    assert route.call_count == 0


@respx.mock
def test_text_over_the_limit_is_rejected_without_a_request(use_config) -> None:
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak("a" * (chatterbox.MAX_INPUT_CHARS + 1))
    assert err.value.kind == "bad_request"
    assert "4096" in (err.value.reason or "")
    assert route.call_count == 0


@respx.mock
def test_text_at_the_limit_is_sent(use_config) -> None:
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
    chatterbox.speak("a" * chatterbox.MAX_INPUT_CHARS)
    assert route.call_count == 1


@respx.mock
def test_missing_reference_file_is_rejected(use_config, tmp_path: Path) -> None:
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(tmp_path / "nope.wav"))
    assert err.value.kind == "bad_request"
    assert "couldn't be found" in (err.value.reason or "")
    assert route.call_count == 0


@respx.mock
@pytest.mark.parametrize("name", ["voice.ogg", "voice.m4a", "voice.wav.txt", "voice"])
def test_reference_must_be_wav_or_mp3(use_config, ref_file, name: str) -> None:
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file(name)))
    assert err.value.kind == "bad_request"
    assert "MP3 or WAV" in (err.value.reason or "")
    assert route.call_count == 0


@respx.mock
def test_empty_reference_file_is_rejected(use_config, ref_file) -> None:
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.wav", b"")))
    assert err.value.kind == "bad_request"
    assert "empty" in (err.value.reason or "")
    assert route.call_count == 0


@respx.mock
def test_oversize_reference_file_is_rejected(use_config, ref_file, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chatterbox, "MAX_REF_BYTES", 10)
    route = respx.post(SPEECH_URL)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.mp3", b"x" * 11)))
    assert err.value.kind == "bad_request"
    assert "too large" in (err.value.reason or "")
    assert route.call_count == 0


def test_limits_match_the_d1_findings() -> None:
    assert chatterbox.MAX_INPUT_CHARS == 4096
    assert chatterbox.MAX_REF_BYTES == 20 * 1024 * 1024


# ---- each error kind, and no automatic retry ---------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "auth"),
        (403, "auth"),
        (404, "config"),
        (500, "bad_response"),
        (502, "unavailable"),
        (503, "unavailable"),
        (429, "unavailable"),
    ],
)
def test_http_errors_map_to_kinds_after_one_attempt(use_config, status: int, kind: str) -> None:
    body = {"error": {"message": "something went wrong", "type": "x", "param": None, "code": "x"}}
    route = respx.post(SPEECH_URL).mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT)
    assert (err.value.service, err.value.kind) == ("chatterbox", kind)
    assert route.call_count == 1  # speech is expensive and the queue is shared: never retried here


@respx.mock
@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectTimeout("slow"), "timeout"),
        (httpx.ConnectError("down"), "unavailable"),
    ],
)
def test_transport_failures_map_to_kinds_after_one_attempt(use_config, exc: Exception, kind: str) -> None:
    route = respx.post(SPEECH_URL).mock(side_effect=exc)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT)
    assert err.value.kind == kind
    assert route.call_count == 1


@respx.mock
def test_bad_input_400_keeps_the_server_reason(use_config) -> None:
    body = {
        "error": {
            "message": "Unsupported language",
            "type": "invalid_request_error",
            "param": "language_id",
            "code": "invalid_value",
        }
    }
    respx.post(SPEECH_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, language="xx")
    assert err.value.kind == "bad_request"
    assert err.value.reason == "Unsupported language"


@respx.mock
def test_a_non_reference_400_with_a_reference_keeps_the_server_reason(use_config, ref_file) -> None:
    body = {
        "error": {
            "message": "Unsupported language",
            "type": "invalid_request_error",
            "param": "language_id",
            "code": "invalid_value",
        }
    }
    respx.post(SPEECH_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.wav")), language="xx")
    assert err.value.kind == "bad_request"
    assert err.value.reason == "Unsupported language"


@respx.mock
def test_invalid_reference_code_is_recognised_even_with_other_wording(use_config, ref_file) -> None:
    body = {
        "error": {
            "message": "Clip rejected.",
            "type": "invalid_request_error",
            "param": "ref_audio",
            "code": "invalid_reference",
        }
    }
    respx.post(SPEECH_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.wav")))
    assert err.value.reason == chatterbox.REF_REJECTED_REASON


@respx.mock
@pytest.mark.parametrize(
    "message",
    [
        "Reference audio could not be decoded or violates the configured duration/audio limits.",
        "Reference file is empty.",
    ],
)
def test_rejected_reference_gets_a_plain_reason(use_config, ref_file, message: str) -> None:
    body = {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "param": "ref_audio",
            "code": "invalid_reference",
        }
    }
    respx.post(SPEECH_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.wav")))
    assert err.value.kind == "bad_request"
    assert err.value.reason == chatterbox.REF_REJECTED_REASON
    assert "MP3 or WAV" in err.value.reason


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b""),
        httpx.Response(200, json={"status": "ok"}),
        httpx.Response(200, content=b"RIFF\x00\x00\x00\x00WAVE"),  # we asked for MP3
    ],
)
def test_a_200_without_mp3_audio_is_a_bad_response(use_config, response: httpx.Response) -> None:
    respx.post(SPEECH_URL).mock(return_value=response)
    with pytest.raises(ServiceError) as err:
        chatterbox.speak(TEXT)
    assert err.value.kind == "bad_response"


# ---- only Chatterbox, only the speech endpoint -------------------------------------------------


def test_only_the_speech_endpoint_on_port_9008_is_called(use_config, ref_file) -> None:
    with respx.mock(assert_all_called=False) as router:
        speech = router.post(SPEECH_URL).mock(return_value=httpx.Response(200, content=MP3))
        voices = router.post(VOICES_URL).mock(return_value=httpx.Response(200, json={}))
        chatterbox.speak(TEXT)
        chatterbox.speak(TEXT, voice_ref_path=str(ref_file("voice.wav")))
    assert speech.call_count == 2
    assert voices.call_count == 0  # never save a voice on the shared server
    for call in router.calls:
        assert call.request.url.port == 9008


def test_the_module_names_no_other_service_or_speech_library() -> None:
    source = (ROOT / "jukebox" / "clients" / "chatterbox.py").read_text(encoding="utf-8").lower()
    for word in (
        "qwen",
        "flux",
        "acestep",
        "ace-step",
        "9001",
        "9006",
        "9007",
        "pyttsx3",
        "gtts",
        "speechsynthesis",
        "/v1/voices",
    ):
        assert word not in source, word
