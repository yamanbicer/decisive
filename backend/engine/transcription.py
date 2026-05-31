"""Pitch-video → transcript via ElevenLabs Scribe STT.

Ported from jury-meeting/backend/voice.py. Scribe accepts video containers
(mp4/webm/mov) directly, so there's no ffmpeg/audio-extraction step. The
`elevenlabs` import is lazy (inside the function) so the app still boots and
every other route works when the package/key is absent — preserving the
zero-keys boot guarantee.
"""
from __future__ import annotations

import io

import weave

from ..config import get_settings


@weave.op()
def transcribe_media(data: bytes, filename: str = "pitch.mp4") -> str:
    """Transcribe uploaded audio/video bytes to text. Raises if no key is set."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    bio = io.BytesIO(data)
    bio.name = filename  # the SDK sniffs the format from the extension
    result = client.speech_to_text.convert(file=bio, model_id=settings.elevenlabs_stt_model)
    return (getattr(result, "text", "") or "").strip()
