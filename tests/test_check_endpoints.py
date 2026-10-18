"""Tests for scripts/check_endpoints.py: one tiny request per service, PASS/FAIL with latency.

All HTTP is mocked with respx. No real class service is ever called.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_endpoints import main  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
PORTS = {"qwen": 9001, "flux": 9006, "acestep": 9007, "chatterbox": 9008}
# What each service reports in GET /v1/models (PROJECT.md 7.1, spike docs B1, B2, C1, D1)
REPORTED = {
    "qwen": "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
    "flux": "black-forest-labs/FLUX.2-klein-4B",
    "acestep": "acestep/acestep-v15-xl-turbo",
    "chatterbox": "chatterbox-v3",
}
CONFIGURED = {
    "qwen": "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit",
    "flux": "black-forest-labs/FLUX.2-klein-4B",
    "acestep": "ACE-Step/acestep-v15-xl-turbo",  # class-endpoints.txt spelling, differs from the server's
    "chatterbox": "chatterbox-v3",
}
NO_SLEEP = {"sleep": lambda _s: None}  # the client's retry backoff must not slow the tests


def url(service: str) -> str:
    return f"http://{HOST}:{PORTS[service]}/v1/models"


def models_body(*ids: str) -> dict:
    return {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}


def settings(tmp_path: Path, **overrides: str) -> Path:
    values = {
        "CLASS_API_KEY": KEY,
        **{f"{s.upper()}_BASE_URL": f"http://{HOST}:{p}" for s, p in PORTS.items()},
        **{f"{s.upper()}_MODEL": m for s, m in CONFIGURED.items()},
    }
    values.update(overrides)
    f = tmp_path / "settings"
    f.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    return f


def mock_all_ok() -> None:
    for service in PORTS:
        respx.get(url(service)).respond(200, json=models_body(REPORTED[service]))


def run(tmp_path: Path, **overrides: str) -> int:
    return main(["--env-file", str(settings(tmp_path, **overrides))], env={}, **NO_SLEEP)


def row(out: str, service: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(service))


# ---- success ----------------------------------------------------------------------------------


@respx.mock
def test_all_four_pass_prints_pass_and_latency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mock_all_ok()
    assert run(tmp_path) == 0
    out = capsys.readouterr().out
    for service in PORTS:
        line = row(out, service)
        assert "PASS" in line
        assert " ms" in line
        assert str(PORTS[service]) in line
    assert "FAIL" not in out


@respx.mock
def test_each_service_gets_exactly_one_authenticated_request_to_its_own_port(tmp_path: Path) -> None:
    mock_all_ok()
    run(tmp_path)
    assert len(respx.calls) == 4
    seen = set()
    for call in respx.calls:
        request = call.request
        assert request.method == "GET"
        assert request.url.host == HOST
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        seen.add(request.url.port)
    assert seen == set(PORTS.values())  # the four class ports and nothing else, never the forbidden one


@respx.mock
@pytest.mark.parametrize("suffix", ["/v1", "/v1/"])
def test_base_urls_that_already_end_in_v1_are_not_doubled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], suffix: str
) -> None:
    """A pasted /v1 base is stripped by jukebox/config.py; end to end, the request must still be /v1/models."""
    mock_all_ok()
    overrides = {f"{s.upper()}_BASE_URL": f"http://{HOST}:{p}{suffix}" for s, p in PORTS.items()}
    assert run(tmp_path, **overrides) == 0
    assert "FAIL" not in capsys.readouterr().out
    assert len(respx.calls) == 4
    assert {call.request.url.path for call in respx.calls} == {"/v1/models"}


@respx.mock
def test_mixed_base_urls_each_reach_v1_models(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The real setup: Qwen and FLUX bases are pasted with /v1, ACE-Step and Chatterbox without."""
    mock_all_ok()
    overrides = {
        "QWEN_BASE_URL": f"http://{HOST}:9001/v1",
        "FLUX_BASE_URL": f"http://{HOST}:9006/v1",
    }
    assert run(tmp_path, **overrides) == 0
    assert "FAIL" not in capsys.readouterr().out
    assert {call.request.url.path for call in respx.calls} == {"/v1/models"}
    assert {call.request.url.port for call in respx.calls} == set(PORTS.values())


@respx.mock
@pytest.mark.parametrize("reported", ["acestep/acestep-v15-xl-turbo", "ACE-Step/acestep-v15-xl-turbo"])
def test_acestep_prefix_variants_are_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reported: str
) -> None:
    mock_all_ok()
    respx.get(url("acestep")).respond(200, json=models_body(reported))
    assert run(tmp_path) == 0
    assert "PASS" in row(capsys.readouterr().out, "acestep")


@respx.mock
def test_a_service_listing_several_models_passes_if_the_expected_one_is_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_all_ok()
    respx.get(url("acestep")).respond(200, json=models_body("something/else", REPORTED["acestep"]))
    assert run(tmp_path) == 0
    assert "PASS" in row(capsys.readouterr().out, "acestep")


@respx.mock
def test_unset_model_setting_still_checks_the_documented_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_all_ok()
    assert run(tmp_path, QWEN_MODEL="REPLACE_WITH_QWEN_NAME") == 0
    capsys.readouterr()  # drop the first run's output
    respx.get(url("qwen")).respond(200, json=models_body("some-other-llm"))
    assert run(tmp_path, QWEN_MODEL="REPLACE_WITH_QWEN_NAME") == 1
    assert "FAIL" in row(capsys.readouterr().out, "qwen")


