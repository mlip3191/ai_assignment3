"""Tests for the cover-art prompt builder in jukebox/services/art.py (task C3).

Qwen is mocked: most tests pass a fake `chat(messages, *, max_tokens, temperature) -> str` matching
PROJECT.md 7.2, and one checks the default path really calls `jukebox.clients.qwen.chat` (B3) with
those arguments. No class service is ever called.
"""

from __future__ import annotations

import sys
import time
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


def test_template_system_rules_forbid_text_real_people_clear_faces_and_real_artists() -> None:
    system = art.load_template().system.lower()
    rules = ("text", "real artists", "real person", "original", "faces in shadow", "clearly drawn face")
    for phrase in rules:
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


def test_by_default_the_real_qwen_client_writes_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from jukebox.clients import qwen

    calls: list[dict] = []

    def recording_chat(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        return "A misty harbor at dawn"

    monkeypatch.setattr(qwen, "chat", recording_chat)
    prompt = art.write_cover_prompt(**POP)
    assert prompt == f"A misty harbor at dawn, {SUFFIX}"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == art.MAX_TOKENS == 300
    assert calls[0]["temperature"] == art.TEMPERATURE == 0.8
    assert [m["role"] for m in calls[0]["messages"]] == ["system", "user"]
    assert "Windows Down" in calls[0]["messages"][-1]["content"]


# ---- review nits from #33 (@gunnaroc) ---------------------------------------------------------


def test_the_lyrics_excerpt_skips_section_tags_and_blank_lines() -> None:
    song = dict(
        POP, lyrics="[intro]\n\n[verse]\nSun on the dashboard\nWheels on the road\n\n[chorus]\nWindows down"
    )
    excerpt = art.build_messages(**song)[1]["content"].split("Lyrics (excerpt):", 1)[1]
    assert "[" not in excerpt
    assert "\n\n" not in excerpt.strip()
    assert "Sun on the dashboard\nWheels on the road\nWindows down" in excerpt


def test_a_long_excerpt_is_cut_at_a_word_boundary() -> None:
    song = dict(POP, lyrics="[verse]\n" + " ".join(["wonderful"] * 200))
    excerpt = art.build_messages(**song)[1]["content"].split("Lyrics (excerpt):", 1)[1].strip()
    assert len(excerpt) <= art.LYRICS_EXCERPT_CHARS
    assert excerpt.split()[-1] == "wonderful"


@pytest.mark.parametrize(
    "reply",
    [
        'Here is your prompt: "A sunlit field at golden hour"',
        "Here's the image prompt: A sunlit field at golden hour",
        "Sure! Here is the prompt: 'A sunlit field at golden hour.'",
    ],
)
def test_a_chatty_lead_in_is_removed(reply: str) -> None:
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply=reply))
    assert prompt == f"A sunlit field at golden hour, {SUFFIX}"


def test_a_colon_inside_a_real_prompt_is_kept() -> None:
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply="A quiet room: soft lamp light"))
    assert prompt == f"A quiet room: soft lamp light, {SUFFIX}"


def test_an_unmatched_quote_inside_the_prompt_is_kept() -> None:
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply='A sign that reads nothing, a "quiet street'))
    assert prompt == f'A sign that reads nothing, a "quiet street, {SUFFIX}'


# ---- people on covers: small, backlit, faces not defined (TC-04 dry run, 10/24) ----------------
# A cover showed two front-facing, recognizable faces and a man with three arms. People may stay in a
# scene, but drawn so faces aren't defined and hands aren't prominent (where FLUX's mistakes show).


