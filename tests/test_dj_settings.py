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


def _gradio_copy(cache: Path, name: str, seconds: float) -> Path:
    """An upload where Gradio puts it: a folder inside its upload cache."""
    folder = cache / "3f2a9c"
    folder.mkdir(parents=True)
    return _clip(folder / name, seconds)


def test_gradios_copy_of_the_upload_is_deleted_once_saved(
    tmp_path: Path, voice: dj.VoiceSetting, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "gradio"
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(cache))
    upload = _gradio_copy(cache, "me.wav", 10)
    settings.on_upload(str(upload))
    assert not upload.exists()  # only the copy in runtime/uploads/ is kept
    assert Path(voice.path).exists()


def test_gradios_copy_of_a_rejected_upload_is_deleted_too(
    tmp_path: Path, voice: dj.VoiceSetting, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "gradio"
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(cache))
    upload = _gradio_copy(cache, "me.wav", 2)
    status, _reset, _upload = settings.on_upload(str(upload))
    assert "between 5 and 30 seconds" in status["value"]
    assert not upload.exists()
    assert voice.path is None


def test_a_file_outside_gradios_cache_is_never_deleted(
    tmp_path: Path, voice: dj.VoiceSetting, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRADIO_TEMP_DIR", str(tmp_path / "gradio"))
    mine = _clip(tmp_path / "mine.wav", 10)
    settings.on_upload(str(mine))
    assert mine.exists()


def test_a_reload_still_shows_the_custom_voice_and_reset(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    """The voice is app-wide, so a new page or a second tab must show it (@gunnaroc on #69)."""
    settings.on_upload(str(_clip(tmp_path / "me.wav", 10)))
    status, reset, _upload = settings.on_load()
    assert "Custom voice active" in status["value"]
    assert reset["visible"] is True


def test_a_reload_after_reset_shows_the_default_voice(tmp_path: Path, voice: dj.VoiceSetting) -> None:
    settings.on_upload(str(_clip(tmp_path / "me.wav", 10)))
    settings.on_reset()
    status, reset, _upload = settings.on_load()
    assert status["value"] == settings.DEFAULT_ACTIVE
    assert reset["visible"] is False


def _library_with(tmp_path: Path, make_track, *tracks: tuple[str, str]):
    """A library in tmp_path holding (id, source) tracks, each with a stand-in audio file."""
    from jukebox.library import Library

    library = Library(root=tmp_path)
    for track_id, source in tracks:
        audio = f"runtime/generated/{track_id}.mp3"
        (tmp_path / audio).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / audio).write_bytes(b"\x00")
        library.add(make_track(id=track_id, source=source, audio_path=audio))
    return library


def test_opening_a_page_warms_the_first_samples_intro(
    tmp_path: Path, make_track, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D5: Play queue starts with the first sample, so its intro is made before anyone presses Play."""
    library = _library_with(
        tmp_path, make_track, ("g1", "generated"), ("sample_01", "sample"), ("sample_02", "sample")
    )
    monkeypatch.setattr(settings, "get_library", lambda: library)
    asked: list[tuple[str, object]] = []
    monkeypatch.setattr(
        dj.PREFETCH, "prefetch", lambda track, previous=None, **_: asked.append((track.id, previous))
    )
    settings.on_load()
    assert asked == [("sample_01", None)]


def test_opening_a_page_with_no_samples_warms_nothing(
    tmp_path: Path, make_track, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _library_with(tmp_path, make_track, ("g1", "generated"))
    monkeypatch.setattr(settings, "get_library", lambda: library)
    asked: list[str] = []
    monkeypatch.setattr(dj.PREFETCH, "prefetch", lambda track, previous=None, **_: asked.append(track.id))
    settings.on_load()
    assert asked == []


def test_connect_load_refreshes_the_panel_when_a_page_opens() -> None:
    with gr.Blocks() as demo:
        panel = settings.render()
        panel.connect_load(demo)
    fns = demo.fns.values() if isinstance(demo.fns, dict) else demo.fns
    loads = [fn for fn in fns if (demo._id, "load") in [tuple(t) for t in fn.targets]]
    assert len(loads) == 1
    assert [o.elem_id for o in loads[0].outputs] == ["dj-voice-status", "dj-voice-reset", "dj-voice-upload"]


def test_render_builds_upload_status_and_reset() -> None:
    with gr.Blocks() as demo:
        settings.render()
    blocks = {getattr(b, "elem_id", None): b for b in demo.blocks.values()}
    assert {"dj-settings", "dj-voice-upload", "dj-voice-status", "dj-voice-reset"} <= set(blocks)
    assert set(blocks["dj-voice-upload"].file_types) == {".mp3", ".wav"}
