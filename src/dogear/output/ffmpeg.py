"""Small ffmpeg and ffprobe helpers shared by the packagers."""

from __future__ import annotations

from pathlib import Path

from dogear.config import Config
from dogear.errors import ToolFailedError, ToolNotFoundError
from dogear.tools import TOOLS, find_tool, run_tool


def check_ffmpeg(config: Config) -> None:
    """Fail now, not after hours of speaking, if ffmpeg can't package a book.

    The peak limiter's `latency` option (see `loudness.py`) arrived in ffmpeg 5.1.
    """
    ffmpeg = find_tool("ffmpeg", config)
    find_tool("ffprobe", config)
    options = run_tool([ffmpeg, "-hide_banner", "-h", "filter=alimiter"]).stdout
    if "latency" not in options:
        raise ToolNotFoundError(
            "This ffmpeg is too old for Dogear, which needs version 5.1 or newer.",
            hint=TOOLS["ffmpeg"][1],
        )


def probe_duration(path: Path, config: Config) -> float:
    """Length of an audio file in seconds. Fails rather than guessing."""
    ffprobe = find_tool("ffprobe", config)
    result = run_tool(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise ToolFailedError(f"ffprobe couldn't read the length of {path.name}.") from None


def probe_sample_rate(path: Path, config: Config) -> int:
    """Sample rate of the first audio stream, in Hz."""
    ffprobe = find_tool("ffprobe", config)
    result = run_tool(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate"]
        + ["-of", "csv=p=0", str(path)]
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        raise ToolFailedError(f"ffprobe couldn't read the sample rate of {path.name}.") from None


def write_concat_list(paths: list[Path], directory: Path) -> Path:
    """An input list for ffmpeg's concat demuxer, which joins the files in order."""
    # The concat demuxer reads single-quoted paths; a quote inside is written as '\''.
    listing = directory / "inputs.txt"
    lines = []
    for path in paths:
        quoted = path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{quoted}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing
