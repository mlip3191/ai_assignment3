"""Tests for the cover-art prompt builder in jukebox/services/art.py (task C3).

Qwen is mocked: a fake `chat(messages, *, max_tokens, temperature) -> str` matching PROJECT.md 7.2
stands in until the real client (B3) lands. No class service is ever called.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.errors import ServiceError  # noqa: E402
from jukebox.services import art  # noqa: E402

SUFFIX = "square album cover, no text, no letters, no logos, no real people"

LOFI = {
    "title": "Midnight Notes",
    "style": "lo-fi hip hop, jazzy keys, vinyl crackle",
    "mood": "mellow",
    "theme": "late-night study session",
    "vocal": False,
    "lyrics": None,
}
POP = {
    "title": "Windows Down",
    "style": "upbeat pop, summery, bright synths",
    "mood": "joyful",
    "theme": "road trip with friends",
    "vocal": True,
    "lyrics": "[verse]\nSun on the dashboard, wheels on the road\n[chorus]\nWindows down, singing loud",
}
FOLK = {
    "title": "Last Train Home",
    "style": "cinematic folk, acoustic guitar, strings",
    "mood": "melancholy",
    "theme": "leaving a hometown",
    "vocal": True,
    "lyrics": "[verse]\nPorch light fading as the platform hums\n[chorus]\nI carry the river wherever I run",
}


class FakeQwen:
    """Records every call and answers with a reply built from the user message."""

    def __init__(self, reply: str | None = None) -> None:
        self.calls: list[dict] = []
        self.reply = reply

    def __call__(self, messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        self.calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        if self.reply is not None:
            return self.reply
        user = messages[-1]["content"]
        fields = dict(line.split(": ", 1) for line in user.splitlines() if ": " in line)
        return f"A {fields['Mood']} scene for {fields['Title']}, painted in the style of {fields['Style']}"


def _user(chat: FakeQwen) -> str:
    return chat.calls[0]["messages"][-1]["content"]


# ---- the template -----------------------------------------------------------------------------


def test_template_has_system_user_and_suffix_sections() -> None:
    t = art.load_template()
    assert "album cover" in t.system
    assert "{title}" in t.user and "{lyrics_block}" in t.user
    assert t.suffix == SUFFIX


def test_template_system_rules_forbid_text_real_people_and_real_artists() -> None:
    system = art.load_template().system.lower()
    for phrase in ("text", "real artists", "real person", "original", "no visible face"):
        assert phrase in system


def test_missing_section_is_a_clear_error(tmp_path: Path) -> None:
    broken = tmp_path / "cover_art.md"
    broken.write_text("## System\nhi\n\n## User\nthere\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Suffix"):
        art.load_template(broken)


# ---- building the messages --------------------------------------------------------------------


def test_messages_are_system_then_user_with_every_placeholder_filled() -> None:
    messages = art.build_messages(**POP)
    assert [m["role"] for m in messages] == ["system", "user"]
    user = messages[1]["content"]
    for value in ("Windows Down", "upbeat pop", "joyful", "road trip with friends"):
        assert value in user
    assert "{" not in user and "}" not in user


def test_vocal_track_includes_a_lyrics_excerpt() -> None:
    user = art.build_messages(**POP)[1]["content"]
    assert "Lyrics (excerpt):" in user
    assert "Sun on the dashboard" in user


def test_long_lyrics_are_cut_to_the_excerpt_length() -> None:
    song = dict(POP, lyrics="la " * 2000)
    user = art.build_messages(**song)[1]["content"]
    excerpt = user.split("Lyrics (excerpt):", 1)[1]
    assert len(excerpt.strip()) <= art.LYRICS_EXCERPT_CHARS


def test_instrumental_track_says_so_and_sends_no_lyrics() -> None:
    user = art.build_messages(**dict(LOFI, lyrics="should be ignored"))[1]["content"]
    assert "Instrumental track, no lyrics." in user
    assert "should be ignored" not in user


@pytest.mark.parametrize("theme", [None, "", "   "])
def test_missing_theme_reads_none_given(theme: str | None) -> None:
    user = art.build_messages(**dict(LOFI, theme=theme))[1]["content"]
    assert "Theme: none given" in user


def test_braces_in_user_input_are_kept_literally() -> None:
    user = art.build_messages(**dict(LOFI, style="lo-fi {mood} {title}"))[1]["content"]
    assert "Style: lo-fi {mood} {title}" in user


# ---- asking Qwen and finishing the prompt -----------------------------------------------------


def test_three_contrasting_songs_give_distinct_prompts() -> None:
    prompts = {art.write_cover_prompt(**song, chat=FakeQwen()) for song in (LOFI, POP, FOLK)}
    assert len(prompts) == 3


def test_the_suffix_is_always_appended_once() -> None:
    for song in (LOFI, POP, FOLK):
        prompt = art.write_cover_prompt(**song, chat=FakeQwen())
        assert prompt.endswith(SUFFIX)
        assert prompt.count(SUFFIX) == 1


def test_a_reply_that_already_ends_with_the_suffix_is_not_doubled() -> None:
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply=f"A quiet desk at night. {SUFFIX}."))
    assert prompt.count(SUFFIX) == 1


def test_reply_is_cleaned_of_thinking_quotes_and_extra_space() -> None:
    reply = '<think>plan the image</think>\n  "A rainy window,\n  warm lamp light."  '
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply=reply))
    assert prompt == f"A rainy window, warm lamp light, {SUFFIX}"


@pytest.mark.parametrize("reply", ["", "   ", "<think>only thinking</think>", '""'])
def test_an_empty_reply_is_a_qwen_bad_response(reply: str) -> None:
    with pytest.raises(ServiceError) as exc:
        art.write_cover_prompt(**LOFI, chat=FakeQwen(reply=reply))
    assert (exc.value.service, exc.value.kind) == ("qwen", "bad_response")


def test_a_qwen_error_is_passed_through_unchanged() -> None:
    def failing_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        raise ServiceError("qwen", "timeout", "slow")

    with pytest.raises(ServiceError) as exc:
        art.write_cover_prompt(**LOFI, chat=failing_chat)
    assert (exc.value.service, exc.value.kind) == ("qwen", "timeout")


def test_qwen_gets_one_call_with_the_documented_settings() -> None:
    chat = FakeQwen()
    art.write_cover_prompt(**POP, chat=chat)
    assert len(chat.calls) == 1
    assert chat.calls[0]["max_tokens"] == art.MAX_TOKENS
    assert chat.calls[0]["temperature"] == art.TEMPERATURE
    assert "Windows Down" in _user(chat)


def test_the_builder_never_calls_flux() -> None:
    source = (ROOT / "jukebox" / "services" / "art.py").read_text(encoding="utf-8")
    builder = source.split("def write_cover_prompt", 1)[1].split("\ndef ", 1)[0]
    assert "flux" not in builder.lower()
