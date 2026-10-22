"""Placeholder Generate tab. Lane B replaces the body of render()."""

from __future__ import annotations

import gradio as gr


def render() -> None:
    gr.Markdown(
        "Song generation is not connected yet. Style, mood, duration, and instrumental or vocal will go here.",
        elem_id="generate-panel",
    )
