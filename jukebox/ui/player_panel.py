"""Placeholder player. E4 wires the one audio element and the buttons."""

from __future__ import annotations

import gradio as gr


def render() -> None:
    gr.Markdown(
        "\n".join(
            [
                "**Now playing**",
                "",
                "Cover and title appear here when a song is chosen.",
                "",
                "Up next: the queue is not connected yet.",
            ]
        ),
        elem_id="player-panel",
    )
    gr.Audio(
        label="Now playing",
        type="filepath",
        autoplay=False,
        interactive=False,
        elem_id="now-playing",
    )
    gr.Button("Play queue", elem_id="play-queue", interactive=False)
    gr.Button("Skip", elem_id="skip", interactive=False)
