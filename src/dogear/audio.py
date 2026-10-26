"""Join audio files and package them as MP3 or M4B, using ffmpeg."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.document import Metadata
from dogear.errors import ToolFailedError
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChapterAudio:
    title: str
    path: Path


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


def concat_to_mp3(inputs: list[Path], output: Path, config: Config) -> None:
    """Join audio files in order into one MP3."""
    if not inputs:
        raise ValueError("no audio files to join")
    ffmpeg = find_tool("ffmpeg", config)
    output.parent.mkdir(parents=True, exist_ok=True)
    quality = str(config["audio"]["mp3_quality"])
    with tempfile.TemporaryDirectory() as tmp:
        listing = _write_concat_list(inputs, Path(tmp))
        run_tool(
            [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
            + ["-c:a", "libmp3lame", "-q:a", quality, str(output)]
        )
    log.info("Joined %d files into %s", len(inputs), output.name)


def build_m4b(
    chapters: list[ChapterAudio], metadata: Metadata, output: Path, config: Config
) -> None:
    """One M4B audiobook with a chapter marker at the start of each input file."""
    if not chapters:
        raise ValueError("no chapters to package")
    ffmpeg = find_tool("ffmpeg", config)
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = [probe_duration(c.path, config) for c in chapters]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        listing = _write_concat_list([c.path for c in chapters], tmp_dir)
        meta = tmp_dir / "chapters.txt"
        meta.write_text(
            ffmetadata(metadata, [c.title for c in chapters], durations), encoding="utf-8"
        )
        run_tool(
            [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
            + ["-i", str(meta), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
            + ["-c:a", "aac", "-b:a", config["audio"]["m4b_bitrate"], "-f", "mp4", str(output)]
        )
    log.info("Built %s with %d chapters", output.name, len(chapters))


def ffmetadata(metadata: Metadata, titles: list[str], durations: list[float]) -> str:
    """ffmpeg's FFMETADATA1 text: book tags plus one [CHAPTER] per title."""
    authors = ", ".join(metadata.authors)
    lines = [";FFMETADATA1"]
    for key, value in [
        ("title", metadata.title),
        ("album", metadata.title),
        ("artist", authors),
        ("album_artist", authors),
        ("genre", "Audiobook"),
    ]:
        if value:
            lines.append(f"{key}={_escape(value)}")
    elapsed = 0.0
    for title, duration in zip(titles, durations, strict=True):
        start = round(elapsed * 1000)
        elapsed += duration
        lines += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start}",
            f"END={round(elapsed * 1000)}",
            f"title={_escape(title)}",
        ]
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    # FFMETADATA treats these as syntax unless backslash-escaped.
    for char in ("\\", "=", ";", "#", "\n"):
        value = value.replace(char, "\\" + char)
    return value


def _write_concat_list(paths: list[Path], directory: Path) -> Path:
    # The concat demuxer reads single-quoted paths; a quote inside is written as '\''.
    listing = directory / "inputs.txt"
    lines = []
    for path in paths:
        quoted = path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{quoted}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing
