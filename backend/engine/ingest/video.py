"""Video (.mp4) extraction: audio track → bytes for ASR, and sampled keyframes →
JPEGs for the vision model. Uses imageio-ffmpeg's bundled static ffmpeg (no apt).

Graceful: a missing ffmpeg binary, a corrupt file, or a video with no audio stream
returns None / [] and the pipeline degrades (frames-only, or no video at all).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

import weave

_TIMEOUT_S = 180


def _ffmpeg() -> Optional[str]:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@weave.op()
def extract_audio(data: bytes) -> Optional[bytes]:
    """mp4 bytes → 16 kHz mono FLAC bytes (Groq's recommended preprocessing).

    Returns None if ffmpeg is unavailable or the file has no audio stream.
    """
    ff = _ffmpeg()
    if not ff:
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.mp4"), os.path.join(d, "out.flac")
        with open(src, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run(
                [ff, "-y", "-i", src, "-ar", "16000", "-ac", "1",
                 "-map", "0:a", "-c:a", "flac", dst],
                capture_output=True, timeout=_TIMEOUT_S)
        except Exception:
            return None
        if r.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as f:
            return f.read()


@weave.op()
def sample_frames(data: bytes, *, every_seconds: float = 20.0, max_frames: int = 12,
                  long_side: int = 768) -> list[bytes]:
    """Sample ~1 frame / every_seconds as JPEG bytes, hard-capped at max_frames."""
    ff = _ffmpeg()
    if not ff:
        return []
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as f:
            f.write(data)
        pattern = os.path.join(d, "f_%04d.jpg")
        try:
            subprocess.run(
                [ff, "-y", "-i", src, "-vf",
                 f"fps=1/{every_seconds},scale={long_side}:-1", "-q:v", "3", pattern],
                capture_output=True, timeout=_TIMEOUT_S)
        except Exception:
            return []
        frames: list[bytes] = []
        for name in sorted(os.listdir(d)):
            if name.startswith("f_") and name.endswith(".jpg"):
                with open(os.path.join(d, name), "rb") as f:
                    frames.append(f.read())
                if len(frames) >= max_frames:
                    break
        return frames
