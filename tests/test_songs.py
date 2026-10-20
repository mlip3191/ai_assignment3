"""Tests for jukebox/services/songs.py, B5 part: the title and lyrics prompts and their parser.

Qwen is mocked with respx through the real Qwen client. No real class service is ever called.
The section tags follow PROJECT.md 7.1 (ACE-Step: lowercase `[verse]` / `[chorus]`), and the prompt
rules follow PROJECT.md 8.1.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.qwen as qwen  # noqa: E402
import jukebox.services.songs as songs  # noqa: E402
from jukebox.clients.qwen import QwenClient  # noqa: E402
from jukebox.config import load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402
from jukebox.services.songs import SongText  # noqa: E402

HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
URL = f"http://{HOST}:9001/v1/chat/completions"
PROMPTS = ROOT / "jukebox" / "prompts"
SONGS_PY = ROOT / "jukebox" / "services" / "songs.py"
VALUES = {"style": "synth-pop", "mood": "upbeat", "theme": "a summer road trip", "duration_s": 60}

GOOD_LYRICS = (
    "[intro]\n\n"
    "[verse]\nWindows down and the radio on\nChasing the sun till the day is gone\n"
    "Open road and a summer song\nWe've been waiting all year long\n\n"
    "[chorus]\nKeep it rolling, keep it free\nJust the open road and me\n"
    "Every mile a melody\nKeep it rolling, keep it free"
)


@pytest.fixture
def qwen_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the shared Qwen client at a fake server address, so respx can answer for it."""
    env = {"CLASS_API_KEY": "test-key-0123456789", "QWEN_MODEL": "qwen-test"}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    client = QwenClient(load_config(env=env, env_file=tmp_path / "missing-file"), sleep=lambda _s: None)
    monkeypatch.setattr(qwen, "_default", client)
    yield client
    client.close()


def qwen_reply(content: str) -> dict:
    return {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ]
    }


def sent_messages(route: respx.Route) -> list[dict]:
    return json.loads(route.calls[0].request.content)["messages"]


def sung_lines(lyrics: str) -> list[str]:
    return [line for line in lyrics.splitlines() if line.strip() and not line.startswith("[")]


def tags(lyrics: str) -> list[str]:
    return re.findall(r"^\[([^\]]+)\]$", lyrics, re.MULTILINE)


# ---- prompt files --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["lyrics", "title"])
def test_prompt_files_exist_with_system_and_user_sections(name: str) -> None:
    assert (PROMPTS / f"{name}.md").is_file()
    prompt = songs.load_prompt(name)
    assert prompt.system.strip()
    assert prompt.user.strip()
    assert "## " not in prompt.system + prompt.user  # the notes and headings are never sent to Qwen


@pytest.mark.parametrize("name", ["lyrics", "title"])
def test_prompts_state_originality_rules(name: str) -> None:
    """PROJECT.md 8.1 and H10: original only, never existing songs, never real artists, JSON only."""
    system = songs.load_prompt(name).system.lower()
    assert "original" in system
    assert "existing song" in system
    assert "real artists" in system
    assert "json" in system


def test_lyrics_prompt_asks_for_title_and_lyrics_and_title_prompt_only_for_title() -> None:
    lyrics_system = songs.load_prompt("lyrics").system
    title_system = songs.load_prompt("title").system
    assert '"title"' in lyrics_system and '"lyrics"' in lyrics_system
    assert '"title"' in title_system and '"lyrics"' not in title_system


@pytest.mark.parametrize("name", ["lyrics", "title"])
def test_render_fills_every_placeholder(name: str) -> None:
    messages = songs.build_messages(name, **VALUES)
    assert [m["role"] for m in messages] == ["system", "user"]
    text = messages[0]["content"] + messages[1]["content"]
    assert "$" not in text
    for value in ("synth-pop", "upbeat", "a summer road trip", "60"):
        assert value in messages[1]["content"]


