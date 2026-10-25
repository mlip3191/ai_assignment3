"""Tests for the real-artist safeguard in jukebox/services/songs.py (task B8, PROJECT.md 8.1, H10).

Style or theme text that points at a real artist ("in the style of <name>", "sounds like <name>",
"<Name>-esque") is removed before anything reaches Qwen or ACE-Step, and the UI can show why.
Qwen and ACE-Step are mocked with respx through the real clients.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from urllib.parse import quote

import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.acestep as acestep  # noqa: E402
import jukebox.clients.qwen as qwen  # noqa: E402
import jukebox.services.art as art  # noqa: E402
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
        ("IN THE STYLE OF TAYLOR SWIFT, pop", "pop", ["IN THE STYLE OF TAYLOR SWIFT"]),
    ],
)
def test_in_the_style_of_a_name_is_removed(raw: str, cleaned: str, removed: list[str]) -> None:
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == removed


@pytest.mark.parametrize(
    "raw",
    ["in the style of taylor swift", "in the style of the beatles", "rock like taylor swift"],
)
def test_lowercase_names_are_a_known_limit(raw: str) -> None:
    """Reviews of #38: lowercase words after a pointer were removed as names, which also removed real
    descriptions ("inspired by the sea"). Only capitalized names count now; this is listed in B9."""
    assert songs.check_style(raw).text == raw


@pytest.mark.parametrize(
    "raw",
    ["a breakup song in the style of adele", "a song that sounds like drake", "a road trip à la prince"],
)
def test_lowercase_names_are_a_known_limit_in_song_idea_too(raw: str) -> None:
    """#56 review: the Song idea screen has the same rule, so the help text says names need a capital."""
    result = songs.check_theme(raw)
    assert (result.text, result.warning) == (raw, None)


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


# ---- review round on #38 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "inspired by the sea",
        "sounds like rain",
        "in the style of ocean waves",
        "inspired by nature, calm",
        "reminiscent of the 90s",
        "à la mode pop",
        "metal à la mode",
    ],
)
def test_lowercase_descriptions_after_a_pointer_are_kept(raw: str) -> None:
    result = songs.check_style(raw)
    assert result.text == raw
    assert result.removed == ()


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("pop, Adele's voice", "pop", "Adele's voice"),
        ("pop, Adele’s vocals", "pop", "Adele’s vocals"),
        ("Taylor Swift's sound", "", "Taylor Swift's sound"),
        ("rock with Bono's style", "rock with", "Bono's style"),
    ],
)
def test_possessive_names_are_removed(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


def test_a_removed_possessive_voice_brings_back_the_default_voice_tag() -> None:
    """Reviews of #38: "pop, Adele's voice" left Adele as the only voice ACE-Step was given."""
    style = songs.check_style("pop, Adele's voice").text
    assert songs.build_tags(style, "joyful", vocal=True) == "pop, joyful, warm natural vocals"


def test_genre_possessives_are_kept() -> None:
    assert songs.check_style("Motown's sound").text == "Motown's sound"


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("pop, by Drake", "pop", "by Drake"),
        ("hip hop featuring Eminem", "hip hop", "featuring Eminem"),
        ("rap, feat. Nicki Minaj", "rap", "feat. Nicki Minaj"),
        ("in the manner of Bob Dylan, folk", "folk", "in the manner of Bob Dylan"),
        ("soul with the voice of Aretha Franklin", "soul with", "the voice of Aretha Franklin"),
        ("pop (like Adele)", "pop", "like Adele"),
    ],
)
def test_more_ways_of_naming_an_artist_are_removed(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


@pytest.mark.parametrize(
    "raw",
    [
        "backed by strings",
        "lit by candlelight",
        "sounds like Motown",
        "inspired by Brazil",
        "Latin vibe",
        "summer vibes",
        "Friday vibes",
        "Chill-ish lo-fi",
    ],
)
def test_the_new_patterns_keep_ordinary_text(raw: str) -> None:
    result = songs.check_style(raw)
    assert result.removed == ()


@pytest.mark.parametrize(
    "raw",
    [
        "Beach vibes",
        "Good vibes",
        "Tropical vibes",
        "Island vibes",
        "Halloween vibes",
        "Neon vibes",
        "Phonk vibe",
        "Afro vibe",
        "Dancehall vibes",
        "Nu Metal vibe",
        "Cozy vibes, warm piano",
        "Boom Bap type beat",
        "Trap type beat",
        "Hyperpop-ish",
        "Summer's sound",
        "folk by the Sea",
        "Lullaby by Moonlight",
        "Played by Ear",
        "Made by Hand",
        "Driven By Drums",
        "pop backed by Strings",
        "Piano by Night",
        "pop ft. Heavy Bass",
        "rock featuring Guitar Solos",
        "Dreamy music, Heavy bass",
        "Deep House vibes",
        "Golden Hour vibes",
        "Late Night Drive vibes",
        "Sad Girl vibes",
        "Workout type beat",
        "Club Banger type beat",
        "Cottagecore-ish",
        "Tiki-ish lounge",
        "Forest-like ambience",
        "song by Candlelight",
        "music by Fire",
        "Christmas song by the Fireplace",
        "Heavy Guitars ft. Big Drums",
    ],
)
def test_capitalized_ordinary_styles_come_back_unchanged(raw: str) -> None:
    """Re-review of #38: capitalized everyday words were refused or cut as artist names."""
    result = songs.check_style(raw)
    assert (result.text, result.removed) == (raw, ())


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("pop, sung by Adele", "pop", "sung by Adele"),
        ("rock, produced by Rick Rubin", "rock", "produced by Rick Rubin"),
        ("hip hop ft Drake", "hip hop", "ft Drake"),
        ("hip hop feat Drake", "hip hop", "feat Drake"),
    ],
)
def test_name_forms_that_still_count(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


# ---- narrowed after the re-review: explicit forms only ---------------------------------------------


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("in the style of Adele, Drake", "", "in the style of Adele, Drake"),
        ("in the style of Beyoncé, Rihanna", "", "in the style of Beyoncé, Rihanna"),
        ("in the style of Adele, Drake, soul", "soul", "in the style of Adele, Drake"),
    ],
)
def test_names_listed_after_a_removed_name_are_removed_too(raw: str, cleaned: str, removed: str) -> None:
    """Mike's review of #38: listing several artists is the natural way to write this."""
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


