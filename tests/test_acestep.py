"""Tests for jukebox/clients/acestep.py: the ACE-Step music client (task B4).

All HTTP is mocked with respx, and time is faked, so nothing really waits and no real class service is
called. Request and reply shapes follow the B2 spike (docs/spikes/B2-acestep.md) and PROJECT.md 7.1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.clients.acestep as acestep  # noqa: E402
from jukebox.clients.acestep import AceStepClient  # noqa: E402
from jukebox.config import Config, ConfigError, load_config  # noqa: E402
from jukebox.errors import ServiceError  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
BASE = f"http://{HOST}:9007"
SUBMIT = f"{BASE}/release_task"
POLL = f"{BASE}/query_result"
SERVER_PATH = "/srv/teacher/acestep/tmp/api_audio/abc123.mp3"  # stands in for the server's private path
FILE_REF = f"/v1/audio?path={quote(SERVER_PATH, safe='')}"
AUDIO = b"ID3\x04fake-mp3-bytes" * 10
LYRICS = "[verse]\nWindows down\n\n[chorus]\nKeep it rolling"


def make_config(tmp_path: Path, *, timeout_s: float | None = None) -> Config:
    env = {"CLASS_API_KEY": KEY, "ACESTEP_MODEL": "ACE-Step/acestep-v15-xl-turbo"}
    for service, port in PORTS.items():
        env[f"{service.upper()}_BASE_URL"] = f"http://{HOST}:{port}"
    if timeout_s is not None:
        env["ACESTEP_TIMEOUT_S"] = str(timeout_s)
    return load_config(env=env, env_file=tmp_path / "missing-file")


class FakeTime:
    """A clock that only moves when the client sleeps, so polling loops run instantly."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def client(tmp_path: Path, fake_time: FakeTime):
    c = AceStepClient(make_config(tmp_path), sleep=fake_time.sleep, clock=fake_time.clock)
    yield c
    c.close()


def submitted(task_id: str = "task-1") -> dict:
    return {"data": {"task_id": task_id, "status": "queued", "queue_position": 1}, "code": 200, "error": None}


def polled(
    status: int, *, file: str = FILE_REF, dit_model: str = "acestep-v15-xl-turbo", result=None
) -> dict:
    """A /query_result body. `result` is a JSON *string*, exactly as the class server sends it."""
    if result is None:
        result = json.dumps(
            [
                {
                    "file": file,
                    "status": 1,
                    "metas": {"duration": 30.0, "bpm": 96},
                    "seed_value": "42",
                    "dit_model": dit_model,
                    "lm_model": "acestep-5Hz-lm-4B",
                }
            ]
        )
    progress = f"Saved audio to {SERVER_PATH}" if status == 1 else "generating"
    return {"data": [{"task_id": "task-1", "status": status, "result": result, "progress_text": progress}]}


def mock_happy_path(*, statuses: tuple[int, ...] = (1,), audio: bytes = AUDIO, file: str = FILE_REF):
    submit = respx.post(SUBMIT).respond(200, json=submitted())
    poll = respx.post(POLL).mock(
        side_effect=[httpx.Response(200, json=polled(s, file=file)) for s in statuses]
    )
    download = respx.get(url__startswith=f"{BASE}/v1/audio").respond(
        200, content=audio, headers={"content-type": "audio/mpeg"}
    )
    return submit, poll, download


def body_of(route: respx.Route, call: int = 0) -> dict:
    return json.loads(route.calls[call].request.content)


# ---- the submit request (B2 format) -------------------------------------------------------------


@respx.mock
def test_submit_body_follows_b2_format_for_vocal(client: AceStepClient) -> None:
    submit, _, _ = mock_happy_path()
    client.generate_music(tags="upbeat pop, summery", lyrics=LYRICS, duration_s=30)
    body = body_of(submit)
    assert body["prompt"] == "upbeat pop, summery"
    assert body["lyrics"] == LYRICS
    assert body["audio_duration"] == 30
    assert body["audio_format"] == "mp3"
    assert body["inference_steps"] == 8
    assert body["batch_size"] == 1  # the server's default is 2, which would make two songs
    assert body["thinking"] is False
    assert body["vocal_language"] == "en"
    assert body["model"] == "ACE-Step/acestep-v15-xl-turbo"
    assert submit.calls[0].request.headers["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("lyrics", [None, "", "   \n"])
@respx.mock
def test_instrumental_sends_instrumental_marker(client: AceStepClient, lyrics: str | None) -> None:
    submit, _, _ = mock_happy_path()
    client.generate_music(tags="lo-fi hip hop, mellow", lyrics=lyrics, duration_s=30)
    assert body_of(submit)["lyrics"] == "[Instrumental]"


@respx.mock
def test_seed_turns_off_random_seed(client: AceStepClient) -> None:
    submit, _, _ = mock_happy_path()
    client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30, seed=42)
    body = body_of(submit)
    assert body["seed"] == 42
    assert body["use_random_seed"] is False


@respx.mock
def test_no_seed_uses_random_seed(client: AceStepClient) -> None:
    submit, _, _ = mock_happy_path()
    client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    body = body_of(submit)
    assert "seed" not in body
    assert body["use_random_seed"] is True


# ---- submit, poll, download ---------------------------------------------------------------------


@respx.mock
def test_polls_until_done_then_downloads(client: AceStepClient, fake_time: FakeTime) -> None:
    submit, poll, download = mock_happy_path(statuses=(0, 0, 1))
    audio, ext = client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert (audio, ext) == (AUDIO, "mp3")
    assert submit.call_count == 1
    assert poll.call_count == 3
    assert body_of(poll) == {"task_id_list": ["task-1"]}
    assert fake_time.sleeps == [1.0, 1.0]  # one poll per second while the job runs
    assert download.call_count == 1
    assert download.calls[0].request.url.params["path"] == SERVER_PATH


@respx.mock
def test_poll_uses_short_per_request_timeout(client: AceStepClient) -> None:
    _, poll, _ = mock_happy_path()
    client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    timeout = poll.calls[0].request.extensions["timeout"]
    assert timeout["read"] == acestep.POLL_TIMEOUT_S < 300


@respx.mock
def test_extension_comes_from_the_file_path(client: AceStepClient) -> None:
    wav_ref = f"/v1/audio?path={quote('/srv/x/song.wav', safe='')}"
    mock_happy_path(file=wav_ref)
    _, ext = client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert ext == "wav"


@pytest.mark.parametrize(
    "failure", [httpx.TimeoutException("slow"), httpx.Response(503), httpx.ConnectError("down")]
)
@respx.mock
def test_submit_is_never_retried(client: AceStepClient, failure: object) -> None:
    """A submit that timed out may already be queued, so a retry would start a second job (B2)."""
    route = respx.post(SUBMIT)
    if isinstance(failure, Exception):
        route.mock(side_effect=failure)
    else:
        route.mock(return_value=failure)
    with pytest.raises(ServiceError):
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert route.call_count == 1


# ---- errors -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (400, "bad_request"), (404, "config"), (500, "bad_response"), (503, "unavailable")],
)
@respx.mock
def test_submit_http_errors_map_to_kinds(client: AceStepClient, status: int, kind: str) -> None:
    respx.post(SUBMIT).respond(status, json={"detail": "nope"})
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.service == "acestep"
    assert e.value.kind == kind


@pytest.mark.parametrize(
    "body",
    [
        {"data": {}, "code": 200, "error": None},
        {"data": None, "code": 500, "error": "queue full"},
        {"code": 200},
        ["not", "a", "dict"],
    ],
)
@respx.mock
def test_submit_without_task_id_is_bad_response(client: AceStepClient, body: object) -> None:
    respx.post(SUBMIT).respond(200, json=body)
    poll = respx.post(POLL)
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"
    assert poll.call_count == 0


@respx.mock
def test_failed_job_is_bad_response(client: AceStepClient) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    respx.post(POLL).respond(200, json=polled(2, result="[]"))
    download = respx.get(url__startswith=f"{BASE}/v1/audio")
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"
    assert download.call_count == 0


@respx.mock
def test_job_that_never_finishes_times_out(tmp_path: Path, fake_time: FakeTime) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    poll = respx.post(POLL).respond(200, json=polled(0))
    download = respx.get(url__startswith=f"{BASE}/v1/audio")
    with AceStepClient(
        make_config(tmp_path, timeout_s=20), sleep=fake_time.sleep, clock=fake_time.clock
    ) as c:
        with pytest.raises(ServiceError) as e:
            c.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "timeout"
    assert 15 <= poll.call_count <= 22  # about one poll per second for the 20 s job limit
    assert download.call_count == 0


@respx.mock
def test_a_job_still_missing_from_the_queue_is_polled_again(client: AceStepClient) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    poll = respx.post(POLL).mock(
        side_effect=[httpx.Response(200, json={"data": []}), httpx.Response(200, json=polled(1))]
    )
    respx.get(url__startswith=f"{BASE}/v1/audio").respond(200, content=AUDIO)
    assert client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30) == (AUDIO, "mp3")
    assert poll.call_count == 2


@respx.mock
def test_unexpected_model_is_bad_response(client: AceStepClient) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    respx.post(POLL).respond(200, json=polled(1, dit_model="some-other-model"))
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"
    assert "acestep-v15-xl-turbo" in e.value.detail


@pytest.mark.parametrize("result", ["not json", "[]", "{}", '[{"status": 1}]', '[{"file": 42}]', None])
@respx.mock
def test_unparseable_result_is_bad_response(client: AceStepClient, result: object) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    body = polled(1)
    body["data"][0]["result"] = result
    respx.post(POLL).respond(200, json=body)
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"


@respx.mock
def test_poll_404_is_bad_response_not_config(client: AceStepClient) -> None:
    """A 404 here means the job is gone, not that the settings are wrong (PROJECT.md 7.2)."""
    respx.post(SUBMIT).respond(200, json=submitted())
    respx.post(POLL).respond(404)
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"


@respx.mock
def test_download_404_is_bad_response_not_config(client: AceStepClient) -> None:
    respx.post(SUBMIT).respond(200, json=submitted())
    respx.post(POLL).respond(200, json=polled(1))
    respx.get(url__startswith=f"{BASE}/v1/audio").respond(404)
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"


@respx.mock
def test_empty_audio_is_bad_response(client: AceStepClient) -> None:
    mock_happy_path(audio=b"")
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert e.value.kind == "bad_response"


@pytest.mark.parametrize("duration_s", [5, 9, 601, 0, -30])
@respx.mock
def test_duration_out_of_range_is_bad_request_without_calling(client: AceStepClient, duration_s: int) -> None:
    submit = respx.post(SUBMIT)
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=duration_s)
    assert e.value.kind == "bad_request"
    assert "10" in (e.value.reason or "") and "600" in (e.value.reason or "")
    assert submit.call_count == 0


@respx.mock
def test_errors_never_include_server_paths(client: AceStepClient) -> None:
    """The server's progress_text and file values contain its private paths (B2). Keep them out."""
    respx.post(SUBMIT).respond(200, json=submitted())
    respx.post(POLL).respond(200, json=polled(1, dit_model="other"))
    with pytest.raises(ServiceError) as e:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert "/srv/" not in str(e.value)
    assert "teacher" not in str(e.value)

    respx.get(url__startswith=f"{BASE}/v1/audio").respond(404, text=f"no such file {SERVER_PATH}")
    respx.post(POLL).respond(200, json=polled(1))
    with pytest.raises(ServiceError) as e2:
        client.generate_music(tags="pop", lyrics=LYRICS, duration_s=30)
    assert "/srv/" not in str(e2.value)
    assert "teacher" not in str(e2.value)


# ---- module-level generate_music() (PROJECT.md 7.2 signature) ---------------------------------------


def test_module_generate_music_uses_lazy_default_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[int] = []
    fake_time = FakeTime()

    def fake_client() -> AceStepClient:
        built.append(1)
        return AceStepClient(make_config(tmp_path), sleep=fake_time.sleep, clock=fake_time.clock)

    monkeypatch.setattr(acestep, "_default", None)
    monkeypatch.setattr(acestep, "_make_default_client", fake_client)
    with respx.mock:
        respx.post(SUBMIT).respond(200, json=submitted())
        respx.post(POLL).respond(200, json=polled(1))
        respx.get(url__startswith=f"{BASE}/v1/audio").respond(200, content=AUDIO)
        assert acestep.generate_music(tags="pop", lyrics=None, duration_s=30) == (AUDIO, "mp3")
        assert acestep.generate_music(tags="pop", lyrics=LYRICS, duration_s=60, seed=7) == (AUDIO, "mp3")
    assert built == [1]  # created once, on first use, then reused


def test_module_config_error_becomes_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> AceStepClient:
        raise ConfigError(["ACESTEP_BASE_URL: missing"])

    monkeypatch.setattr(acestep, "_default", None)
    monkeypatch.setattr(acestep, "_make_default_client", broken)
    with pytest.raises(ServiceError) as e:
        acestep.generate_music(tags="pop", lyrics=None, duration_s=30)
    assert (e.value.service, e.value.kind) == ("acestep", "config")
    assert "ACESTEP_BASE_URL" in e.value.detail
    assert acestep._default is None


def test_client_is_bound_to_acestep_only(client: AceStepClient) -> None:
    assert client.service == "acestep"
    assert client.base_url == BASE
