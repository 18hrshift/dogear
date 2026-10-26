"""Make short test WAVs with ffmpeg and inspect finished audio with ffprobe.

Audio is generated per test run and never committed. Loudness is checked with ffmpeg's
`loudnorm` analysis, a different meter from the `ebur128` one the code under test uses.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from conftest import require_tool
from PIL import Image


def _lavfi_wav(path: Path, source: str, rate: int) -> Path:
    ffmpeg = require_tool("ffmpeg")
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", source]
        + ["-ar", str(rate), "-ac", "1", "-c:a", "pcm_s16le", str(path)],
        check=True,
    )
    return path


def tone(path: Path, seconds: float, *, hz: int = 440, gain_db: float = 0.0, rate=24000) -> Path:
    """A sine tone. At gain 0 it measures about -21.7 LUFS with a -18.1 dBTP peak."""
    return _lavfi_wav(path, f"sine=frequency={hz}:duration={seconds},volume={gain_db}dB", rate)


def silence(path: Path, seconds: float, rate: int = 24000) -> Path:
    return _lavfi_wav(path, f"anullsrc=r={rate}:cl=mono,atrim=duration={seconds}", rate)


def spiky(path: Path, seconds: float, rate: int = 24000) -> Path:
    """A steady tone with a loud 2 ms burst every half second, like plosives in speech.

    About -20 LUFS with -1 dBTP peaks, so reaching -18 LUFS needs the limiter.
    """
    expr = "0.15*sin(2*PI*440*t)+0.75*sin(2*PI*1000*t)*lt(mod(t\\,0.5)\\,0.002)"
    return _lavfi_wav(path, f"aevalsrc='{expr}':s={rate}:d={seconds}", rate)


def probe(path: Path) -> dict:
    ffprobe = require_tool("ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-show_chapters"]
        + ["-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def loudness(path: Path, start: float | None = None, seconds: float | None = None):
    """(integrated LUFS, true peak dBTP) of a file, or of part of it."""
    ffmpeg = require_tool("ffmpeg")
    window = []
    if start is not None:
        window += ["-ss", f"{start:.3f}"]
    if seconds is not None:
        window += ["-t", f"{seconds:.3f}"]
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", *window, "-i", str(path), "-map", "0:a:0"]
        + ["-af", "loudnorm=print_format=json", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = json.loads(result.stderr[result.stderr.rfind("{") :])
    return float(report["input_i"]), float(report["input_tp"])


def image_bytes(fmt: str) -> bytes:
    """A tiny cover image, "JPEG" or "PNG"."""
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "teal").save(buffer, fmt)
    return buffer.getvalue()
