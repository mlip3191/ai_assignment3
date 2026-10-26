"""Tests for jukebox/ui/dj_settings.py: the DJ voice upload panel (task D4).

The handlers are plain functions over dj.VOICE, so they're tested without a browser. Every clip is
made in tmp_path; no recording is committed and no class service is called.
"""

from __future__ import annotations

import sys
from pathlib import Path

import gradio as gr
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jukebox.services.dj as dj  # noqa: E402
import jukebox.ui.dj_settings as settings  # noqa: E402


def _clip(path: Path, seconds: float, rate: int = 16000) -> Path:
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * rate)) / rate
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * 220 * t)).astype("float32"), rate)
    return path


@pytest.fixture(autouse=True)
def voice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dj.VoiceSetting:
    monkeypatch.setattr(dj, "UPLOADS_DIR", tmp_path / "uploads")
    setting = dj.VoiceSetting()
    monkeypatch.setattr(dj, "VOICE", setting)
    return setting


def test_starts_on_the_default_voice_with_no_reset_button() -> None:
    status, reset, _upload = settings.on_reset()
    assert status["value"] == settings.DEFAULT_ACTIVE
    assert reset["visible"] is False


def test_upload_shows_custom_voice_active(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    status, reset, upload = settings.on_upload(str(_clip(tmp_path / "me.mp3", 10)))
    assert "Custom voice active" in status["value"]
    assert reset["visible"] is True
    assert upload["value"] is None  # cleared, so the same file can be picked again
    assert voice.path is not None


def test_rejection_keeps_previous_voice_and_shows_reason(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    settings.on_upload(str(_clip(tmp_path / "me.wav", 10)))
    kept = voice.path
    status, reset, _upload = settings.on_upload(str(_clip(tmp_path / "me.ogg", 10)))
    assert "Only MP3 or WAV files are supported" in status["value"]
    assert "Still using your custom voice" in status["value"]
    assert reset["visible"] is True
    assert voice.path == kept


def test_rejection_on_the_default_voice_says_so(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    status, reset, _upload = settings.on_upload(str(_clip(tmp_path / "me.wav", 2)))
    assert "between 5 and 30 seconds" in status["value"]
    assert "Still using the default voice" in status["value"]
    assert reset["visible"] is False
    assert voice.path is None


def test_reset_button_shows_default(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    settings.on_upload(str(_clip(tmp_path / "me.wav", 10)))
    status, reset, _upload = settings.on_reset()
    assert status["value"] == settings.DEFAULT_ACTIVE
    assert reset["visible"] is False
    assert voice.path is None


def test_no_file_changes_nothing(voice: dj.VoiceSetting) -> None:
    status, _reset, _upload = settings.on_upload(None)
    assert status["value"] == settings.DEFAULT_ACTIVE
    assert voice.path is None


def test_an_unexpected_save_error_is_a_plain_message(
    tmp_path: Path, voice: dj.VoiceSetting, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_path: str) -> Path:
        raise OSError("disk full at C:\\secret\\place")

    monkeypatch.setattr(voice, "use", boom)
    status, _reset, _upload = settings.on_upload(str(_clip(tmp_path / "me.wav", 10)))
    assert "couldn't be saved" in status["value"]
    assert "secret" not in status["value"]


def test_render_builds_upload_status_and_reset() -> None:
    with gr.Blocks() as demo:
        settings.render()
    blocks = {getattr(b, "elem_id", None): b for b in demo.blocks.values()}
    assert {"dj-settings", "dj-voice-upload", "dj-voice-status", "dj-voice-reset"} <= set(blocks)
    assert set(blocks["dj-voice-upload"].file_types) == {".mp3", ".wav"}
