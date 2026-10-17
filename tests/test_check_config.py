"""Tests for scripts/check_config.py: a per-variable OK/missing table that never prints values."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_config import main  # noqa: E402

KEY = "test-key-0123456789"
HOST = "class.example"
FORBIDDEN_PORT = 9 * 1000


def settings(tmp_path: Path, **overrides: str) -> Path:
    values = {
        "CLASS_API_KEY": KEY,
        "QWEN_BASE_URL": f"http://{HOST}:9001/v1",
        "FLUX_BASE_URL": f"http://{HOST}:9006/v1",
        "ACESTEP_BASE_URL": f"http://{HOST}:9007",
        "CHATTERBOX_BASE_URL": f"http://{HOST}:9008",
        "QWEN_MODEL": "qwen-model",
        "FLUX_MODEL": "flux-model",
        "ACESTEP_MODEL": "acestep-model",
        "CHATTERBOX_MODEL": "chatterbox-model",
    }
    values.update(overrides)
    f = tmp_path / "settings"
    f.write_text("\n".join(f"{k}={v}" for k, v in values.items() if v is not None) + "\n", encoding="utf-8")
    return f


def test_valid_settings_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--env-file", str(settings(tmp_path))], env={}) == 0
    out = capsys.readouterr().out
    for var in ("CLASS_API_KEY", "QWEN_BASE_URL", "FLUX_BASE_URL", "ACESTEP_BASE_URL", "CHATTERBOX_BASE_URL"):
        assert var in out
    assert "MISSING" not in out and "INVALID" not in out


def test_table_never_prints_values(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["--env-file", str(settings(tmp_path))], env={})
    out = capsys.readouterr().out
    assert KEY not in out
    assert HOST not in out
    assert "qwen-model" not in out


def test_missing_variable_is_reported_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "settings"
    f.write_text(f"QWEN_BASE_URL=http://{HOST}:9001\n", encoding="utf-8")
    assert main(["--env-file", str(f)], env={}) == 1
    rows = {line.split()[0]: line for line in capsys.readouterr().out.splitlines() if line.strip()}
    assert "MISSING" in rows["CLASS_API_KEY"]
    assert "MISSING" in rows["FLUX_BASE_URL"]
    assert "OK" in rows["QWEN_BASE_URL"]


def test_port_9000_is_flagged_without_echoing_the_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = settings(tmp_path, QWEN_BASE_URL=f"http://{HOST}:{FORBIDDEN_PORT}")
    assert main(["--env-file", str(f)], env={}) == 1
    out = capsys.readouterr().out
    qwen = next(line for line in out.splitlines() if line.startswith("QWEN_BASE_URL"))
    assert "INVALID" in qwen
    assert HOST not in out


def test_wrong_port_for_a_service_is_flagged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = settings(tmp_path, FLUX_BASE_URL=f"http://{HOST}:9001")
    assert main(["--env-file", str(f)], env={}) == 1
    out = capsys.readouterr().out
    assert next(line for line in out.splitlines() if line.startswith("FLUX_BASE_URL")).count("INVALID") == 1


def test_unknown_base_url_is_flagged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "settings"
    f.write_text(settings(tmp_path).read_text(encoding="utf-8") + f"OPENAI_BASE_URL=http://{HOST}:9002\n")
    assert main(["--env-file", str(f)], env={}) == 1
    out = capsys.readouterr().out
    assert "OPENAI_BASE_URL" in out
    assert HOST not in out


def test_missing_file_fails_with_a_clear_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--env-file", str(tmp_path / "nope")], env={}) == 1
    out = capsys.readouterr().out
    assert "not found" in out.lower()


def test_unset_optional_values_say_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["--env-file", str(settings(tmp_path))], env={})
    out = capsys.readouterr().out
    timeout = next(line for line in out.splitlines() if line.startswith("ACESTEP_TIMEOUT_S"))
    assert "default" in timeout
