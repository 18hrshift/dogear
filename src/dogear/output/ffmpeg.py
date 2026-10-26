"""Small ffmpeg and ffprobe helpers shared by the packagers."""

from __future__ import annotations

from pathlib import Path

from dogear.config import Config
from dogear.errors import ToolFailedError
from dogear.tools import find_tool, run_tool


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