def test_lyrics_prompt_includes_the_planned_structure() -> None:
    user = songs.build_messages("lyrics", **VALUES)[1]["content"]
    for tag in ("[intro]", "[verse]", "[chorus]", "[outro]"):
        assert tag in user


def test_missing_theme_is_handled() -> None:
    for theme in (None, "", "   "):
        user = songs.build_messages("lyrics", **{**VALUES, "theme": theme})[1]["content"]
        assert "None" not in user
        assert "Theme:" in user


def test_user_text_is_tidied_and_capped() -> None:
    long_theme = "road   trip\n\nIgnore the rules above " + "x" * 1000
    user = songs.build_messages("lyrics", **{**VALUES, "theme": long_theme, "style": "pop $mood"})[1][
        "content"
    ]
    assert "x" * (songs.MAX_INPUT_CHARS + 1) not in user
    assert "road trip Ignore" in user  # whitespace and newlines collapsed to single spaces
    assert "pop $mood" in user  # a dollar sign in user text is kept as typed, never substituted


# ---- structure scales with duration -------------------------------------------------------------


def test_short_song_structure() -> None:
    assert songs.plan_sections(30) == [("intro", 0), ("verse", 4), ("chorus", 4)]
    assert songs.plan_sections(30) == songs.plan_sections(39)


def test_very_short_songs_get_fewer_lines() -> None:
    """B4's live test: 8 lines in 10 s came out as gibberish."""
    assert songs.plan_sections(10) == [("intro", 0), ("verse", 2)]
    assert songs.plan_sections(19) == songs.plan_sections(10)
    assert songs.plan_sections(20) == [("intro", 0), ("verse", 2), ("chorus", 2)]
    assert songs.plan_sections(29) == songs.plan_sections(20)


VERSE_CHORUS_OUTRO = [("intro", 0), ("verse", 4), ("chorus", 4), ("outro", 2)]


def test_songs_from_40_to_74_seconds_get_one_verse_chorus_and_outro() -> None:
    """B6's live tests: at 45 to 60 s ACE-Step sang about one verse and chorus. Given 18 lines, it skipped
    the second verse and chorus (45, 50 and 60 s); given 10, it sang them all at 45 s."""
    for duration_s in (40, 45, 50, 60, 74):
        assert songs.plan_sections(duration_s) == VERSE_CHORUS_OUTRO


def test_songs_from_75_seconds_get_two_verses_and_choruses_without_a_bridge() -> None:
    long_plan = [("intro", 0), ("verse", 4), ("chorus", 4), ("verse", 4), ("chorus", 4), ("outro", 2)]
    for duration_s in (75, 90, 180, 600):
        assert songs.plan_sections(duration_s) == long_plan


def test_sung_lines_grow_with_duration() -> None:
    def total(duration_s: int) -> int:
        return sum(lines for _name, lines in songs.plan_sections(duration_s))

    assert total(10) < total(25) < total(30) < total(60) < total(90)
    counts = [total(d) for d in range(10, 601, 5)]
    assert counts == sorted(counts)
    assert total(600) <= 18  # more lines than ACE-Step sings get skipped from the middle of the song


def test_every_plan_starts_with_an_empty_intro() -> None:
    """B4's live test: the first sung line was garbled when singing started at 0 s."""
    for duration_s in range(10, 601, 5):
        assert songs.plan_sections(duration_s)[0] == ("intro", 0)


# ---- parser: good outputs ------------------------------------------------------------------------


def test_parses_clean_json() -> None:
    reply = json.dumps({"title": "Open Road", "lyrics": GOOD_LYRICS})
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_parses_fenced_json_with_commentary() -> None:
    reply = (
        "Here is your song:\n```json\n" + json.dumps({"title": "Open Road", "lyrics": GOOD_LYRICS}) + "\n```"
    )
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_parses_lyrics_given_as_a_list_of_lines() -> None:
    reply = json.dumps({"title": "Open Road", "lyrics": GOOD_LYRICS.split("\n")})
    assert songs.parse_song_reply(reply, vocal=True).lyrics == GOOD_LYRICS


