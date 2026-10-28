"""The DJ voice panel (F3b, D4): upload an MP3 or WAV to use as the DJ's voice, or reset to default.

The checks and storage live in jukebox.services.dj (VOICE); this module only shows the result. It
does not call a model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import gradio as gr
from gradio.utils import get_upload_folder

from jukebox.library import get_library
from jukebox.services import dj

log = logging.getLogger(__name__)

LIMITS = (
    f"MP3 or WAV, {dj.MIN_VOICE_S:g} to {dj.MAX_VOICE_S:g} seconds, "
    f"up to {dj.MAX_VOICE_BYTES // (1024 * 1024)} MB"
)
DEFAULT_ACTIVE = f"Default DJ voice. Upload a recording ({LIMITS}) to use your own."
CUSTOM_ACTIVE = "**Custom voice active.** New DJ intros use your recording."
SAVE_FAILED = "Your recording couldn't be saved. Try again."


def _current() -> str:
    return CUSTOM_ACTIVE if dj.VOICE.path else DEFAULT_ACTIVE


def _outputs(status: str) -> tuple[object, ...]:
    """status text, the Reset button (only with a custom voice), and a cleared upload box."""
    return (
        gr.update(value=status),
        gr.update(visible=dj.VOICE.path is not None),
        gr.update(value=None),
    )


def on_upload(file: str | None) -> tuple[object, ...]:
    if not file:
        return _outputs(_current())
    try:
        dj.VOICE.use(file)
    except dj.VoiceRejected as err:
        still = "Still using your custom voice." if dj.VOICE.path else "Still using the default voice."
        return _outputs(f"{err} {still}")
    except OSError as err:
        log.warning("voice upload not saved: %s", type(err).__name__)
        return _outputs(SAVE_FAILED)
    finally:
        _discard(file)
    return _outputs(CUSTOM_ACTIVE)


def _discard(file: str) -> None:
    """Delete Gradio's copy of the upload, so the saved voice in runtime/uploads/ is the only one (H9).

    Only a file inside Gradio's upload folder is deleted, never one from anywhere else.
    """
    path = Path(file).resolve()
    if not path.is_relative_to(Path(get_upload_folder()).resolve()):
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as err:
        log.warning("Gradio's copy of the upload not deleted: %s", type(err).__name__)


def on_reset() -> tuple[object, ...]:
    dj.VOICE.reset()
    return _outputs(DEFAULT_ACTIVE)


def on_load() -> tuple[object, ...]:
    """A page opening (a reload or a second tab) shows the app-wide voice as it is now, and warms
    the first sample's DJ intro (D5): Play queue starts with it, before anything else can prefetch."""
    first = next((track for track in get_library().list() if track.source == "sample"), None)
    if first is not None:
        dj.PREFETCH.prefetch(first)
    return _outputs(_current())


@dataclass(frozen=True)
class DjSettings:
    """What the page connects: connect_load() refreshes the panel each time a page opens."""

    outputs: tuple  # status, Reset, upload box, in _outputs() order

    def connect_load(self, demo: gr.Blocks) -> None:
        demo.load(on_load, outputs=list(self.outputs), show_progress="hidden")


def render() -> DjSettings:
    with gr.Group(elem_id="dj-settings"):
        upload = gr.File(
            label=f"DJ voice ({LIMITS})",
            file_types=list(dj.VOICE_TYPES),
            type="filepath",
            elem_id="dj-voice-upload",
        )
        status = gr.Markdown(_current(), elem_id="dj-voice-status")
        reset = gr.Button(
            "Reset to default", visible=dj.VOICE.path is not None, size="sm", elem_id="dj-voice-reset"
        )
    outputs = [status, reset, upload]
    upload.upload(on_upload, inputs=upload, outputs=outputs)
    reset.click(on_reset, outputs=outputs)
    return DjSettings(tuple(outputs))
