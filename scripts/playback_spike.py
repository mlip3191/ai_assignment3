"""Option A playback spike (E1).

One gr.Audio plays three generated tones after a single Play click. The
component's stop event (end of media) advances the queue. Skip moves on
immediately and bumps a token so a late end event cannot advance twice.

Windows (PowerShell): .\\.venv\\Scripts\\python scripts\\playback_spike.py
macOS:                python scripts/playback_spike.py
"""

from __future__ import annotations

import math
import re
import shutil
import socket
import struct
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import gradio as gr

TONES = (440.0, 554.0, 659.0)
CLIP_SECONDS = 2.0
SAMPLE_RATE = 44100
LAUNCH = {"server_name": "127.0.0.1", "server_port": 7860, "share": False}
_TOKEN_IN_NAME = re.compile(r"^t(\d+)-")


@dataclass(frozen=True)
class QueueState:
    clips: tuple[Path, ...]
    index: int
    token: int


@dataclass(frozen=True)
class Step:
    index: int | None
    token: int
    path: Path | None
    status: str
    message: str


def write_clips(directory: Path) -> tuple[Path, Path, Path]:
    """Write three distinct 2-second tones and return their paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for freq in TONES:
        path = directory / f"clip-{int(freq)}hz.wav"
        _write_tone(path, freq)
        paths.append(path)
    return paths[0], paths[1], paths[2]


def new_queue(clips: Sequence[Path]) -> QueueState:
    return QueueState(tuple(Path(clip) for clip in clips), -1, 0)


def play(state: QueueState) -> tuple[QueueState, Step]:
    """Start at the first clip. A second Play does not restart the queue."""
    if state.index != -1:
        path = state.clips[state.index] if 0 <= state.index < len(state.clips) else None
        return state, Step(state.index if path else None, state.token, path, "ignored", "Already started.")
    started = QueueState(state.clips, 0, 1)
    return started, Step(0, 1, state.clips[0], "playing", _playing_message(started))


def advance(state: QueueState, event_token: int | None) -> tuple[QueueState, Step]:
    """Move to the next clip.

    event_token None is Skip and always applies to the current clip.
    An int is an end-of-media event. It is ignored when it is not the token
    of the clip that is playing now, so a late event cannot double-advance.
    """
    count = len(state.clips)
    if state.index < 0:
        return state, Step(None, state.token, None, "ignored", "Press Play queue first.")
    if state.index >= count:
        return state, Step(None, state.token, None, "finished", "Queue finished")
    if event_token is not None and event_token != state.token:
        return state, Step(
            state.index,
            state.token,
            state.clips[state.index],
            "ignored",
            f"ignored stale end event; still on clip {state.index + 1} of {count}",
        )
    nxt = state.index + 1
    moved = QueueState(state.clips, nxt, state.token + 1)
    if nxt >= count:
        return moved, Step(None, moved.token, None, "finished", "Queue finished")
    return moved, Step(nxt, moved.token, state.clips[nxt], "playing", _playing_message(moved))


def serve_for_browser(clip: Path, token: int) -> Path:
    """Copy a clip to a name that carries the play token, for the end event."""
    dest = clip.parent / f"t{token}-{clip.name}"
    if not dest.exists():
        shutil.copyfile(clip, dest)
    return dest


def token_from_audio(value: object) -> int | None:
    """Read the play token from a Gradio audio value, if the name has one."""
    path = _audio_path(value)
    if path is None:
        return None
    match = _TOKEN_IN_NAME.match(Path(path).name)
    if match is None:
        return None
    return int(match.group(1))


def build_demo(clips: Sequence[Path]) -> gr.Blocks:
    """Option A: one autoplay Audio, Play queue, and Skip."""
    queue = tuple(Path(clip) for clip in clips)

    def on_play(index: int, token: int) -> tuple[object, str, int, int]:
        state, step = play(QueueState(queue, int(index), int(token)))
        if step.status != "playing" or step.path is None:
            return gr.skip(), _stamp("play", step.message), int(token), int(index)
        served = serve_for_browser(step.path, step.token)
        return str(served), _stamp("play", step.message), step.token, step.index

    def on_skip(index: int, token: int) -> tuple[object, str, int, int]:
        state, step = advance(QueueState(queue, int(index), int(token)), None)
        return _audio_update(step), _stamp("skip", step.message), step.token, state.index

    def on_end(audio_value: object, index: int, token: int) -> tuple[object, str, int, int]:
        event_token = token_from_audio(audio_value)
        heard = Path(_audio_path(audio_value) or "").name
        if event_token is None:
            event_token = -1
        state, step = advance(QueueState(queue, int(index), int(token)), event_token)
        detail = f"{step.message} | file={heard or 'none'} parsed_token={event_token}"
        if step.status == "ignored":
            return gr.skip(), _stamp("end", detail), int(token), int(index)
        return _audio_update(step), _stamp("end", detail), step.token, state.index

    with gr.Blocks(title="Playback spike") as demo:
        gr.Markdown(
            "\n".join(
                [
                    "# Playback spike (Option A)",
                    "",
                    "Click **Play queue** once. Three tones should play in order, low then higher, "
                    "about 2 seconds each. Do not click again.",
                    "",
                    "The status line timestamps each end event and the next file. "
                    "The gap is the time between those two lines.",
                    "Skip during a tone should move to the next tone once.",
                    "Pause and resume use the controls on the single player.",
                ]
            )
        )
        status = gr.Textbox(label="Status", value="Idle. Click Play queue.", lines=6, elem_id="status")
        audio = gr.Audio(
            label="Now playing",
            type="filepath",
            autoplay=True,
            interactive=False,
            format="wav",
            elem_id="now-playing",
        )
        index = gr.State(-1)
        token = gr.State(0)
        play_btn = gr.Button("Play queue", elem_id="play-queue")
        skip_btn = gr.Button("Skip", elem_id="skip")
        play_btn.click(on_play, inputs=[index, token], outputs=[audio, status, token, index])
        skip_btn.click(on_skip, inputs=[index, token], outputs=[audio, status, token, index])
        audio.stop(on_end, inputs=[audio, index, token], outputs=[audio, status, token, index])
    return demo


def event_bindings(demo: gr.Blocks) -> set[tuple[str, str]]:
    """Return (elem_id, event name) pairs wired on this Blocks demo."""
    by_block_id: dict[int, str] = {}
    for block in demo.blocks.values():
        elem_id = getattr(block, "elem_id", None)
        block_id = getattr(block, "_id", None)
        if elem_id and block_id is not None:
            by_block_id[int(block_id)] = str(elem_id)

    found: set[tuple[str, str]] = set()
    for dep in _dependencies(demo):
        targets = getattr(dep, "targets", None)
        if targets is None and isinstance(dep, dict):
            targets = dep.get("targets")
        if not targets:
            continue
        for target in targets:
            if isinstance(target, (list, tuple)) and len(target) >= 2:
                elem_id = by_block_id.get(int(target[0]))
                if elem_id:
                    found.add((elem_id, str(target[1])))
                continue
            elem_id = getattr(target, "elem_id", None)
            event = getattr(dep, "event_name", None) or getattr(dep, "trigger", None)
            if elem_id and event:
                found.add((str(elem_id), str(event)))
    return found


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    clips = write_clips(root / "runtime" / "spike")
    port = int(LAUNCH["server_port"])
    if not _can_bind(str(LAUNCH["server_name"]), port):
        print(f"Port {port} is in use. Opening the spike on 7861 instead.")
        port = 7861
    print(f"Open http://{LAUNCH['server_name']}:{port} and click Play queue once.")
    demo = build_demo(clips)
    demo.launch(
        server_name=str(LAUNCH["server_name"]),
        server_port=port,
        share=False,
        allowed_paths=[str(clips[0].parent.resolve())],
    )


def _playing_message(state: QueueState) -> str:
    return f"playing clip {state.index + 1} of {len(state.clips)}"


def _audio_update(step: Step) -> object:
    if step.status != "playing" or step.path is None:
        return None
    return str(serve_for_browser(step.path, step.token))


def _stamp(event: str, message: str) -> str:
    now = datetime.now(UTC).isoformat(timespec="milliseconds")
    return f"{now} {event}: {message}"


def _audio_path(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, Path)):
        return str(value)
    if isinstance(value, dict):
        for key in ("path", "name", "orig_name"):
            item = value.get(key)
            if item:
                return str(item)
    named = getattr(value, "path", None)
    if named:
        return str(named)
    return None


def _dependencies(demo: gr.Blocks) -> list[object]:
    collected: list[object] = []
    for attr in ("fns", "dependencies"):
        raw = getattr(demo, attr, None)
        if not raw:
            continue
        collected.extend(raw.values() if isinstance(raw, dict) else list(raw))
    return collected


def _write_tone(path: Path, freq: float) -> None:
    count = int(SAMPLE_RATE * CLIP_SECONDS)
    amplitude = 0.2 * 32767
    frames = bytearray()
    for i in range(count):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)


def _can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


if __name__ == "__main__":
    main()