# ---- wrong model ------------------------------------------------------------------------------


@respx.mock
def test_a_port_reporting_a_different_model_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mock_all_ok()
    respx.get(url("flux")).respond(200, json=models_body("some-other-image-model"))
    assert run(tmp_path) == 1
    out = capsys.readouterr().out
    flux = row(out, "flux")
    assert "FAIL" in flux
    assert "some-other-image-model" in flux  # says what it found
    assert "FLUX.2 klein 4B" in flux  # and what it expected
    for service in ("qwen", "acestep", "chatterbox"):
        assert "PASS" in row(out, service)


@respx.mock
def test_a_configured_model_the_service_does_not_offer_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_all_ok()
    assert run(tmp_path, CHATTERBOX_MODEL="chatterbox-v9") == 1
    line = row(capsys.readouterr().out, "chatterbox")
    assert "FAIL" in line
    assert "CHATTERBOX_MODEL" in line


@respx.mock
@pytest.mark.parametrize(
    "body",
    [{"models": ["chatterbox-v3"]}, {"data": []}, {"data": [{"name": "chatterbox-v3"}]}, ["chatterbox-v3"]],
)
def test_an_unexpected_models_body_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], body: object
) -> None:
    mock_all_ok()
    respx.get(url("chatterbox")).respond(200, json=body)
    assert run(tmp_path) == 1
    line = row(capsys.readouterr().out, "chatterbox")
    assert "FAIL" in line
    assert "model" in line.lower()


@respx.mock
def test_a_non_json_body_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mock_all_ok()
    respx.get(url("qwen")).respond(200, text="<html>hello</html>")
    assert run(tmp_path) == 1
    assert "returned something unexpected" in row(capsys.readouterr().out, "qwen")


# ---- service failures -------------------------------------------------------------------------


@respx.mock
def test_a_401_fails_with_the_credentials_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for service in PORTS:
        respx.get(url(service)).respond(401, json={"error": "Unauthorized"})
    assert run(tmp_path) == 1
    out = capsys.readouterr().out
    for service in PORTS:
        line = row(out, service)
        assert "FAIL" in line
        assert "rejected our credentials" in line
    assert len(respx.calls) == 4  # no retry on 4xx


@respx.mock
def test_one_dead_service_does_not_hide_the_others(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mock_all_ok()
    respx.get(url("qwen")).mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(url("flux")).mock(side_effect=httpx.ConnectError("down"))
    assert run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "took too long" in row(out, "qwen")
    assert "unreachable" in row(out, "flux")
    assert "PASS" in row(out, "acestep")
    assert "PASS" in row(out, "chatterbox")


@respx.mock
def test_failed_rows_still_show_how_long_the_request_took(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PASS/FAIL plus latency: a refusal and a timeout are told apart by their time, so FAIL rows show it too."""
    mock_all_ok()
    respx.get(url("qwen")).respond(401, json={"error": "Unauthorized"})
    respx.get(url("flux")).mock(side_effect=httpx.ConnectError("down"))
    respx.get(url("acestep")).respond(200, json=models_body("some-other-model"))
    assert run(tmp_path) == 1
    out = capsys.readouterr().out
    for service in ("qwen", "flux", "acestep"):
        line = row(out, service)
        assert "FAIL" in line
        assert re.search(r"\d+ ms", line), f"no latency on the {service} FAIL row: {line!r}"
    assert re.search(r"\d+ ms", row(out, "chatterbox"))


@respx.mock
def test_summary_counts_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mock_all_ok()
    respx.get(url("flux")).respond(503)
    run(tmp_path)
    assert "1 of 4" in capsys.readouterr().out


# ---- configuration problems -------------------------------------------------------------------


@respx.mock
def test_missing_settings_fail_without_calling_anything_or_printing_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "settings"
    f.write_text(f"QWEN_BASE_URL=http://{HOST}:9001\n", encoding="utf-8")
    assert main(["--env-file", str(f)], env={}, **NO_SLEEP) == 1
    out = capsys.readouterr().out
    assert "CLASS_API_KEY" in out  # names the variable
    assert HOST not in out
    assert len(respx.calls) == 0


@respx.mock
def test_missing_settings_file_fails_with_a_clear_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--env-file", str(tmp_path / "nope")], env={}, **NO_SLEEP) == 1
    assert "not found" in capsys.readouterr().out.lower()
    assert len(respx.calls) == 0


@respx.mock
def test_a_service_url_on_the_wrong_port_is_refused_before_any_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, FLUX_BASE_URL=f"http://{HOST}:9001") == 1
    assert "FLUX_BASE_URL" in capsys.readouterr().out
    assert len(respx.calls) == 0


# ---- secrets ----------------------------------------------------------------------------------


@respx.mock
def test_the_key_and_host_never_appear_in_output_or_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    mock_all_ok()
    respx.get(url("qwen")).respond(401, text=f"bad key {KEY} for Authorization: Bearer {KEY}")
    respx.get(url("flux")).respond(200, json=models_body(f"model-{KEY}"))
    with caplog.at_level(logging.DEBUG):
        run(tmp_path)
    captured = capsys.readouterr()
    everything = captured.out + captured.err + caplog.text
    assert KEY not in everything
    assert HOST not in captured.out