@pytest.mark.parametrize(
    "tag",
    [
        "Warm Pads",
        "Big Chorus",
        "Slow Tempo",
        "Rainy Day",
        "Road Trip",
        "Catchy Hooks",
        "Reverb",
        "Sad",
        "Happy",
        "Driving Beat",
        "Deep Bass",
        "Fast",
        "Soft Piano",
        "Female Vocals",
    ],
)
def test_capitalized_tags_after_a_removed_name_are_kept(tag: str) -> None:
    """Re-review of #38: the list rule ate everyday tags after an artist, and could refuse the style."""
    result = songs.check_style(f"in the style of Adele, {tag}")
    assert (result.text, list(result.removed)) == (tag, ["in the style of Adele"])


def test_the_list_rule_stops_at_the_first_ordinary_tag() -> None:
    result = songs.check_style("in the style of Adele, Drake, Warm Pads, Big Chorus, pop")
    assert (result.text, list(result.removed)) == (
        "Warm Pads, Big Chorus, pop",
        ["in the style of Adele, Drake"],
    )
    assert (
        songs.check_style("pop, sounds like Adele, Warm Pads, Soft Piano").text
        == "pop, Warm Pads, Soft Piano"
    )


def test_the_theme_has_no_list_rule() -> None:
    """Re-review of #38: "Grandma" after a removed name was eaten from the theme."""
    result = songs.check_theme("a road trip, sounds like Coldplay, Grandma, Paris in Spring")
    assert (result.text, list(result.removed)) == (
        "a road trip, Grandma, Paris in Spring",
        ["sounds like Coldplay"],
    )


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("jazz, vocals by Frank Sinatra", "jazz", "vocals by Frank Sinatra"),
        ("acoustic, cover of Elvis", "acoustic", "cover of Elvis"),
        ("rock, covers of Queen", "rock", "covers of Queen"),
        ("pop featuring Beyoncé", "pop", "featuring Beyoncé"),
        ("the voice of Morgan Freeman", "", "the voice of Morgan Freeman"),
    ],
)
def test_credit_and_cover_phrases_are_removed(raw: str, cleaned: str, removed: str) -> None:
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


@pytest.mark.parametrize(
    ("raw", "removed"),
    [
        ("in the style of Beach House", "in the style of Beach House"),
        ("in the style of Neon Indian", "in the style of Neon Indian"),
        ("sounds like Love", "sounds like Love"),
        ("sounds like Ocean", "sounds like Ocean"),
    ],
)
def test_names_made_of_everyday_words_are_caught(raw: str, removed: str) -> None:
    """Re-review of #38: over-general sound words let these real names through."""
    assert list(songs.check_style(raw).removed) == [removed]


