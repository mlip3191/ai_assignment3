"""Compose the jukebox page. Feature lanes fill in their own render() functions."""

from __future__ import annotations

import gradio as gr

from jukebox.ui import dj_settings, generate_tab, library_tab, player_panel

HOW_TO = "\n".join(
    [
        "# How to use",
        "",
        "These controls are not connected yet. This page is the shell the rest of the jukebox plugs into.",
        "",
        "- **Play the samples.** When the player is connected, press **Play queue** once. "
        "The browser plays nothing until that click. The queue then advances on its own.",
        "- **Generate a song.** Choose style, mood, duration, and instrumental or vocal. "
        "The button stays disabled while it runs, and a status line names the stage. "
        "With an empty class queue, a short Qwen reply is about 1.5 seconds, "
        "an ACE-Step song is about 5 to 7 seconds, and a FLUX cover is about 2.3 seconds. "
        "A busy queue can take longer.",
        "- **Change the DJ voice.** Keep the default voice, or upload an MP3 or WAV. "
        "A failed DJ intro still leaves the song. The DJ wait has not been measured.",
        "",
        "Generated songs stay available until you stop the app.",
    ]
)


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="AI Jukebox") as demo:
        gr.Markdown(HOW_TO, elem_id="how-to")
        with gr.Row():
            with gr.Column():
                with gr.Tabs():
                    with gr.Tab("Generate", elem_id="generate-tab"):
                        generate_tab.render()
                    with gr.Tab("Library", elem_id="library-tab"):
                        library_tab.render()
            with gr.Column():
                player_panel.render()
                dj_settings.render()
    return demo
