"""Tests for jukebox/errors.py: ServiceError, the user-facing messages (PROJECT.md 7.3), and redaction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jukebox.errors import ServiceError, recovery, redact, user_message  # noqa: E402

KEY = "test-key-0123456789"
SERVICES = {"qwen": "Qwen", "flux": "FLUX", "acestep": "ACE-Step", "chatterbox": "Chatterbox"}


# ---- ServiceError -----------------------------------------------------------------------------


def test_service_error_carries_service_kind_and_detail() -> None:
    err = ServiceError("flux", "timeout", "read timed out after 120s")
    assert (err.service, err.kind, err.detail) == ("flux", "timeout", "read timed out after 120s")
    assert "flux" in str(err) and "timeout" in str(err) and "read timed out" in str(err)


def test_service_error_is_an_exception() -> None:
    with pytest.raises(ServiceError):
        raise ServiceError("qwen", "auth")


def test_unknown_kind_or_service_is_rejected() -> None:
    with pytest.raises(ValueError):
        ServiceError("qwen", "exploded")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ServiceError("openai", "auth")  # type: ignore[arg-type]


# ---- user-facing messages (7.3) ---------------------------------------------------------------


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize(
    ("kind", "phrase"),
    [
        ("config", "isn't configured"),
        ("auth", "rejected our credentials"),
        ("timeout", "took too long to respond"),
        ("unavailable", "unreachable right now"),
        ("bad_request", "couldn't process that request"),
        ("bad_response", "returned something unexpected"),
    ],
)
def test_message_names_the_service_and_says_what_happened(service: str, kind: str, phrase: str) -> None:
    msg = user_message(ServiceError(service, kind))  # type: ignore[arg-type]
    assert SERVICES[service] in msg
    assert phrase in msg


def test_config_and_auth_messages_point_at_the_settings_file() -> None:
    assert ".env.example" in user_message(ServiceError("qwen", "config"))
    assert "API key" in user_message(ServiceError("qwen", "auth"))


def test_bad_request_message_includes_the_safe_reason() -> None:
    err = ServiceError("flux", "bad_request", "HTTP 422", reason="prompt is empty")
    assert user_message(err) == "FLUX couldn't process that request: prompt is empty."


def test_bad_request_without_a_reason_still_reads_well() -> None:
    msg = user_message(ServiceError("flux", "bad_request"))
    assert msg.startswith("FLUX couldn't process that request: ") and msg.endswith(".")


def test_long_reasons_are_cut_down() -> None:
    err = ServiceError("qwen", "bad_request", reason="x" * 5000)
    assert len(user_message(err)) < 400


def test_message_never_shows_developer_detail() -> None:
    err = ServiceError("qwen", "bad_response", "Traceback: secret internals at /srv/app.py")
    assert "internals" not in user_message(err)


# ---- recovery hints ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("timeout", "retry"),
        ("unavailable", "retry"),
        ("bad_response", "retry"),
        ("auth", "fix_and_restart"),
        ("bad_request", "edit_inputs"),
        ("config", None),
    ],
)
def test_recovery_offered_per_kind(kind: str, expected: str | None) -> None:
    assert recovery(ServiceError("acestep", kind)) == expected  # type: ignore[arg-type]


# ---- redaction (H8) ---------------------------------------------------------------------------


def test_redact_removes_the_key_everywhere() -> None:
    text = f"failed with {KEY} and again {KEY}"
    assert KEY not in redact(text, [KEY])


def test_redact_handles_authorization_headers_and_bearer_tokens() -> None:
    out = redact("Authorization: Bearer abc.def-123 and Bearer zzz999", [])
    assert "abc.def-123" not in out and "zzz999" not in out
    assert "Authorization" in out  # the header name stays, the value goes


@pytest.mark.parametrize(
    "text",
    ["api_key=sk-12345", '{"api_key": "sk-12345"}', "token: sk-12345", "password=sk-12345"],
)
def test_redact_handles_key_like_pairs(text: str) -> None:
    assert "sk-12345" not in redact(text, [])


def test_redact_leaves_ordinary_text_alone() -> None:
    assert redact("qwen -> class.example:9001 200 842ms", [KEY]) == "qwen -> class.example:9001 200 842ms"


def test_redact_ignores_empty_secrets() -> None:
    assert redact("hello", ["", None]) == "hello"  # type: ignore[list-item]
