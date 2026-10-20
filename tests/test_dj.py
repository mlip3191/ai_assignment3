"""Tests for jukebox/services/dj.py and jukebox/prompts/dj.md: song-specific DJ intros (task D3).

Qwen is replaced by a fake that records the messages it gets and returns scripted replies.
Chatterbox is replaced by a fake in most tests, and mocked at the HTTP level with respx in the
end-to-end test. No real class service is ever called.
"""

from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import jukebox.clients.qwen  # noqa: E402,F401
except ImportError:  # B3 (#21) isn't on this branch yet; every test replaces qwen.chat anyway
    _stub = types.ModuleType("jukebox.clients.qwen")

    def _unpatched_chat(*args, **kwargs):
        raise AssertionError("tests must replace qwen.chat")

    _stub.chat = _unpatched_chat
    sys.modules["jukebox.clients.qwen"] = _stub

import jukebox.clients.chatterbox as chatterbox  # noqa: E402
import jukebox.services.dj as dj  # noqa: E402
from jukebox.clients.base import ServiceClient  # noqa: E402
from jukebox.config import load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
TRACK = SimpleNamespace(
    id="a1b2c3d4",
    title="Midnight Lanterns",
    style="acoustic folk, fingerpicked guitar",
    mood="mellow",
    theme="finding your way home",
)
PREVIOUS = SimpleNamespace(
    id="prev01", title="Sunset Gearshift", style="synth-pop", mood="upbeat", theme=None
)
GOOD = (
    "You're locked in to the AI Jukebox. We're slowing it down now with Midnight Lanterns, "
    "a mellow acoustic folk tune with gentle fingerpicked guitar about finding your way home. Settle in."
)


class FakeQwen:
    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], *, max_tokens: int = 600, temperature: float = 0.8) -> str:
        self.calls.append([dict(m) for m in messages])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeSpeech:
    def __init__(self, result: tuple[bytes, str] | Exception = (MP3, "mp3")) -> None:
        self.result = result
        self.calls: list[dict] = []

    def speak(self, text: str, **kwargs) -> tuple[bytes, str]:
        self.calls.append({"text": text, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def fake_qwen(monkeypatch: pytest.MonkeyPatch):
    def install(*replies: str | Exception) -> FakeQwen:
        fake = FakeQwen(*replies)
        monkeypatch.setattr(dj.qwen, "chat", fake.chat)
        return fake

    return install


@pytest.fixture
def fake_speech(monkeypatch: pytest.MonkeyPatch):
    def install(result: tuple[bytes, str] | Exception = (MP3, "mp3")) -> FakeSpeech:
        fake = FakeSpeech(result)
        monkeypatch.setattr(dj.chatterbox, "speak", fake.speak)
        return fake

    return install


def user_text(call: list[dict]) -> str:
    return "\n".join(m["content"] for m in call if m["role"] == "user")


# ---- the prompt (prompts/dj.md, §8.3) ----------------------------------------------------------


def test_prompt_file_states_the_rules() -> None:
    text = dj.PROMPT_PATH.read_text(encoding="utf-8").lower()
    for rule in (
        "30",
        "50",
        "title",
        "style",
        "mood",
        "theme",
        "plain",
        "emoji",
        "stage direction",
        "real artist",
    ):
        assert rule in text, rule


def test_messages_carry_title_style_mood_and_theme() -> None:
    messages = dj.build_messages(TRACK)
    assert [m["role"] for m in messages] == ["system", "user"]
    user = messages[1]["content"]
    for value in (TRACK.title, TRACK.style, TRACK.mood, TRACK.theme):
        assert value in user
    assert "{" not in user  # every placeholder was filled


def test_missing_theme_and_previous_track_are_handled() -> None:
    no_theme = SimpleNamespace(**{**vars(TRACK), "theme": None})
    user = dj.build_messages(no_theme)[1]["content"]
    assert "None" not in user
    assert "{" not in user

    with_previous = dj.build_messages(TRACK, previous=PREVIOUS)[1]["content"]
    assert PREVIOUS.title in with_previous


def test_braces_in_a_title_do_not_break_the_prompt() -> None:
    odd = SimpleNamespace(**{**vars(TRACK), "title": "Curly {Brace} Blues"})
    assert "Curly {Brace} Blues" in dj.build_messages(odd)[1]["content"]


# ---- write_script: song-specific, under the word limit -----------------------------------------


def test_a_good_reply_is_used_as_is(fake_qwen) -> None:
    qwen = fake_qwen(GOOD)
    script = dj.write_script(TRACK)
    assert script == GOOD
    assert TRACK.title in script
    assert len(script.split()) <= dj.MAX_WORDS
    assert len(qwen.calls) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (f'"{GOOD}"', GOOD),
        (f"“{GOOD}”", GOOD),
        (f"*clears throat* {GOOD}", GOOD),
        (f"[upbeat] {GOOD} 🎶🎸", GOOD),
        (f"DJ: {GOOD}", GOOD),
        (GOOD.replace(". ", ".\n\n"), GOOD),
    ],
)
def test_cleanup_removes_what_tts_would_read_aloud(fake_qwen, raw: str, expected: str) -> None:
    fake_qwen(raw)
    assert dj.write_script(TRACK) == expected


