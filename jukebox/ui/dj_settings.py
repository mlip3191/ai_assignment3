"""Placeholder DJ settings. Lane D replaces the body of render()."""

from __future__ import annotations

import gradio as gr


def render() -> None:
    gr.Markdown(
        "DJ voice is not connected yet. The default voice will be used, or you can upload an MP3 or WAV later. "
        "Uploads stay in runtime/uploads and are not saved in the repo.",
        elem_id="dj-settings",
    )