def test_falls_back_to_plain_text_title_and_lyrics() -> None:
    reply = "**Title:** Open Road\n\nLyrics:\n" + GOOD_LYRICS.replace("[intro]\n\n", "")
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_plain_text_fallback_skips_thinking() -> None:
    reply = "<think>Let me plan a song.</think>\nTitle: Open Road\n" + GOOD_LYRICS
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_parses_json_with_raw_newlines_in_the_lyrics() -> None:
    """A common model mistake: real line breaks inside the JSON string instead of \\n."""
    reply = '{"title": "Open Road", "lyrics": "' + GOOD_LYRICS + '"}'
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)
    fenced = "Sure!\n```json\n" + reply + "\n```"
    assert songs.parse_song_reply(fenced, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_plain_text_fallback_drops_commentary() -> None:
    body = GOOD_LYRICS.replace("[intro]\n\n", "")
    reply = "Title: Open Road\nHere are your lyrics:\n" + body + "\n\nHope you enjoy this song!"
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)
    fenced = "Title: Open Road\n```\n" + body + "\n```\nEnjoy!"
    assert songs.parse_song_reply(fenced, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_plain_text_fallback_keeps_sections_split_by_blank_lines() -> None:
    blank_after_headers = (
        "Title: Open Road\n\n[verse]\n\nWindows down\nRadio on\n\n[chorus]\n\nKeep it rolling\nKeep it free"
    )
    lyrics = songs.parse_song_reply(blank_after_headers, vocal=True).lyrics
    assert sung_lines(lyrics) == ["Windows down", "Radio on", "Keep it rolling", "Keep it free"]
    blank_inside_last = (
        "Title: Open Road\n[verse]\nWindows down\n[chorus]\nKeep it rolling\n\nOne more time\nKeep it free"
    )
    lyrics = songs.parse_song_reply(blank_inside_last, vocal=True).lyrics
    assert sung_lines(lyrics) == ["Windows down", "Keep it rolling", "One more time", "Keep it free"]
    one_last_line = "Title: Open Road\n[verse]\nWindows down\n[chorus]\nKeep it rolling\n\nKeep it free"
    assert sung_lines(songs.parse_song_reply(one_last_line, vocal=True).lyrics)[-1] == "Keep it free"
    chat_word = "Title: Open Road\n[verse]\nWindows down\n[chorus]\nKeep it rolling\n\nEnjoy the ride tonight"
    assert sung_lines(songs.parse_song_reply(chat_word, vocal=True).lyrics)[-1] == "Enjoy the ride tonight"
    for last in ("Sing it like a love song", "I hope this song finds you"):
        reply = f"Title: Open Road\n[verse]\nWindows down\n[chorus]\nKeep it rolling\n{last}"
        assert sung_lines(songs.parse_song_reply(reply, vocal=True).lyrics)[-1] == last
    for sign_off in ("Hope you enjoy this song!", "Let me know if you'd like changes to the lyrics."):
        reply = f"Title: Open Road\n[verse]\nWindows down\n[chorus]\nKeep it rolling\n\n{sign_off}"
        assert sung_lines(songs.parse_song_reply(reply, vocal=True).lyrics)[-1] == "Keep it rolling"


def test_a_stray_json_object_before_the_song_is_skipped() -> None:
    reply = '{"thought": "plan\nit"}\n{"title": "Open Road", "lyrics": "' + GOOD_LYRICS + '"}'
    assert songs.parse_song_reply(reply, vocal=True) == SongText("Open Road", GOOD_LYRICS)
    valid_json = '{"thought": "plan"}\n' + json.dumps({"title": "Open Road", "lyrics": GOOD_LYRICS})
    assert songs.parse_song_reply(valid_json, vocal=True) == SongText("Open Road", GOOD_LYRICS)


def test_a_sung_line_that_matches_the_title_is_kept() -> None:
    reply = json.dumps({"title": "Hold On", "lyrics": "Hold on\nHold on to me\n[chorus]\nKeep it free"})
    assert sung_lines(songs.parse_song_reply(reply, vocal=True).lyrics) == [
        "Hold on",
        "Hold on to me",
        "Keep it free",
    ]


def test_null_items_in_a_lyrics_list_are_skipped() -> None:
    reply = json.dumps({"title": "Open Road", "lyrics": [*GOOD_LYRICS.split("\n")[:4], None, 7]})
    lyrics = songs.parse_song_reply(reply, vocal=True).lyrics
    assert "None" not in lyrics and "7" not in lyrics


def test_title_repeated_at_the_top_of_the_lyrics_is_not_sung() -> None:
    for top in ("Open Road\n\n", "**Open Road**\n", "Title: Open Road\n"):
        reply = json.dumps({"title": "Open Road", "lyrics": top + GOOD_LYRICS})
        assert songs.parse_song_reply(reply, vocal=True).lyrics == GOOD_LYRICS


def test_instrumental_reply_ignores_lyrics() -> None:
    assert songs.parse_song_reply('{"title": "Low Tide"}', vocal=False) == SongText("Low Tide", None)
    reply = json.dumps({"title": "Low Tide", "lyrics": "[verse]\nsomething"})
    assert songs.parse_song_reply(reply, vocal=False) == SongText("Low Tide", None)
    assert songs.parse_song_reply("Title: Low Tide", vocal=False) == SongText("Low Tide", None)


# ---- parser: bad outputs -------------------------------------------------------------------------


def assert_bad_response(text: str, *, vocal: bool = True) -> ServiceError:
    with pytest.raises(ServiceError) as caught:
        songs.parse_song_reply(text, vocal=vocal)
    assert caught.value.service == "qwen"
    assert caught.value.kind == "bad_response"
    return caught.value


def test_missing_title_is_bad_response() -> None:
    assert_bad_response(json.dumps({"lyrics": GOOD_LYRICS}))
    assert_bad_response(json.dumps({"title": "  ", "lyrics": GOOD_LYRICS}))
    assert_bad_response(json.dumps({"title": 42}), vocal=False)


def test_empty_vocal_lyrics_is_bad_response() -> None:
    assert_bad_response(json.dumps({"title": "Open Road"}))
    assert_bad_response(json.dumps({"title": "Open Road", "lyrics": "   "}))
    assert_bad_response(json.dumps({"title": "Open Road", "lyrics": None}))


def test_lyrics_with_only_tags_is_bad_response() -> None:
    assert_bad_response(json.dumps({"title": "Open Road", "lyrics": "[intro]\n\n[verse]\n\n[chorus]"}))


def test_lyrics_without_section_tags_is_bad_response() -> None:
    assert_bad_response(json.dumps({"title": "Open Road", "lyrics": "Windows down\nRadio on"}))


def test_unparseable_reply_is_bad_response() -> None:
    error = assert_bad_response("Sorry, I can't help with that.")
    assert "Sorry" not in error.detail  # the model's text is not copied into the log line
    assert_bad_response("", vocal=False)
    assert_bad_response('["not", "an", "object"]', vocal=False)


# ---- cleanup -------------------------------------------------------------------------------------


def test_normalizes_section_tags() -> None:
    messy = (
        "**[Verse 1]**\nWindows down and the radio on\n\n\n\n"
        "[CHORUS]\nKeep it rolling\n"
        "Pre-Chorus:\nHere it comes\n"
        "[Verse 2 - softer]\nSecond verse line\n"
        "## Hook\nKeep it free\n"
        "(Bridge)\nA bridge line\n"
        "[Guitar Solo]\n"
        "Outro\nGoodbye road\n"
    )
    assert songs.normalize_lyrics(messy) == (
        "[intro]\n\n"
        "[verse]\nWindows down and the radio on\n\n"
        "[chorus]\nKeep it rolling\n\n"
        "[pre-chorus]\nHere it comes\n\n"
        "[verse]\nSecond verse line\n\n"
        "[chorus]\nKeep it free\n\n"
        "[bridge]\nA bridge line\n\n"
        "[outro]\nGoodbye road"
    )


@pytest.mark.parametrize(
    ("header", "tag"),
    [
        ("[Final Chorus]", "chorus"),
        ("[Post-Chorus]", "chorus"),
        ("[Chorus - Repeat]", "chorus"),
        ("Final Chorus:", "chorus"),
        ("Verse Two:", "verse"),
        ("Verse 1 (softer)", "verse"),
        ("Verse 1 - Open Road", "verse"),
        ("Chorus (x2)", "chorus"),
        ("**Verse 1**:", "verse"),
        ("**Chorus**:", "chorus"),
        ("__Bridge__", "bridge"),
        ("### Pre Chorus", "pre-chorus"),
    ],
)
def test_recognizes_common_header_forms(header: str, tag: str) -> None:
    lyrics = songs.normalize_lyrics(f"{header}\nA line to sing")
    assert lyrics == f"[intro]\n\n[{tag}]\nA line to sing"


def test_repeat_marks_are_dropped() -> None:
    lyrics = songs.normalize_lyrics(
        "[verse]\nWindows down (x2)\nRadio on [x3]\n\n(Repeat chorus)\n[Repeat Chorus]\nx2\n[chorus]\nKeep it free"
    )
    assert sung_lines(lyrics) == ["Windows down", "Radio on", "Keep it free"]


@pytest.mark.parametrize(
    "line",
    [
        "Chorus of angels singing",
        "Hook, line and sinker",
        "Bridge over the water",
        "Verse 1: the windows down",
        "Outro of the night we had",
        "Tonight",
        "(oh-oh)",
    ],
)
def test_lyric_lines_starting_with_a_section_word_are_kept(line: str) -> None:
    assert sung_lines(songs.normalize_lyrics(f"[verse]\n{line}")) == [line]


def test_lyric_lines_that_look_like_words_are_kept() -> None:
    lyrics = songs.normalize_lyrics("[verse]\nChorus of angels singing\nTonight\n(oh-oh)\n[chorus]\nHold on")
    assert sung_lines(lyrics) == ["Chorus of angels singing", "Tonight", "(oh-oh)", "Hold on"]


def test_adds_intro_when_missing() -> None:
    lyrics = songs.normalize_lyrics("[verse]\nWindows down\n[chorus]\nKeep it free")
    assert tags(lyrics) == ["intro", "verse", "chorus"]
    assert lyrics.startswith("[intro]\n\n[verse]\n")


def test_intro_stays_instrumental() -> None:
    lyrics = songs.normalize_lyrics("[Intro]\nOoh yeah\n[verse]\nWindows down\n[chorus]\nKeep it free")
    assert lyrics.startswith("[intro]\n\n[verse]\nWindows down")
    assert "Ooh yeah" not in lyrics


def test_lines_before_the_first_tag_become_a_verse() -> None:
    lyrics = songs.normalize_lyrics("Windows down\nRadio on\n[chorus]\nKeep it free")
    assert tags(lyrics) == ["intro", "verse", "chorus"]
    assert sung_lines(lyrics) == ["Windows down", "Radio on", "Keep it free"]


def test_empty_sections_are_dropped() -> None:
    lyrics = songs.normalize_lyrics("[verse]\nWindows down\n[chorus]\n\n[bridge]\n[outro]\nGoodbye")
    assert tags(lyrics) == ["intro", "verse", "outro"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Open Road"', "Open Road"),
        ("**Neon Rain**", "Neon Rain"),
        ("Title: Night Bus", "Night Bus"),
        ("  Low   Tide \n(instrumental)", "Low Tide"),
        ("'Paper Moons.'", "Paper Moons"),
        ("# Summer Static", "Summer Static"),
    ],
)
def test_cleans_title(raw: str, expected: str) -> None:
    assert songs.clean_title(raw) == expected


