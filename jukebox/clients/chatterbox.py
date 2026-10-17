"""DJ speech: the Chatterbox Multilingual V3 client (PROJECT.md 7.2), on CHATTERBOX_BASE_URL (port 9008).

The request format is the one measured in the D1 spike (docs/spikes/D1-chatterbox.md):

  POST /v1/audio/speech  (JSON, synchronous, one complete MP3 back)
  {"model": "chatterbox-v3", "input": <text>, "voice": "default", "language_id": "en",
   "response_format": "mp3", "ref_audio": <base64 WAV or MP3, only for a custom voice>}

  - The default voice is the service's own bundled voice (F3a). A custom voice sends the reference
    recording with every request (F3b). Never use the server's saved-voices endpoint: a voice saved
    there is visible to everyone on the shared class server.
  - One attempt only (`retry=False`). Speech is expensive and the queue is shared, so a retry after a
    timeout would ask for a second clip while the first may still be generating. The DJ service
    decides what to do on failure (skip the clip; the song still plays).
  - Inputs are checked before anything is sent, so a bad script or file never costs a server call.
"""

from __future__ import annotations

import base64
from pathlib import Path

from jukebox.clients.base import ServiceClient
from jukebox.errors import ServiceError

SPEECH_PATH = "/v1/audio/speech"
DEFAULT_MODEL = "chatterbox-v3"
DEFAULT_VOICE = "default"
RESPONSE_FORMAT = "mp3"
MAX_INPUT_CHARS = 4096  # server limit (D1)
MAX_REF_BYTES = 20 * 1024 * 1024  # server limit for a reference recording (D1)
REF_SUFFIXES = frozenset({".wav", ".mp3"})
REF_REJECTED_REASON = "the voice clip couldn't be used. Try a clear 5 to 30 second MP3 or WAV recording"


def _new_client() -> ServiceClient:
    """One client per call, bound to Chatterbox only. Tests replace this to use a test config."""
    return ServiceClient("chatterbox")


def speak(text: str, *, voice_ref_path: str | None = None, language: str = "en") -> tuple[bytes, str]:
    """Speak `text` in the default voice, or in the voice of the recording at `voice_ref_path`.

    Returns (mp3_bytes, "mp3"). Raises ServiceError(service="chatterbox") on any failure.
    """
    script = _check_text(text)
    body: dict[str, str] = {
        "input": script,
        "voice": DEFAULT_VOICE,
        "language_id": language,
        "response_format": RESPONSE_FORMAT,
    }
    if voice_ref_path is not None:
        body["ref_audio"] = base64.b64encode(_read_reference(Path(voice_ref_path))).decode("ascii")

    with _new_client() as client:
        body = {"model": client.model or DEFAULT_MODEL, **body}
        try:
            response = client.request("POST", SPEECH_PATH, json=body, retry=False)
        except ServiceError as err:
            if (
                voice_ref_path is not None
                and err.kind == "bad_request"
                and "reference" in (err.reason or "").lower()
            ):
                raise _bad_request(REF_REJECTED_REASON, err.detail) from None
            raise

    audio = response.content
    if not _looks_like_mp3(audio):
        raise ServiceError("chatterbox", "bad_response", f"expected MP3 audio, got {len(audio)} bytes")
    return audio, RESPONSE_FORMAT


# ---- helpers ------------------------------------------------------------------------------------


def _bad_request(reason: str, detail: str = "") -> ServiceError:
    return ServiceError("chatterbox", "bad_request", detail or reason, reason=reason)


def _check_text(text: str) -> str:
    script = (text or "").strip()
    if not script:
        raise _bad_request("the DJ script is empty")
    if len(script) > MAX_INPUT_CHARS:
        raise _bad_request(f"the DJ script is longer than {MAX_INPUT_CHARS} characters")
    return script


def _read_reference(path: Path) -> bytes:
    if path.suffix.lower() not in REF_SUFFIXES:
        raise _bad_request("the voice clip must be an MP3 or WAV file")
    if not path.is_file():
        raise _bad_request("the voice clip couldn't be found. Upload it again")
    size = path.stat().st_size
    if size == 0:
        raise _bad_request("the voice clip is empty")
    if size > MAX_REF_BYTES:
        raise _bad_request(f"the voice clip is too large (the limit is {MAX_REF_BYTES // (1024 * 1024)} MB)")
    return path.read_bytes()


def _looks_like_mp3(data: bytes) -> bool:
    """An ID3 tag, or an MPEG audio frame sync (11 set bits) at the start."""
    if data.startswith(b"ID3"):
        return True
    return len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