def test_title_match_ignores_case_and_quote_style(fake_qwen) -> None:
    fake_qwen(GOOD.replace("Midnight Lanterns", "‘midnight lanterns’"))
    assert "midnight lanterns" in dj.write_script(TRACK)


def test_a_reply_without_the_title_is_retried_once(fake_qwen) -> None:
    qwen = fake_qwen("Here's a lovely mellow folk song for you. Enjoy it, friends, and stay tuned.", GOOD)
    assert dj.write_script(TRACK) == GOOD
    assert len(qwen.calls) == 2
    retry = user_text(qwen.calls[1])
    assert TRACK.title in retry and "title" in retry.lower()


def test_a_reply_over_the_word_limit_is_retried_once(fake_qwen) -> None:
    long_reply = GOOD + " " + "So many more words keep coming here." * 6
    qwen = fake_qwen(long_reply, GOOD)
    assert dj.write_script(TRACK) == GOOD
    assert len(qwen.calls) == 2
    assert str(dj.MAX_WORDS) in user_text(qwen.calls[1])


def test_two_bad_replies_give_up_without_a_stand_in(fake_qwen, fake_speech) -> None:
    fake_qwen(
        "No title here at all, just vibes.",
        "",
    )
    speech = fake_speech()
    with pytest.raises(ServiceError) as err:
        dj.make_clip(TRACK, out_dir=Path("unused"))
    assert (err.value.service, err.value.kind) == ("qwen", "bad_response")
    assert speech.calls == []  # never speaks a script that failed the checks


def test_qwen_errors_pass_through(fake_qwen, fake_speech, tmp_path: Path) -> None:
    fake_qwen(ServiceError("qwen", "timeout", "ReadTimeout"))
    speech = fake_speech()
    with pytest.raises(ServiceError) as err:
        dj.make_clip(TRACK, out_dir=tmp_path)
    assert err.value.kind == "timeout"
    assert speech.calls == []
    assert list(tmp_path.iterdir()) == []


# ---- make_clip: speech saved under runtime/generated/ ------------------------------------------


def test_clip_is_saved_with_track_and_voice_in_the_name(fake_qwen, fake_speech, tmp_path: Path) -> None:
    fake_qwen(GOOD)
    speech = fake_speech()
    clip = dj.make_clip(TRACK, out_dir=tmp_path)

    assert clip.track_id == TRACK.id
    assert clip.voice_key == "default"
    assert clip.script == GOOD
    assert clip.audio_path == tmp_path / f"dj_{TRACK.id}_default.mp3"
    assert clip.audio_path.read_bytes() == MP3
    assert [p.name for p in tmp_path.iterdir()] == [clip.audio_path.name]  # no temp file left behind
    assert speech.calls[0]["text"] == GOOD
    assert speech.calls[0]["voice_ref_path"] is None