def test_long_title_is_capped_at_a_word_boundary() -> None:
    title = songs.clean_title("A Very Long Title " * 10)
    assert 0 < len(title) <= songs.MAX_TITLE_CHARS
    assert title.startswith("A Very Long Title A Very")
    assert title.split()[-1] in {"A", "Very", "Long", "Title"}  # never cut mid-word


def test_title_without_spaces_is_hard_capped() -> None:
    assert songs.clean_title("A" * 100) == "A" * songs.MAX_TITLE_CHARS


# ---- write_song_text with a mocked Qwen ----------------------------------------------------------


@respx.mock
def test_vocal_uses_lyrics_prompt_and_returns_song_text(qwen_client: QwenClient) -> None:
    route = respx.post(URL).respond(
        200, json=qwen_reply(json.dumps({"title": "Open Road", "lyrics": GOOD_LYRICS}))
    )
    song = songs.write_song_text(
        style="synth-pop", mood="upbeat", theme="road trip", duration_s=30, vocal=True
    )
    assert song == SongText("Open Road", GOOD_LYRICS)
    assert route.call_count == 1
    system, user = (m["content"] for m in sent_messages(route))
    assert system == songs.load_prompt("lyrics").system.strip()
    assert "road trip" in user and "[verse]" in user
    body = json.loads(route.calls[0].request.content)
    assert body["max_tokens"] == songs.LYRICS_MAX_TOKENS
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


