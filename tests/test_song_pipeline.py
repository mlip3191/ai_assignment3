"""Tests for generate_song() in jukebox/services/songs.py: the song pipeline (task B6).

Qwen and ACE-Step are mocked with respx through the real clients, and the library lives in a temporary
folder, so no class service is called and nothing is written to the real runtime/ folder.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
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
from jukebox.jobs import GENERIC_FAILURE, JobStore  # noqa: E402
from jukebox.library import Library, LibraryError  # noqa: E402
from jukebox.models import Job, Track  # noqa: E402

HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
QWEN_URL = f"http://{HOST}:9001/v1/chat/completions"
ACE = f"http://{HOST}:9007"
FILE_REF = f"/v1/audio?path={quote('/srv/acestep/tmp/abc123.mp3', safe='')}"
AUDIO = b"ID3\x04fake-mp3-bytes" * 10
LYRICS = (
    "[intro]\n\n[verse]\nWindows down and the radio on\nChasing the sun till the day is gone\n\n"
    "[chorus]\nKeep it rolling, keep it free\nJust the open road and me"
)
SONG = {"style": "synth-pop", "mood": "upbeat", "duration_s": 30, "vocal": True, "theme": "a road trip"}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Real Qwen and ACE-Step clients pointed at fake addresses, and an empty library and job store."""
    values = {"CLASS_API_KEY": "test-key-0123456789"}
    for service, port in PORTS.items():
        values[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    config = load_config(env=values, env_file=tmp_path / "missing-file")
    q = QwenClient(config, sleep=lambda _s: None)
    a = AceStepClient(config, sleep=lambda _s: None)
    monkeypatch.setattr(qwen, "_default", q)
    monkeypatch.setattr(acestep, "_default", a)
    yield {"library": Library(root=tmp_path), "jobs": JobStore(), "root": tmp_path}
    q.close()
    a.close()


def qwen_says(content: str) -> dict:
    return {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ]
    }


def mock_qwen(title: str = "Open Road", lyrics: str | None = LYRICS) -> respx.Route:
    reply = {"title": title} if lyrics is None else {"title": title, "lyrics": lyrics}
    return respx.post(QWEN_URL).respond(200, json=qwen_says(json.dumps(reply)))


def mock_acestep(audio: bytes = AUDIO) -> tuple[respx.Route, respx.Route]:
    result = json.dumps([{"file": FILE_REF, "status": 1, "dit_model": "acestep-v15-xl-turbo"}])
    submit = respx.post(f"{ACE}/release_task").respond(200, json={"data": {"task_id": "task-1"}})
    respx.post(f"{ACE}/query_result").respond(
        200, json={"data": [{"task_id": "task-1", "status": 1, "result": result}]}
    )
    download = respx.get(url__startswith=f"{ACE}/v1/audio").respond(200, content=audio)
    return submit, download


def run(env: dict, *, start_cover=None, **overrides) -> list[Job]:
    """Run the whole generator and return every update it yielded."""
    args = {**SONG, **overrides}
    return list(
        songs.generate_song(**args, library=env["library"], jobs=env["jobs"], start_cover=start_cover)
    )


def generated_files(env: dict) -> list[Path]:
    folder = env["root"] / "runtime" / "generated"
    return sorted(folder.iterdir()) if folder.exists() else []


# ---- success -------------------------------------------------------------------------------------


