"""Placeholder Library tab. Lane E fills this in when the library exists."""

from __future__ import annotations

import gradio as gr


def render() -> None:
    gr.Markdown(
        "The library will list the sample songs here. No samples are loaded in this shell.",
        elem_id="library-panel",
    )