class ScriptedQwen:
    """Answers each call with the next scripted reply and records the messages it got."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        self.calls.append(messages)
        return self.replies.pop(0)


def test_a_prompt_without_people_is_left_as_written() -> None:
    chat = ScriptedQwen("An empty convertible on a coast road at sunset, warm golden light")
    prompt = art.write_cover_prompt(**POP, chat=chat)
    assert prompt == f"An empty convertible on a coast road at sunset, warm golden light, {SUFFIX}"
    assert art.SOFT_PEOPLE not in prompt


def test_people_stay_but_get_the_soft_figure_style_in_one_call() -> None:
    chat = ScriptedQwen("Two friends stand in a convertible with their arms raised at sunset")
    prompt = art.write_cover_prompt(**POP, chat=chat)
    assert len(chat.calls) == 1  # no extra Qwen call
    assert prompt == (
        f"Two friends stand in a convertible with their arms raised at sunset, {art.SOFT_PEOPLE}, {SUFFIX}"
    )


def test_the_soft_figure_style_is_added_once_and_before_the_suffix() -> None:
    reply = f"A crowd at a summer concert, {art.SOFT_PEOPLE}. {SUFFIX}."
    prompt = art.write_cover_prompt(**POP, chat=ScriptedQwen(reply))
    assert prompt.count(art.SOFT_PEOPLE) == 1 and prompt.count(SUFFIX) == 1
    assert prompt.endswith(f"{art.SOFT_PEOPLE}, {SUFFIX}")


def test_an_echoed_style_line_in_the_middle_or_capitalised_is_not_doubled() -> None:
    style = art.SOFT_PEOPLE
    reply = f"A crowd at a summer concert, {style[0].upper()}{style[1:]}, warm amber light"
    prompt = art.write_cover_prompt(**POP, chat=ScriptedQwen(reply))
    assert prompt.lower().count(style.lower()) == 1
    assert ", ," not in prompt
    assert prompt == f"A crowd at a summer concert, warm amber light, {style}, {SUFFIX}"


def test_the_soft_figure_style_asks_for_undefined_faces_and_hands_out_of_focus() -> None:
    style = art.SOFT_PEOPLE.lower()
    for phrase in ("only as many people as described", "backlit", "faces in shadow", "not detailed", "hands"):
        assert phrase in style
    assert "small in the frame" not in style  # it made FLUX fill a road trip with a crowd (10/24)


def test_the_template_keeps_people_soft_and_never_a_portrait() -> None:
    system = art.load_template().system.lower()
    for phrase in ("only as many people as the scene needs", "faces", "never a close-up"):
        assert phrase in system


@pytest.mark.parametrize(
    "text",
    [
        "Two friends in a car",
        "a woman reading",
        "A MAN on a pier",
        "children playing",
        "a crowd cheering",
        "hands raised to the sky",
        "a lone figure at the gate",
        "a smiling face in the window",
        "dancers under neon",
        "a couple on a bench",
        "a person walking",
        "people on the street",
        "a girl with a kite",
        "the driver waves",
        "the audience in the dark",
        "a guitarist on stage",
        "a drummer behind the kit",
        "a DJ at the decks",
        "a stranger at the station",
        "a lone wanderer",
        "a sailor at the rail",
        "a cyclist on the bridge",
        "skaters in the park",
        "a mother and daughter",
        "eyes closed in the rain",
        "fingers on the keys",
        "bare feet in the sand",
        # missed before Mike's review of #58 (10/25)
        "a fisherman at dawn",
        "an astronaut floating above the earth",
        "a cowboy on a ridge",
        "soldiers marching home",
        "a pilot in the cockpit",
        "a bride in the doorway",
        "a farmer in the field",
        "a baby asleep in a crib",
        "a gentleman in a long coat",
        "a policeman under a streetlight",
        "pedestrians crossing in the rain",
        "a biker on a desert highway",
        "workers on a night shift",
        "a barista behind the counter",
        "a rider on a white horse",
        "shoulders wet with rain",
        "heads bowed in the rain",
        "everyone dancing on the roof",
        "a horseman on the plain",
        "a policewoman at the corner",
        "the silhouette of a man on the hill",
        "a lone human under the stars",
        "humans on a distant shore",
        "spectators in the stands",
        "tourists at the pier",
        "her girlfriend laughing",
        "a sleepy toddler",
        "the hands of a pianist on the keys",
        "an empty street, no people but a lone fisherman",
        # missed in the review agent's check of #58 (10/26)
        "a saxophonist in a smoky club",
        "a trumpeter under a streetlight",
        "a vocalist at the microphone",
        "a performer on a bare stage",
        "a rock band playing on stage",
        "fans cheering at the barrier",
        "concertgoers in the rain",
        "partygoers on a rooftop",
        "ravers under strobe lights",
        "a teenager on a skateboard",
        "a lover waiting at the station",
        "swimmers in a moonlit lake",
        "a monk on a mountain path",
        "a ballerina in the spotlight",
        "a couple of friends on a rooftop",
        "two distant silhouettes on the shore",
        # a "no" list must not swallow the people after it (second review of #58, 10/26)
        "a quiet beach with no crowds, figures far in the distance",
        "no crowds, people dancing in the windows above",
        "no faces, hands on the piano keys",
    ],
)
def test_people_are_noticed(text: str) -> None:
    assert art.mentions_people(text)


@pytest.mark.parametrize(
    "text",
    [
        "An empty convertible on a coast road",
        "a rainy window with a steaming mug",
        "a manmade lake at dusk",
        "a humming neon sign, no letters",
        "a figurehead-free wooden boat",
        "the hands of a clock tower",
        "the arms of an old chair",
        "the body of the guitar",
        "a still body of water",
        "the face of the cliff",
        "the face of a clock",
        "a hand-painted sign",
        "a figure-eight road",
        "the man in the moon",
        "the foot of the hill",
        # flagged before Mike's review of #58 (10/25)
        "the silhouette of a mountain range",
        "palm trees in silhouette against the sunset",
        "clock hands pointing to midnight",
        "the minute hand of a station clock",
        "a runner of red carpet",
        "a table runner with candles",
        "a figure of speech painted on a wall",
        "guy ropes on a tent",
        # words that end in "man" or "men" but are not people
        "a German shepherd on the porch",
        "a velvet ottoman by the fire",
        "a snowman in the yard",
        "a silver talisman on a chain",
        "Roman columns at dusk",
        "a bowl of ramen",
        "a dark omen in the sky",
        "a stone dolmen on the moor",
        "a museum specimen jar",
        "pink cyclamen on a sill",
        # other things that only sound like people
        "a baby blue sky",
        "a pedestrian bridge at night",
        "a pilot light glowing blue",
        "a cowboy hat on a fence post",
        "the head of the river",
        "the road heads west",
        "an empty street with no people",
        "a beach without any people",
        "a desert devoid of people",
        "a quiet room, no figures, no faces",
        # flagged in the review agent's check of #58 (10/26)
        "a couple of candles flickering on a windowsill",
        "palm tree silhouettes against an orange sky",
        "the city skyline silhouette at dusk",
        "pines as dark silhouettes",
        "a cliff face at sunset",
        "a clock face reading midnight",
        "an empty street, no human figures",
        "a bare stage, no people or figures",
        "a still life, no faces or hands",
        "a beach without a single person",
        "a coat of arms on an old gate",
        "a crowd of seagulls over the harbor",
        "no man's land at dawn",
        "the Isle of Man at dusk",
        "an old Pullman carriage",
        "the Tasman Sea at night",
        "a pilot whale breaching",
        "sled runners in fresh snow",
        "table legs carved like vines",
        "an abandoned DJ booth",
        "a rubber band on a desk",
        "a ceiling fan turning slowly",
        "a skyline, the silhouette softened by fog",
        "a metal band around the barrel",
        "a Pac-Man arcade cabinet",
        "no man’s land at dawn",
    ],
)
def test_scenes_without_people_are_left_alone(text: str) -> None:
    assert not art.mentions_people(text)


# The three committed sample cover prompts (samples/manifest.json, written by Qwen on 10/24), shortened.
SAMPLE_PROMPTS = {
    "A cluttered desk bathed in dim blue twilight, featuring an open notebook with fading ink and a steaming "
    "mug. Soft rain streaks the window behind, square album cover, no text, no letters, no logos, "
    "no real people": False,
    "A vintage convertible speeds along a coastal highway, bathed in golden hour sunlight. Two distant "
    "silhouettes sit inside with windows down, arms raised joyfully toward the sky": True,
    "A lone silhouette stands before a weathered wooden gate in twilight, back turned to the viewer": True,
}


@pytest.mark.parametrize(("text", "has_people"), SAMPLE_PROMPTS.items())
def test_the_sample_cover_prompts_are_read_correctly(text: str, has_people: bool) -> None:
    assert art.mentions_people(text) is has_people


def test_long_runs_of_spaces_after_no_people_stay_fast() -> None:
    start = time.perf_counter()
    assert not art.mentions_people("no people" + " " * 5000 + "a quiet sky")
    assert time.perf_counter() - start < 1


def test_an_empty_landscape_reply_gets_no_soft_figure_style() -> None:
    reply = "A desert at night under a sky full of stars, no people, dunes in silhouette, film photograph"
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply=reply))
    assert art.SOFT_PEOPLE not in prompt
    assert prompt == f"{reply}, {SUFFIX}"


def test_a_fisherman_reply_gets_the_soft_figure_style() -> None:
    prompt = art.write_cover_prompt(**LOFI, chat=FakeQwen(reply="A fisherman at dawn on a misty lake"))
    assert prompt == f"A fisherman at dawn on a misty lake, {art.SOFT_PEOPLE}, {SUFFIX}"