@pytest.mark.parametrize(
    "raw",
    [
        "trap, Drake type beat",
        "indie, Arctic Monkeys vibe",
        "Taylor-Swift-like pop",
        "rock, Nirvana-ish",
        "a song by Drake",
    ],
)
def test_loose_name_forms_are_a_known_limit(raw: str) -> None:
    """Narrowed after the re-review: a pattern can't tell "Golden Hour vibes" from "Arctic Monkeys vibe",
    so "vibe", "type beat", "-ish", "-like" and "song by" aren't screened. Listed in B9."""
    assert songs.check_style(raw).text == raw


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("in the style of A$AP Rocky", "", "in the style of A$AP Rocky"),
        ("sounds like Ke$ha", "", "sounds like Ke$ha"),
        ("pop, Ty Dolla $ign style", "pop", "Ty Dolla $ign style"),
        ("trap, inspired by $uicideboy$", "trap", "inspired by $uicideboy$"),
        ("hip hop, A$AP Rocky's flow", "hip hop, A$AP Rocky's flow", None),  # "flow" isn't an owner word
    ],
)
def test_names_with_a_dollar_sign_are_removed_whole(raw: str, cleaned: str, removed: str | None) -> None:
    """Mike's review of #48: "in the style of A$AP Rocky" left "$AP Rocky" in the style sent to the models."""
    result = songs.check_style(raw)
    assert result.text == cleaned
    assert list(result.removed) == ([removed] if removed else [])
    assert "$" not in result.text or removed is None


@pytest.mark.parametrize(
    ("raw", "cleaned", "removed"),
    [
        ("trap ft $uicideboy$", "trap", "ft $uicideboy$"),
        ("pop feat $uicideboy$", "pop", "feat $uicideboy$"),
        ("a la $uicideboy$", "", "a la $uicideboy$"),
    ],
)
def test_short_credits_catch_a_name_that_starts_with_a_dollar_sign(
    raw: str, cleaned: str, removed: str
) -> None:
    """Agent review of the "$" fix: "ft", "feat" and "a la" looked only for a capital letter."""
    result = songs.check_style(raw)
    assert (result.text, list(result.removed)) == (cleaned, [removed])


@pytest.mark.parametrize(
    "raw",
    [
        "pop, $100 bills",
        "lo-fi, cash money $",
        "trap, money $ign",
        "sounds like $ummer",
        "in the style of $ummer",
        "sounds like $unset",
        "inspired by $mall town vibes",
        "trap, $$$",
        "cash $tyle",
    ],
)
def test_ordinary_text_with_a_dollar_sign_is_unchanged(raw: str) -> None:
    """Agent review of the "$" fix: a word that only starts with "$" is an everyday word, not a name."""
    assert songs.check_style(raw).text == raw
    assert songs.check_theme(raw).text == raw


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("sounds like Detroit $ound", "Detroit $ound"),
        ("in the style of Detroit $ummer techno", "Detroit $ummer techno"),
        ("inspired by Paris $ummer", "Paris $ummer"),
        ("sounds like Summer $ad", "Summer $ad"),
    ],
)
def test_a_dollar_word_after_a_sound_word_keeps_the_phrase(raw: str, cleaned: str) -> None:
    """Second agent review of the "$" fix: "$ummer" after "Detroit" joined a "name", so the style was refused."""
    assert songs.check_style(raw).text == cleaned
    assert songs.check_theme(raw).text in (raw, cleaned)


def test_a_dollar_word_after_a_removed_name_is_kept() -> None:
    result = songs.check_style("in the style of Drake, $ad")
    assert (result.text, list(result.removed)) == ("$ad", ["in the style of Drake"])


def test_a_band_name_with_a_comma_is_a_known_limit() -> None:
    """Mike's nit on #48: the comma splits "Earth, Wind & Fire style", so "Earth" stays. Removing the part
    before a "<Name> style" part would also remove everyday tags ("Summer, Drake-style"). Listed in B9."""
    result = songs.check_style("Earth, Wind & Fire style")
    assert (result.text, list(result.removed)) == ("Earth", ["Wind & Fire style"])
    assert songs.check_style("Summer, Drake-style").text == "Summer"


@pytest.mark.parametrize("raw", ["Ocean's voice", "Life's music", "Today's sound"])
def test_possessives_of_everyday_words_are_flagged_with_a_visible_warning(raw: str) -> None:
    """The accepted cost of catching "Adele's voice": B7 shows this warning before Generate is clicked."""
    result = songs.check_style(raw)
    assert result.removed == (raw,)
    assert result.warning is not None


def test_long_input_is_capped_and_fast() -> None:
    """Review of #38: 21,000 characters took about 2.8 s to screen."""
    import time

    for text in ("Aa " * 7000, "A/B/" * 5000, "in the style of " * 2000):
        start = time.perf_counter()
        result = songs.check_style(text)
        assert time.perf_counter() - start < 0.5
        assert len(result.text) <= songs.MAX_SCREENED_CHARS