def test_default_output_folder_is_runtime_generated() -> None:
    assert dj.GENERATED_DIR == ROOT / "runtime" / "generated"


def test_delivery_settings_are_passed_to_speech(fake_qwen, fake_speech, tmp_path: Path) -> None:
    fake_qwen(GOOD)
    speech = fake_speech()
    dj.make_clip(TRACK, out_dir=tmp_path)
    assert speech.calls[0]["exaggeration"] == dj.DJ_EXAGGERATION
    assert speech.calls[0]["cfg_weight"] == dj.DJ_CFG_WEIGHT


def test_custom_voice_is_passed_on_and_keyed_by_its_content(fake_qwen, fake_speech, tmp_path: Path) -> None:
    ref_a = tmp_path / "a.wav"
    ref_a.write_bytes(b"voice A")
    ref_b = tmp_path / "b.wav"
    ref_b.write_bytes(b"voice B")
    out = tmp_path / "out"
    fake_qwen(GOOD, GOOD)
    speech = fake_speech()

    clip_a = dj.make_clip(TRACK, voice_ref_path=str(ref_a), out_dir=out)
    clip_b = dj.make_clip(TRACK, voice_ref_path=str(ref_b), out_dir=out)

    assert speech.calls[0]["voice_ref_path"] == str(ref_a)
    assert clip_a.voice_key != "default"
    assert clip_a.voice_key != clip_b.voice_key  # changing the voice changes the cache key (D5)
    assert clip_a.voice_key == dj.voice_key(str(ref_a))
    assert clip_a.audio_path != clip_b.audio_path


def test_unsafe_characters_in_a_track_id_stay_out_of_the_filename(
    fake_qwen, fake_speech, tmp_path: Path
) -> None:
    fake_qwen(GOOD)
    fake_speech()
    odd = SimpleNamespace(**{**vars(TRACK), "id": "../../etc/x y"})
    clip = dj.make_clip(odd, out_dir=tmp_path)
    assert clip.audio_path.parent == tmp_path
    assert (
        "/" not in clip.audio_path.name
        and "\\" not in clip.audio_path.name
        and ".." not in clip.audio_path.name
    )


def test_speech_errors_pass_through_and_write_nothing(fake_qwen, fake_speech, tmp_path: Path) -> None:
    fake_qwen(GOOD)
    fake_speech(ServiceError("chatterbox", "unavailable", "HTTP 503"))
    with pytest.raises(ServiceError) as err:
        dj.make_clip(TRACK, out_dir=tmp_path)
    assert (err.value.service, err.value.kind) == ("chatterbox", "unavailable")
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_end_to_end_with_the_real_speech_client(
    fake_qwen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://class.example:{port}"
    cfg = load_config(env=env, env_file=tmp_path / "missing-file")
    monkeypatch.setattr(
        chatterbox, "_new_client", lambda: ServiceClient("chatterbox", cfg, sleep=lambda s: None)
    )
    route = respx.post("http://class.example:9008/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=MP3)
    )
    fake_qwen(GOOD)

    clip = dj.make_clip(TRACK, previous=PREVIOUS, out_dir=tmp_path / "gen")

    body = json.loads(route.calls.last.request.content)
    assert body["input"] == GOOD
    assert (body["exaggeration"], body["cfg_weight"]) == (dj.DJ_EXAGGERATION, dj.DJ_CFG_WEIGHT)
    assert clip.audio_path.read_bytes() == MP3


# ---- only Qwen and Chatterbox (H15) -----------------------------------------------------------


def test_dj_imports_only_the_qwen_and_chatterbox_clients() -> None:
    tree = ast.parse((ROOT / "jukebox" / "services" / "dj.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            if node.module == "jukebox.clients":
                imported.update(f"jukebox.clients.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    clients = {name for name in imported if name.startswith("jukebox.clients.")}
    assert clients == {"jukebox.clients.qwen", "jukebox.clients.chatterbox"}
    assert not any(name.startswith(("httpx", "requests", "urllib.request")) for name in imported)