@respx.mock
def test_instrumental_uses_title_prompt_and_no_lyrics(qwen_client: QwenClient) -> None:
    route = respx.post(URL).respond(200, json=qwen_reply('{"title": "Low Tide"}'))
    song = songs.write_song_text(style="lo-fi", mood="mellow", theme=None, duration_s=60, vocal=False)
    assert song == SongText("Low Tide", None)
    assert route.call_count == 1
    system, user = (m["content"] for m in sent_messages(route))
    assert system == songs.load_prompt("title").system.strip()
    assert "[verse]" not in user
    assert json.loads(route.calls[0].request.content)["max_tokens"] == songs.TITLE_MAX_TOKENS


@respx.mock
def test_qwen_failure_propagates_as_service_error(qwen_client: QwenClient) -> None:
    respx.post(URL).respond(503)
    with pytest.raises(ServiceError) as caught:
        songs.write_song_text(style="pop", mood="upbeat", theme=None, duration_s=30, vocal=True)
    assert caught.value.service == "qwen"
    assert caught.value.kind == "unavailable"


@respx.mock
def test_unusable_qwen_reply_is_bad_response(qwen_client: QwenClient) -> None:
    respx.post(URL).respond(200, json=qwen_reply("I'd rather not write lyrics today."))
    with pytest.raises(ServiceError) as caught:
        songs.write_song_text(style="pop", mood="upbeat", theme=None, duration_s=30, vocal=True)
    assert caught.value.kind == "bad_response"


def test_songs_module_uses_only_allowed_clients() -> None:
    """PROJECT.md 7.0: songs may use the Qwen and ACE-Step clients and no other model code."""
    tree = ast.parse(SONGS_PY.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            if node.module == "jukebox.clients":
                imported.update(f"jukebox.clients.{alias.name}" for alias in node.names)
    clients = {name for name in imported if name.startswith("jukebox.clients.")}
    assert clients <= {"jukebox.clients.qwen", "jukebox.clients.acestep"}
    assert not any(name.split(".")[0] in {"httpx", "requests", "urllib"} for name in imported)