# ---- the theme -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "theme",
    [
        "a love song inspired by Paris in spring",
        "inspired by Mom",
        "dancing like Nobody is watching",
        "a road trip like Thelma & Louise",
        "a Beatles-esque daydream",
        "the voice of God",
        "the voice of an Angel",
        "listening to the voice of My Mother",
    ],
)
def test_the_theme_keeps_ordinary_names_and_places(theme: str) -> None:
    """Reviews of #38: the theme lost its subject silently. Only obvious style pointers are removed."""
    result = songs.check_theme(theme)
    assert result.text == theme
    assert result.removed == ()


@pytest.mark.parametrize(
    ("theme", "cleaned", "removed"),
    [
        (
            "a song about rain in the style of Taylor Swift",
            "a song about rain",
            "in the style of Taylor Swift",
        ),
        ("road trip, sounds like Coldplay", "road trip", "sounds like Coldplay"),
        ("heartbreak à la Adele", "heartbreak", "à la Adele"),
    ],
)
def test_the_theme_drops_obvious_style_pointers_and_warns(theme: str, cleaned: str, removed: str) -> None:
    result = songs.check_theme(theme)
    assert (result.text, list(result.removed)) == (cleaned, [removed])
    assert result.warning is not None


@pytest.mark.parametrize(
    "voice_style", ["rap, rapper", "opera, soprano", "falsetto pop", "a cappella", "acapella"]
)
def test_more_voice_words_count_as_a_named_voice(voice_style: str) -> None:
    assert "warm natural vocals" not in songs.build_tags(voice_style, "joyful", vocal=True)


# ---- the warning the UI shows --------------------------------------------------------------------


def test_warning_names_what_was_removed_and_says_why() -> None:
    one = songs.check_style("pop in the style of Taylor Swift").warning
    assert one == (
        "Removed “in the style of Taylor Swift”, which may point at an artist; that text isn't sent to the models."
    )
    two = songs.check_style("in the style of Adele, sounds like Drake, soul").warning
    assert two == (
        "Removed “in the style of Adele” and “sounds like Drake”, which may point at artists; "
        "that text isn't sent to the models."
    )


def test_the_warning_promises_only_what_the_app_does() -> None:
    """B9 review: the default voice can still resemble a famous singer, so the app can't promise that songs
    "never imitate" anyone. The screen is pattern-based, so it can't promise that every artist name is
    caught either. It can promise only that the text it removed never reaches the models."""
    warning = songs.check_style("pop in the style of Taylor Swift").warning
    assert "imitat" not in warning.lower()
    assert "never" not in warning.lower()
    assert "artist names" not in warning.lower()
    assert "that text isn't sent" in warning
    assert "may point at an artist" in warning  # #56 review: say why, without claiming it was an artist


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
        env, style="upbeat pop in the style of Taylor Swift", theme="a road trip, sounds like Coldplay"
    )
    assert updates[-1].status == "succeeded"
    tags = json.loads(submit.calls[0].request.content)["prompt"]
    assert tags == "upbeat pop, upbeat, warm natural vocals"
    sent = json.dumps(json.loads(qwen_route.calls[0].request.content)["messages"])
    assert "Taylor" not in sent and "Swift" not in sent and "Coldplay" not in sent


@respx.mock
def test_the_cover_prompt_gets_the_cleaned_style_and_theme(env: dict) -> None:
    """#56 review: the removed text never reaches FLUX either. The cover hook gets the stored, cleaned
    Track, and the cover prompt is built from it."""
    mock_services()
    covered: list = []
    done = threading.Event()
    run(
        env,
        style="indie rock, sounds like Radiohead",
        theme="rainy city, in the style of Adele",
        start_cover=lambda track: (covered.append(track), done.set()),
    )
    assert done.wait(5)
    asked: list = []

    def chat(messages, **_kw) -> str:
        asked.append(json.dumps(messages))
        return "a rainy city street at night"

    art.render_cover(
        covered[0], env["library"].resolve("cover.jpg"), chat=chat, generate=lambda *_a, **_k: b"jpg"
    )
    for name in ("Radiohead", "Adele"):
        assert name not in asked[0]


@respx.mock
def test_pipeline_keeps_an_ordinary_theme(env: dict) -> None:
    mock_services()
    track_id = run(env, style="pop", theme="a love song inspired by Paris in spring")[-1].track_id
    assert env["library"].get(track_id).theme == "a love song inspired by Paris in spring"


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
