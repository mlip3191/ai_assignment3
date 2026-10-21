"""Tests for the real-artist safeguard in jukebox/services/songs.py (task B8, PROJECT.md 8.1, H10).

Style or theme text that points at a real artist ("in the style of <name>", "sounds like <name>",
"<Name>-esque") is removed before anything reaches Qwen or ACE-Step, and the UI can show why.
Qwen and ACE-Step are mocked with respx through the real clients.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.acestep as acestep  # noqa: E402
import jukebox.clients.qwen as qwen  # noqa: E402
import jukebox.services.songs as songs  # noqa: E402
from jukebox.clients.acestep import AceStepClient  # noqa: E402
from jukebox.clients.qwen import QwenClient  # noqa: E402
from jukebox.config import load_config  # noqa: E402
from jukebox.jobs import JobStore  # noqa: E402
from jukebox.library import Library  # noqa: E402

HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
QWEN_URL = f"http://{HOST}:9001/v1/chat/completions"
ACE = f"http://{HOST}:9007"


# ---- check_style: what gets removed ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("upbeat pop in the style of Taylor Swift", "upbeat pop", ["in the style of Taylor Swift"]),
        (
            "synth-pop, in the style of Daft Punk, warm pads",
            "synth-pop, warm pads",
            ["in the style of Daft Punk"],
        ),
        ("in the style of taylor swift", "", ["in the style of taylor swift"]),
        ("in the style of the beatles", "", ["in the style of the beatles"]),
        ("in the style of taylor swift pop", "pop", ["in the style of taylor swift"]),
    ],
)
def test_in_the_style_of_a_name_is_removed(raw: str, cleaned: str, removed: list[str]) -> None:
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == removed


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("sounds like Radiohead", "", "sounds like Radiohead"),
        ("indie rock inspired by Arctic Monkeys", "indie rock", "inspired by Arctic Monkeys"),
        ("influenced by Miles Davis, jazz", "jazz", "influenced by Miles Davis"),
        ("reminiscent of The Beatles", "", "reminiscent of The Beatles"),
        ("anthemic, similar to Coldplay", "anthemic", "similar to Coldplay"),
        ("à la Prince funk", "funk", "à la Prince"),
        ("Sounds Like Nirvana, grunge", "grunge", "Sounds Like Nirvana"),
        ("in the vein of Fleetwood Mac", "", "in the vein of Fleetwood Mac"),
    ],
)
def test_other_pointer_phrases_are_removed(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == [removed]


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("Beatles-esque harmonies", "harmonies", "Beatles-esque"),
        ("Taylor Swift style pop", "pop", "Taylor Swift style"),
        ("rock, Nirvana-inspired guitars", "rock, guitars", "Nirvana-inspired"),
        ("Daft Punk-style house", "house", "Daft Punk-style"),
    ],
)
def test_capitalized_name_style_and_esque_are_removed(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == [removed]


def test_like_with_a_name_is_removed_but_like_a_lowercase_phrase_stays() -> None:
    result = songs.check_style("pop like Dua Lipa, bright")
    assert (result.text, list(result.removed)) == ("pop, bright", ["like Dua Lipa"])
    for ordinary in ("dreamy like a lullaby", "drums like thunder", "Like a dream, ambient"):
        assert songs.check_style(ordinary).text == ordinary
        assert songs.check_style(ordinary).removed == ()


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("in the style of 80s synthwave", "80s synthwave"),
        ("in the style of Latin jazz", "Latin jazz"),
        ("inspired by lo-fi hip hop, rainy", "lo-fi hip hop, rainy"),
        ("sounds like K-Pop", "K-Pop"),
        ("Latin style percussion", "Latin style percussion"),
        ("Retro style synths", "Retro style synths"),
    ],
)
def test_genres_after_a_pointer_phrase_are_kept(raw: str, cleaned: str) -> None:
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert result.removed == ()


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("in the style of southern rock", "southern rock"),
        ("in the style of trip hop", "trip hop"),
        ("inspired by bedroom pop", "bedroom pop"),
        ("sounds like yacht rock", "yacht rock"),
        ("in the style of video game music", "video game music"),
        ("inspired by rainy nights", "rainy nights"),
        ("in the spirit of summer", "summer"),
        ("sounds like a movie soundtrack", "sounds like a movie soundtrack"),
        ("in the style of a lullaby", "in the style of a lullaby"),
        ("a love song inspired by my grandmother", "a love song inspired by my grandmother"),
    ],
)
def test_descriptive_phrases_after_a_pointer_are_kept(raw: str, cleaned: str) -> None:
    """Review finding: ordinary lowercase descriptions were cut short or refused as artist names."""
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert result.removed == ()


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("in the style of Detroit techno", "Detroit techno"),
        ("sounds like Chicago house", "Chicago house"),
        ("in the style of UK garage", "UK garage"),
        ("inspired by French house", "French house"),
        ("in the style of Spanish guitar", "Spanish guitar"),
        ("in the style of Japanese city pop", "Japanese city pop"),
        ("in the style of Nashville country", "Nashville country"),
        ("in the style of Neo-Soul", "Neo-Soul"),
        ("sounds like Christmas", "Christmas"),
        ("Western-style guitar", "Western-style guitar"),
        ("Spaghetti Western style", "Spaghetti Western style"),
        ("in the style of New Orleans jazz", "New Orleans jazz"),
    ],
)
def test_places_and_capitalized_genres_are_kept(raw: str, cleaned: str) -> None:
    """Review finding: places, nationalities and capitalized genres were treated as names."""
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert result.removed == ()


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("in the style of AC/DC, rock", "rock", "in the style of AC/DC"),
        ("rock in the style of Adele or Drake", "rock", "in the style of Adele or Drake"),
        ("in the style of Lady Gaga/Madonna", "", "in the style of Lady Gaga/Madonna"),
        ("in the style of Earth, Wind & Fire", "", "in the style of Earth, Wind & Fire"),
        ("in the style of Ed Sheeran and pop", "pop", "in the style of Ed Sheeran"),
    ],
)
def test_joined_and_listed_names_are_removed_whole(raw: str, cleaned: str, removed: str) -> None:
    """Review finding: names joined by "/", "or", "and" or a comma leaked through."""
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == [removed]


def test_a_name_followed_by_an_ordinary_part_keeps_that_part() -> None:
    """Re-review finding: title-case tags after a name were eaten as part of it."""
    assert songs.check_style("in the style of Adele, Warm pads").text == "Warm pads"
    assert songs.check_style("in the style of Adele, Lo-Fi").text == "Lo-Fi"
    assert songs.check_style("in the style of Adele, Female Vocals").text == "Female Vocals"
    assert songs.check_style("in the style of Adele, Heartfelt").text == "Heartfelt"


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("in the style of a Taylor Swift song", "", "in the style of a Taylor Swift song"),
        ("upbeat, sounds like a Coldplay ballad", "upbeat", "sounds like a Coldplay ballad"),
        ("in the style of an Adele ballad, piano", "piano", "in the style of an Adele ballad"),
        ("sounds like that Daft Punk album", "", "sounds like that Daft Punk album"),
        ("inspired by my favorite band Radiohead", "", "inspired by my favorite band Radiohead"),
        ("sounds like a mix of Adele and Drake", "", "sounds like a mix of Adele and Drake"),
        ("upbeat pop like a Beyoncé anthem", "upbeat pop", "like a Beyoncé anthem"),
    ],
)
def test_a_description_that_names_an_artist_is_removed(raw: str, cleaned: str, removed: str) -> None:
    """Re-review finding: "a/my/that ..." descriptions were kept even when they named an artist."""
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == [removed]


def test_descriptions_with_only_sound_words_are_kept() -> None:
    for kept in ("sounds like a Christmas song", "dreamy like a lullaby", "sounds like a Sunday morning"):
        assert songs.check_style(kept).text == kept


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("a la carte jazz", "a la carte jazz", []),
        ("a la mode", "a la mode", []),
        ("a la Prince, funk", "funk", ["a la Prince"]),
    ],
)
def test_a_la_without_the_accent_needs_a_capitalized_name(raw: str, cleaned: str, removed: list[str]) -> None:
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, removed)


@pytest.mark.parametrize(
    "style",
    [
        "lo-fi hip hop, jazzy keys",
        "synth-pop",
        "country rock",
        "ambient electronic",
        "punk rock",
        "indie pop",
        "pop rock",
        "synth-pop, warm natural female vocals",
        "Latin jazz, upbeat",
        "80s synthwave, neon",
        "orchestral, cinematic strings",
        "drum and bass",
        "rock and roll",
    ],
)
def test_ordinary_styles_are_unchanged(style: str) -> None:
    result = songs.check_style(style)
    assert result.text == style
    assert result.removed == ()
    assert result.warning is None


def test_leftover_commas_and_spaces_are_tidied() -> None:
    result = songs.check_style(" , upbeat pop ,  in the style of Taylor Swift ,, , synths , ")
    assert result.text == "upbeat pop, synths"


def test_two_names_are_both_removed() -> None:
    result = songs.check_style("in the style of Adele, sounds like Drake, soul")
    assert result.text == "soul"
    assert list(result.removed) == ["in the style of Adele", "sounds like Drake"]


def test_blank_or_missing_text_is_left_alone() -> None:
    assert songs.check_style("").text == ""
    assert songs.check_style("   ").removed == ()


# ---- the warning the UI shows --------------------------------------------------------------------


def test_warning_names_what_was_removed_and_says_why() -> None:
    one = songs.check_style("pop in the style of Taylor Swift").warning
    assert one == "Removed “in the style of Taylor Swift”. Songs are original and never imitate real artists."
    two = songs.check_style("in the style of Adele, sounds like Drake, soul").warning
    assert two == (
        "Removed “in the style of Adele” and “sounds like Drake”. "
        "Songs are original and never imitate real artists."
    )


def test_no_warning_when_nothing_was_removed() -> None:
    assert songs.check_style("lo-fi hip hop").warning is None
    assert songs.check_style("in the style of 80s synthwave").warning is None


# ---- the prompts ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["lyrics", "title"])
def test_prompts_forbid_imitating_a_real_artists_style_or_voice(name: str) -> None:
    system = songs.load_prompt(name).system.lower()
    assert "imitate a real artist" in system
    assert "even if the request names one" in system
    assert "never quote" in system or "never use or imitate the title" in system


# ---- the pipeline --------------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    values = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in PORTS.items():
        values[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    config = load_config(env=values, env_file=tmp_path / "missing-file")
    q, a = QwenClient(config, sleep=lambda _s: None), AceStepClient(config, sleep=lambda _s: None)
    monkeypatch.setattr(qwen, "_default", q)
    monkeypatch.setattr(acestep, "_default", a)
    yield {"library": Library(root=tmp_path), "jobs": JobStore()}
    q.close()
    a.close()


def mock_services() -> tuple[respx.Route, respx.Route]:
    lyrics = "[intro]\n\n[verse]\nWindows down\nRadio on\n\n[chorus]\nKeep it free"
    qwen_route = respx.post(QWEN_URL).respond(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"title": "Open Road", "lyrics": lyrics}),
                    },
                    "finish_reason": "stop",
                }
            ]
        },
    )
    file_ref = f"/v1/audio?path={quote('/srv/acestep/a.mp3', safe='')}"
    result = json.dumps([{"file": file_ref, "dit_model": "acestep-v15-xl-turbo"}])
    submit = respx.post(f"{ACE}/release_task").respond(200, json={"data": {"task_id": "t1"}})
    respx.post(f"{ACE}/query_result").respond(
        200, json={"data": [{"task_id": "t1", "status": 1, "result": result}]}
    )
    respx.get(url__startswith=f"{ACE}/v1/audio").respond(200, content=b"ID3fake" * 10)
    return qwen_route, submit


def run(env: dict, **song) -> list:
    args = {"mood": "upbeat", "duration_s": 30, "vocal": True, **song}
    return list(songs.generate_song(**args, library=env["library"], jobs=env["jobs"]))


@respx.mock
def test_pipeline_sends_cleaned_tags_and_prompts(env: dict) -> None:
    qwen_route, submit = mock_services()
    updates = run(
        env, style="upbeat pop in the style of Taylor Swift", theme="a road trip like Thelma & Louise"
    )
    assert updates[-1].status == "succeeded"
    tags = json.loads(submit.calls[0].request.content)["prompt"]
    assert tags == "upbeat pop, upbeat, warm natural vocals"
    sent = json.dumps(json.loads(qwen_route.calls[0].request.content)["messages"])
    assert "Taylor" not in sent and "Swift" not in sent and "Thelma" not in sent


@respx.mock
def test_pipeline_stores_the_cleaned_style_and_theme(env: dict) -> None:
    mock_services()
    track_id = run(env, style="indie rock, sounds like Radiohead", theme="rainy city, in the style of Adele")[
        -1
    ].track_id
    track = env["library"].get(track_id)
    assert (track.style, track.theme) == ("indie rock", "rainy city")


@respx.mock
def test_style_that_was_only_an_artist_is_refused_before_any_call(env: dict) -> None:
    qwen_route, submit = mock_services()
    updates = run(env, style="in the style of Taylor Swift")
    assert [u.status for u in updates] == ["queued", "failed"]
    assert updates[-1].error == (
        "ACE-Step couldn't process that request: Describe the style without naming real artists."
    )
    assert qwen_route.call_count == 0 and submit.call_count == 0


@respx.mock
def test_theme_that_was_only_an_artist_becomes_no_theme(env: dict) -> None:
    mock_services()
    track_id = run(env, style="pop", theme="sounds like Adele")[-1].track_id
    assert env["library"].get(track_id).theme is None
