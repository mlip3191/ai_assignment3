"""Compose the jukebox page. Feature lanes fill in their own render() functions."""

from __future__ import annotations

import gradio as gr

from jukebox.ui import dj_settings, generate_tab, library_tab, player_panel

HOW_TO = "\n".join(
    [
        "# How to use",
        "",
        "The DJ voice is not connected yet, so songs play without a DJ intro for now.",
        "",
        "- **Play the samples.** Press **Play queue** once. "
        "The browser plays nothing until that click. The queue then advances on its own.",
        "- **Generate a song.** Choose style, mood, duration, and instrumental or vocal. "
        "The button stays disabled while it runs, and a status line names the stage. "
        "With an empty class queue, a short Qwen reply is about 1.5 seconds, "
        "an ACE-Step song is about 5 to 7 seconds, and a FLUX cover is about 2.3 seconds. "
        "A busy queue can take longer. "
        "When it finishes, **Play now** plays the new song at once and **Add to queue** puts it "
        "at the end of the queue. Every song is also listed in the **Library** tab.",
        "- **Change the DJ voice.** Keep the default voice, or upload an MP3 or WAV. "
        "A failed DJ intro still leaves the song. The DJ wait has not been measured.",
        "",
        "Generated songs stay available until you stop the app.",
    ]
)


def build_demo() -> gr.Blocks:
    # Gradio copies every file the page shows into its cache (runtime/uploads/gradio, set in launch.py):
    # check hourly and delete copies older than a day, so it can't grow forever.
    with gr.Blocks(title="AI Jukebox", delete_cache=(3600, 86400)) as demo:
        gr.Markdown(HOW_TO, elem_id="how-to")
        with gr.Row():
            with gr.Column():
                with gr.Tabs():
                    with gr.Tab("Generate", elem_id="generate-tab"):
                        generate = generate_tab.render(player_connected=True)
                    with gr.Tab("Library", elem_id="library-tab"):
                        library = library_tab.render()
            with gr.Column():
                panel = player_panel.render()
                voice = dj_settings.render()
        # Both tabs send a song to the player by its track id, so a song is never found by list position.
        panel.connect_add(generate.add_to_queue, generate.track_id)
        panel.connect_play_now(generate.play_now, generate.track_id)
        panel.connect_add(library.add_to_queue, library.selected)
        panel.connect_play_now(library.play_now, library.selected)
        # The DJ voice is app-wide: each page that opens shows it as it is now.
        voice.connect_load(demo)
    return demo
