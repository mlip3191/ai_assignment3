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
EXAGGERATION_RANGE = (0.0, 2.0)  # server minimum is 0; above 2 the model's delivery breaks down
CFG_WEIGHT_RANGE = (0.0, 1.0)  # server range


def _new_client() -> ServiceClient:
    """One client per call, bound to Chatterbox only. Tests replace this to use a test config."""
    return ServiceClient("chatterbox")


def speak(
    text: str,
    *,
    voice_ref_path: str | None = None,
    language: str = "en",
    exaggeration: float | None = None,
    cfg_weight: float | None = None,
) -> tuple[bytes, str]:
    """Speak `text` in the default voice, or in the voice of the recording at `voice_ref_path`.

    `exaggeration` (more energy, 0 to 2) and `cfg_weight` (lower is looser and more dramatic, 0 to 1)
    are the service's delivery controls. Left as None, they're not sent and the service defaults apply.

    Returns (mp3_bytes, "mp3"). Raises ServiceError(service="chatterbox") on any failure.
    """
    script = _check_text(text)
    body: dict[str, str | float] = {
        "input": script,
        "voice": DEFAULT_VOICE,
        "language_id": language,
        "response_format": RESPONSE_FORMAT,
    }
    if exaggeration is not None:
        body["exaggeration"] = _check_range("exaggeration", exaggeration, EXAGGERATION_RANGE)
    if cfg_weight is not None:
        body["cfg_weight"] = _check_range("cfg_weight", cfg_weight, CFG_WEIGHT_RANGE)
    if voice_ref_path is not None:
        body["ref_audio"] = base64.b64encode(_read_reference(Path(voice_ref_path))).decode("ascii")

    with _new_client() as client:
        body = {"model": client.model or DEFAULT_MODEL, **body}
        try:
            response = client.request("POST", SPEECH_PATH, json=body, retry=False)
        except ServiceError as err:
            # A 404 stays kind="config" (the base mapping) on purpose: we always send voice="default",
            # so a 404 means a wrong base URL or path, not a missing voice.
            if voice_ref_path is not None and _is_reference_rejection(err):
                raise _bad_request(REF_REJECTED_REASON, err.detail) from None
            raise

    audio = response.content
    if not _looks_like_mp3(audio):
        raise ServiceError("chatterbox", "bad_response", f"expected MP3 audio, got {len(audio)} bytes")
    return audio, RESPONSE_FORMAT


# ---- helpers ------------------------------------------------------------------------------------


def _is_reference_rejection(err: ServiceError) -> bool:
    """A 400 about the voice clip: the server's `invalid_reference` code (it's in the error detail,
    which holds the start of the response body), or, as a fallback, its message mentioning the reference."""
    if err.kind != "bad_request":
        return False
    return "invalid_reference" in err.detail or "reference" in (err.reason or "").lower()


def _bad_request(reason: str, detail: str = "") -> ServiceError:
    return ServiceError("chatterbox", "bad_request", detail or reason, reason=reason)


def _check_text(text: str) -> str:
    script = (text or "").strip()
    if not script:
        raise _bad_request("the DJ script is empty")
    if len(script) > MAX_INPUT_CHARS:
        raise _bad_request(f"the DJ script is longer than {MAX_INPUT_CHARS} characters")
    return script


def _check_range(name: str, value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    if not low <= value <= high:
        raise _bad_request(f"{name} must be between {low:g} and {high:g}")
    return value


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
