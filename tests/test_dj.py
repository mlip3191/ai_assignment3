"""Tests for jukebox/services/dj.py and jukebox/prompts/dj.md: song-specific DJ intros (task D3).

Qwen is replaced by a fake that records the messages it gets and returns scripted replies.
Chatterbox is replaced by a fake in most tests, and mocked at the HTTP level with respx in the
end-to-end test. No real class service is ever called.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.chatterbox as chatterbox  # noqa: E402
import jukebox.clients.qwen as qwen  # noqa: E402
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


@pytest.mark.parametrize("title", ["The {mood} Hour", "{title} of {style}", "{previous} Love"])
def test_placeholder_names_in_a_title_are_not_filled_in(title: str) -> None:
    odd = SimpleNamespace(**{**vars(TRACK), "title": title})
    user = dj.build_messages(odd, previous=PREVIOUS)[1]["content"]
    assert f"Title: {title}" in user


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


@pytest.mark.parametrize(
    "text",
    [
        "Five * two is ten, and a 3*4 groove keeps it moving.",
        "A song (written for night drives) with a 2*2 beat.",
    ],
)
def test_cleanup_keeps_ordinary_text(text: str) -> None:
    assert dj.clean_script(text) == text


@pytest.mark.parametrize(
    "direction", ["(laughs)", "(Pauses for effect)", "(upbeat music)", "*clears throat*"]
)
def test_cleanup_drops_spoken_stage_directions(direction: str) -> None:
    assert dj.clean_script(f"{direction} Here comes the next one.") == "Here comes the next one."


@pytest.mark.parametrize(
    ("title", "reply_title"),
    [
        ("Midnight [Remix]", "Midnight"),
        ("*Starlit* Avenue", "Starlit Avenue"),
        ("Glow (Live)", "Glow (Live)"),
    ],
)
def test_titles_with_brackets_or_asterisks_can_still_match(fake_qwen, title: str, reply_title: str) -> None:
    track = SimpleNamespace(**{**vars(TRACK), "title": title})
    reply = f"Next up on the AI Jukebox is {reply_title}, a mellow acoustic folk tune for the road home. Enjoy it."
    qwen = fake_qwen(reply)
    assert dj.write_script(track)
    assert len(qwen.calls) == 1


@pytest.mark.parametrize(
    ("title", "partial", "whole"),
    [
        (
            "Run",
            "Running late? This mellow folk tune slows you down.",
            "Run is a mellow folk tune to slow you down.",
        ),
        ("Glow", "Feel the glowing warmth of this folk tune.", "Feel the warmth of Glow, a folk tune."),
    ],
)
def test_title_must_appear_as_whole_words(title: str, partial: str, whole: str) -> None:
    assert "title" in (dj.script_problem(partial, title) or "")
    assert "title" not in (dj.script_problem(whole, title) or "")  # these short samples may trip the minimum


def test_a_title_with_an_apostrophe_matches_a_curly_one() -> None:
    reply = "Here on the AI Jukebox, Don’t Stop keeps the mellow folk mood going all night long."
    assert dj.script_problem(reply, "Don't Stop") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\"Hello there, this is Midnight Lanterns.'", "\"Hello there, this is Midnight Lanterns.'"),
        ("‘Hello, this is Midnight Lanterns.’", "Hello, this is Midnight Lanterns."),
    ],
)
def test_only_a_matched_pair_of_quotes_is_stripped(raw: str, expected: str) -> None:
    assert dj.clean_script(raw) == expected


def test_title_match_ignores_case_and_quote_style(fake_qwen) -> None:
    fake_qwen(GOOD.replace("Midnight Lanterns", "‘midnight lanterns’"))
    assert "midnight lanterns" in dj.write_script(TRACK)


def test_a_reply_without_the_title_is_retried_once(fake_qwen) -> None:
    qwen = fake_qwen("Here's a lovely mellow folk song for you. Enjoy it, friends, and stay tuned.", GOOD)
    assert dj.write_script(TRACK) == GOOD
    assert len(qwen.calls) == 2
    retry = user_text(qwen.calls[1])
    assert TRACK.title in retry and "title" in retry.lower()


def test_a_reply_under_the_minimum_is_retried_once(fake_qwen) -> None:
    qwen = fake_qwen("Up next: Midnight Lanterns.", GOOD)
    assert dj.write_script(TRACK) == GOOD
    assert len(qwen.calls) == 2
    retry = dj.script_problem("Up next: Midnight Lanterns.", TRACK.title) or ""
    assert str(dj.MIN_WORDS) in retry


def test_the_minimum_is_inclusive() -> None:
    words = ["Midnight", "Lanterns"] + ["la"] * (dj.MIN_WORDS - 2)
    assert dj.script_problem(" ".join(words), TRACK.title) is None
    assert dj.script_problem(" ".join(words[:-1]), TRACK.title) is not None


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


def test_a_briefly_locked_target_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_replace = dj.os.replace
    failures = iter([PermissionError("locked"), PermissionError("locked")])
    waits: list[float] = []

    def flaky_replace(src, dst):
        error = next(failures, None)
        if error:
            raise error
        real_replace(src, dst)

    monkeypatch.setattr(dj.os, "replace", flaky_replace)
    monkeypatch.setattr(dj, "_sleep", waits.append)
    target = tmp_path / "dj_t1_default.mp3"

    dj._write_atomically(target, MP3)

    assert target.read_bytes() == MP3
    assert waits == [dj.REPLACE_WAIT_S, dj.REPLACE_WAIT_S]
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


def test_a_target_that_stays_locked_raises_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_locked(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(dj.os, "replace", always_locked)
    monkeypatch.setattr(dj, "_sleep", lambda s: None)
    with pytest.raises(PermissionError):
        dj._write_atomically(tmp_path / "dj_t1_default.mp3", MP3)
    assert list(tmp_path.iterdir()) == []


def test_concurrent_saves_of_the_same_clip_all_succeed(tmp_path: Path) -> None:
    import threading

    target = tmp_path / "dj_t1_default.mp3"
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def save(n: int) -> None:
        start.wait()
        try:
            dj._write_atomically(target, MP3 + bytes([n]))
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    for _ in range(10):
        threads = [threading.Thread(target=save, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == []
    assert target.read_bytes().startswith(MP3)
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


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


@respx.mock
def test_end_to_end_with_both_real_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://class.example:{port}"
    cfg = load_config(env=env, env_file=tmp_path / "missing-file")
    monkeypatch.setattr(qwen, "_default", qwen.QwenClient(cfg, sleep=lambda s: None))
    monkeypatch.setattr(
        chatterbox, "_new_client", lambda: ServiceClient("chatterbox", cfg, sleep=lambda s: None)
    )
    reply = {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": GOOD}, "finish_reason": "stop"}]
    }
    chat = respx.post("http://class.example:9001/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=reply)
    )
    speech = respx.post("http://class.example:9008/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=MP3)
    )

    clip = dj.make_clip(TRACK, out_dir=tmp_path / "gen")

    sent = json.loads(chat.calls.last.request.content)
    assert TRACK.title in sent["messages"][-1]["content"]
    assert sent["max_tokens"] == dj.QWEN_MAX_TOKENS
    assert json.loads(speech.calls.last.request.content)["input"] == GOOD
    assert clip.script == GOOD
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