@respx.mock
def test_vocal_song_yields_each_stage_in_order(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    updates = run(env)
    assert [u.stage for u in updates] == [
        songs.STAGE_QUEUED,
        songs.STAGE_LYRICS,
        songs.STAGE_MUSIC,
        songs.STAGE_SAVING,
        songs.STAGE_DONE,
    ]
    assert [u.status for u in updates] == ["queued", "running", "running", "running", "succeeded"]
    assert all(u.kind == "song" and u.id == updates[0].id for u in updates)
    assert updates[-1].error is None
    assert updates[-1].track_id


@respx.mock
def test_instrumental_song_is_named_and_sent_as_instrumental(env: dict) -> None:
    qwen_route = mock_qwen(title="Low Tide", lyrics=None)
    submit, _ = mock_acestep()
    updates = run(env, vocal=False, style="lo-fi hip hop", mood="mellow", theme=None)
    assert updates[1].stage == songs.STAGE_TITLE
    assert updates[-1].status == "succeeded"
    assert json.loads(submit.calls[0].request.content)["lyrics"] == acestep.INSTRUMENTAL
    assert "[verse]" not in json.loads(qwen_route.calls[0].request.content)["messages"][1]["content"]
    track = env["library"].get(updates[-1].track_id)
    assert track.title == "Low Tide"
    assert track.lyrics is None
    assert track.vocal is False


@respx.mock
def test_tags_combine_style_mood_and_voice(env: dict) -> None:
    mock_qwen()
    submit, _ = mock_acestep()
    run(env)
    body = json.loads(submit.calls[0].request.content)
    assert body["prompt"] == "synth-pop, upbeat, warm natural vocals"
    assert body["lyrics"] == LYRICS
    assert body["audio_duration"] == 30
    assert (
        songs.build_tags("lo-fi hip hop, jazzy keys", "mellow", vocal=False)
        == "lo-fi hip hop, jazzy keys, mellow, instrumental"
    )


@pytest.mark.parametrize(
    "style",
    [
        "upbeat pop, warm natural female vocals",
        "cinematic folk, deep male vocal",
        "soul, powerful female vocalist",
        "folk, raspy voice",
        "gospel, choir",
        "indie, Female Vocals",
    ],
)
def test_voice_tag_is_added_only_when_the_style_names_no_voice(style: str) -> None:
    """Review of #40: sample_02 would have been sent "...female vocals, joyful, warm natural vocals"."""
    assert songs.build_tags(style, "joyful", vocal=True) == f"{style}, joyful"


def test_default_voice_tag_is_kept_for_styles_without_a_voice() -> None:
    assert songs.build_tags("synth-pop", "upbeat", vocal=True) == "synth-pop, upbeat, warm natural vocals"
    assert (
        songs.build_tags("country rock, steel guitar", "triumphant", vocal=True)
        == "country rock, steel guitar, triumphant, warm natural vocals"
    )
    assert songs.build_tags("vocal jazz", "smooth", vocal=False) == "vocal jazz, smooth, instrumental"


@respx.mock
def test_seed_is_sent_and_kept_on_the_track(env: dict) -> None:
    mock_qwen()
    submit, _ = mock_acestep()
    updates = run(env, seed=1234)
    assert json.loads(submit.calls[0].request.content)["seed"] == 1234
    assert env["library"].get(updates[-1].track_id).seed == 1234


# ---- saving and the library ----------------------------------------------------------------------


@respx.mock
def test_audio_is_saved_under_runtime_generated_by_track_id(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    track_id = run(env)[-1].track_id
    assert generated_files(env) == [env["root"] / "runtime" / "generated" / f"{track_id}.mp3"]
    assert generated_files(env)[0].read_bytes() == AUDIO


@respx.mock
def test_track_joins_the_library_with_every_field(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    track_id = run(env)[-1].track_id
    track = env["library"].get(track_id)
    assert isinstance(track, Track)
    assert len(track_id) == 32 and int(track_id, 16) >= 0  # uuid4 hex (PROJECT.md 6.1)
    assert (track.title, track.style, track.mood, track.theme) == (
        "Open Road",
        "synth-pop",
        "upbeat",
        "a road trip",
    )
    assert (track.duration_s, track.vocal, track.lyrics) == (30, True, LYRICS)
    assert track.audio_path == f"runtime/generated/{track_id}.mp3"  # relative, forward slashes (6.3)
    assert env["library"].resolve(track.audio_path).read_bytes() == AUDIO
    assert (track.cover_path, track.cover_prompt, track.source, track.seed) == (None, None, "generated", None)
    datetime.fromisoformat(track.created_at)
    assert [t.id for t in env["library"].list()] == [track_id]


@respx.mock
def test_blank_theme_is_stored_as_none(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    track_id = run(env, theme="   ")[-1].track_id
    assert env["library"].get(track_id).theme is None


@respx.mock
def test_job_store_records_the_finished_job(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    last = run(env)[-1]
    stored = env["jobs"].get(last.id)
    assert stored.status == "succeeded"
    assert stored.track_id == last.track_id
    assert stored.finished_at is not None


@respx.mock
def test_yields_are_snapshots(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    updates = run(env)
    updates[0].stage = "changed by the UI"
    assert env["jobs"].get(updates[0].id).stage == songs.STAGE_DONE


# ---- the cover job ---------------------------------------------------------------------------------


@respx.mock
def test_cover_job_starts_without_waiting(env: dict) -> None:
    """The song finishes while the cover is still running, on another thread."""
    mock_qwen()
    mock_acestep()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    seen: list[tuple[Track, threading.Thread]] = []

    def slow_cover(track: Track) -> None:
        seen.append((track, threading.current_thread()))
        started.set()
        release.wait(10)
        finished.set()

    try:
        updates = run(env, start_cover=slow_cover)
        assert updates[-1].status == "succeeded"
        assert not finished.is_set()  # a cover run inline would have finished before the song did
        assert started.wait(5)
        track, thread = seen[0]
        assert thread is not threading.current_thread()
        assert track.id == updates[-1].track_id
        assert env["library"].get(track.id) is not None  # the track is already in the library
    finally:
        release.set()
    assert finished.wait(5)


@respx.mock
def test_cover_failure_never_affects_the_song(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    called = threading.Event()

    def broken_cover(_track: Track) -> None:
        called.set()
        raise RuntimeError("FLUX exploded")

    updates = run(env, start_cover=broken_cover)
    assert called.wait(5)
    assert updates[-1].status == "succeeded"
    assert env["library"].get(updates[-1].track_id) is not None


@respx.mock
def test_no_cover_hook_is_fine(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    track_id = run(env, start_cover=None)[-1].track_id
    assert env["library"].get(track_id).cover_path is None  # the UI shows the placeholder


# ---- failures --------------------------------------------------------------------------------------


@respx.mock
def test_qwen_failure_fails_the_job_with_no_track_and_no_audio_call(env: dict) -> None:
    respx.post(QWEN_URL).respond(503)
    submit, _ = mock_acestep()
    updates = run(env)
    last = updates[-1]
    assert last.status == "failed"
    assert last.stage == songs.STAGE_LYRICS  # the stage where it failed stays visible
    assert last.error == "The Qwen service is unreachable right now."
    assert last.track_id is None
    assert submit.call_count == 0
    assert env["library"].list() == []
    assert generated_files(env) == []


@respx.mock
def test_unusable_lyrics_fail_the_song(env: dict) -> None:
    respx.post(QWEN_URL).respond(200, json=qwen_says("I'd rather not."))
    submit, _ = mock_acestep()
    last = run(env)[-1]
    assert last.status == "failed"
    assert last.error == "Qwen returned something unexpected."
    assert submit.call_count == 0  # no stand-in lyrics (PROJECT.md 7.3)


@respx.mock
def test_acestep_failure_leaves_no_track_and_no_file(env: dict) -> None:
    mock_qwen()
    respx.post(f"{ACE}/release_task").respond(401)
    last = run(env)[-1]
    assert last.status == "failed"
    assert last.stage == songs.STAGE_MUSIC
    assert last.error == "The ACE-Step service rejected our credentials. Check the API key in `.env`."
    assert env["library"].list() == []
    assert generated_files(env) == []


@respx.mock
def test_library_failure_removes_the_saved_file(env: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_qwen()
    mock_acestep()

    def refuse(_track: Track) -> Track:
        raise LibraryError("no room")

    monkeypatch.setattr(env["library"], "add", refuse)
    last = run(env)[-1]
    assert last.status == "failed"
    assert last.error == GENERIC_FAILURE
    assert generated_files(env) == []


@respx.mock
def test_unexpected_error_becomes_the_generic_message_and_never_raises(
    env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_qwen()
    mock_acestep()

    def disk_full(*_args, **_kwargs):
        raise OSError("No space left on device: C:\\Users\\someone\\secret")

    monkeypatch.setattr(songs, "_save_audio", disk_full)
    last = run(env)[-1]
    assert last.status == "failed"
    assert last.error == GENERIC_FAILURE
    assert "secret" not in last.error
    assert env["library"].list() == []


@respx.mock
@pytest.mark.parametrize("duration_s", [5, 9, 601])
def test_out_of_range_duration_fails_before_any_call(env: dict, duration_s: int) -> None:
    qwen_route = mock_qwen()
    submit, _ = mock_acestep()
    updates = run(env, duration_s=duration_s)
    assert [u.status for u in updates] == ["queued", "failed"]
    assert (
        updates[-1].error
        == "ACE-Step couldn't process that request: Duration must be between 10 and 600 seconds."
    )
    assert qwen_route.call_count == 0 and submit.call_count == 0


@respx.mock
@pytest.mark.parametrize(("field", "message"), [("style", "Choose a style"), ("mood", "Choose a mood")])
def test_blank_style_or_mood_fails_before_any_call(env: dict, field: str, message: str) -> None:
    qwen_route = mock_qwen()
    updates = run(env, **{field: "  "})
    assert updates[-1].status == "failed"
    assert updates[-1].error == f"ACE-Step couldn't process that request: {message}."
    assert qwen_route.call_count == 0


@respx.mock
def test_whole_number_floats_from_the_ui_are_accepted(env: dict) -> None:
    """A Gradio slider or number box may send 60.0 instead of 60."""
    mock_qwen()
    submit, _ = mock_acestep()
    updates = run(env, duration_s=30.0, seed=7.0)
    assert updates[-1].status == "succeeded"
    track = env["library"].get(updates[-1].track_id)
    assert track.duration_s == 30 and isinstance(track.duration_s, int)
    assert track.seed == 7 and isinstance(track.seed, int)
    body = json.loads(submit.calls[0].request.content)
    assert body["audio_duration"] == 30 and body["seed"] == 7


@respx.mock
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"duration_s": 30.5}, "Duration must be a whole number of seconds"),
        ({"duration_s": "30"}, "Duration must be a whole number of seconds"),
        ({"duration_s": True}, "Duration must be a whole number of seconds"),
        ({"seed": 7.5}, "Seed must be a whole number"),
        ({"seed": "7"}, "Seed must be a whole number"),
    ],
)
def test_fractional_or_non_numeric_inputs_fail_before_any_call(
    env: dict, overrides: dict, message: str
) -> None:
    qwen_route = mock_qwen()
    submit, _ = mock_acestep()
    updates = run(env, **overrides)
    assert [u.status for u in updates] == ["queued", "failed"]
    assert updates[-1].error == f"ACE-Step couldn't process that request: {message}."
    assert qwen_route.call_count == 0 and submit.call_count == 0


@respx.mock
def test_closing_right_after_queued_fails_the_job(env: dict) -> None:
    mock_qwen()
    updates = songs.generate_song(**SONG, library=env["library"], jobs=env["jobs"])
    first = next(updates)
    updates.close()
    stored = env["jobs"].get(first.id)
    assert stored.status == "failed"
    assert stored.finished_at is not None


@respx.mock
def test_closing_the_generator_early_fails_the_job_and_leaves_nothing(env: dict) -> None:
    """The UI may stop listening part-way (a closed browser tab). The job must not stay "running"."""
    mock_qwen()
    mock_acestep()
    updates = songs.generate_song(**SONG, library=env["library"], jobs=env["jobs"])
    first = next(updates)
    next(updates)  # now writing lyrics
    updates.close()
    stored = env["jobs"].get(first.id)
    assert stored.status == "failed"
    assert stored.error == GENERIC_FAILURE
    assert env["library"].list() == []
    assert generated_files(env) == []


# ---- two songs at once (R2) ------------------------------------------------------------------------


@respx.mock
def test_two_songs_at_once_get_their_own_tracks(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    results: list[Job] = []

    def make() -> None:
        results.append(run(env)[-1])

    threads = [threading.Thread(target=make) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert [r.status for r in results] == ["succeeded", "succeeded"]
    ids = {r.track_id for r in results}
    assert len(ids) == 2
    assert {t.id for t in env["library"].list()} == ids
    assert len(generated_files(env)) == 2


@respx.mock
def test_jobs_go_to_the_shared_store_by_default(env: dict) -> None:
    mock_qwen()
    mock_acestep()
    updates = list(songs.generate_song(**SONG, library=env["library"]))
    assert isinstance(songs.JOBS, JobStore)
    assert songs.JOBS.get(updates[-1].id).status == "succeeded"
    assert env["jobs"].list() == []
