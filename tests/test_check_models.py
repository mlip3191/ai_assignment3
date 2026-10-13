"""Tests for scripts/check_models.py: only the four class models may be used."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_models import POLICY, scan  # noqa: E402


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def app(tmp_path: Path) -> Path:
    """A minimal, compliant app layout."""
    write(tmp_path, "requirements.txt", "gradio==5.0.0\nhttpx==0.27.0\nsoundfile==0.12.1\n")
    write(
        tmp_path,
        ".env.example",
        "CLASS_API_KEY=your-key\nQWEN_BASE_URL=http://HOST:9001\nFLUX_BASE_URL=http://HOST:9006\n"
        "ACESTEP_BASE_URL=http://HOST:9007\nCHATTERBOX_BASE_URL=http://HOST:9008\n",
    )
    write(tmp_path, "jukebox/clients/base.py", "import httpx\n")
    write(tmp_path, "jukebox/clients/qwen.py", "from .base import request\nURL_VAR = 'QWEN_BASE_URL'\n")
    write(tmp_path, "jukebox/clients/flux.py", "from .base import request\nURL_VAR = 'FLUX_BASE_URL'\n")
    write(tmp_path, "jukebox/clients/acestep.py", "from .base import request\nURL_VAR = 'ACESTEP_BASE_URL'\n")
    write(
        tmp_path,
        "jukebox/clients/chatterbox.py",
        "from .base import request\nURL_VAR = 'CHATTERBOX_BASE_URL'\n",
    )
    write(
        tmp_path,
        "jukebox/services/songs.py",
        "from jukebox.clients import qwen, acestep\ndef song_pipeline(): ...\n",
    )
    write(
        tmp_path,
        "jukebox/services/art.py",
        "from jukebox.clients import qwen\nfrom jukebox.clients.flux import x\n",
    )
    write(tmp_path, "jukebox/services/dj.py", "from ..clients import qwen, chatterbox\n")
    write(tmp_path, "jukebox/services/player.py", "from jukebox import library\n")
    write(tmp_path, "jukebox/ui/generate_tab.py", "from jukebox.services import songs\n")
    write(tmp_path, "app.py", "import gradio as gr\ndemo = gr.Blocks()\ndemo.launch(server_port=7860)\n")
    return tmp_path


def test_compliant_app_passes(app: Path) -> None:
    assert scan(app) == []


def test_policy_lists_exactly_the_four_class_models() -> None:
    models = {s["model"]: s["port"] for s in POLICY["services"].values()}
    assert models == {
        "Qwen3.6-35B-A3B": 9001,
        "FLUX.2 klein 4B": 9006,
        "ACE-Step 1.5 XL Turbo": 9007,
        "Chatterbox Multilingual V3": 9008,
    }
    assert 9000 in POLICY["forbidden_ports"]


@pytest.mark.parametrize(
    "rel,text,needle",
    [
        ("requirements.txt", "openai==1.0\n", "dependency 'openai'"),
        ("requirements.txt", "transformers>=4\n", "dependency 'transformers'"),
        ("requirements.txt", "edge_tts==6\n", "dependency 'edge-tts'"),
        ("jukebox/services/dj.py", "import pyttsx3\n", "imports 'pyttsx3'"),
        ("jukebox/services/art.py", "from diffusers import FluxPipeline\n", "imports 'diffusers'"),
        ("jukebox/services/songs.py", "from anthropic import Anthropic\n", "imports 'anthropic'"),
        ("jukebox/library.py", "URL = 'https://api.openai.com/v1/chat'\n", "api.openai.com"),
        ("app.py", "demo = gr.load('models/some/model')\n", "gr.load"),
        ("jukebox/ui/player.js", "speechSynthesis.speak(u)\n", "speechSynthesis"),
        ("jukebox/services/songs.py", "p = pipeline('text-generation')\n", "pipelines"),
        ("jukebox/services/songs.py", "import httpx\n", "network library 'httpx' outside jukebox/clients"),
        ("jukebox/services/songs.py", "from jukebox.clients import flux\n", "uses the 'flux' client"),
        ("jukebox/services/dj.py", "from jukebox.clients import acestep\n", "uses the 'acestep' client"),
        (
            "jukebox/services/player.py",
            "from jukebox.clients import chatterbox\n",
            "uses the 'chatterbox' client",
        ),
        ("jukebox/ui/generate_tab.py", "from jukebox.clients import qwen\n", "uses the 'qwen' client"),
        ("jukebox/clients/qwen.py", "URL = settings.FLUX_BASE_URL\n", "mentions 'FLUX_BASE_URL'"),
        ("jukebox/clients/flux.py", "# borrow the qwen client\n", "mentions 'qwen'"),
        ("jukebox/config.py", "DEFAULT = 'http://host:9002'\n", "hard-coded URL port 9002"),
        (".env.example", "QWEN_BASE_URL=http://HOST:9006\n", "QWEN_BASE_URL must use port 9001"),
        (".env.example", "FLUX_BASE_URL=http://HOST:9000\n", "port 9000, which is forbidden"),
        (".env.example", "WHISPER_BASE_URL=http://HOST:9010\n", "not one of the four class services"),
    ],
)
def test_violations_are_caught(app: Path, rel: str, text: str, needle: str) -> None:
    p = app / rel
    existing = p.read_text(encoding="utf-8") if p.exists() and rel.startswith(".env") else ""
    write(app, rel, existing + text)
    problems = scan(app)
    assert any(needle in x for x in problems), problems


def test_own_module_named_chatterbox_is_not_flagged(app: Path) -> None:
    # Our client module is jukebox.clients.chatterbox; only the local `chatterbox` TTS package is banned.
    write(
        app, "jukebox/services/dj.py", "from jukebox.clients import chatterbox\nimport jukebox.clients.qwen\n"
    )
    assert scan(app) == []


def test_real_repo_passes() -> None:
    assert scan(ROOT) == []
