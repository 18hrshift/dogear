"""One M4B audiobook: AAC audio, a chapter marker per section, tags, and the cover."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from dogear.config import Config
from dogear.document import Metadata
from dogear.output.chapter import ChapterAudio
from dogear.output.cover import write_cover
from dogear.output.ffmpeg import probe_duration, probe_sample_rate, write_concat_list
from dogear.output.languages import iso639_2
from dogear.output.loudness import LoudnessSettings, normalize_filter
from dogear.output.tags import book_tags
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)

# The iTunes "stik" tag; 2 means Audiobook, so Apple's apps file the book as one.
_MEDIA_TYPE_AUDIOBOOK = "2"


def build_m4b(
    chapters: list[ChapterAudio], metadata: Metadata, output: Path, config: Config
) -> None:
    """Normalize each chapter's loudness, join them, and write one M4B at `output`."""
    if not chapters:
        raise ValueError("no chapters to package")
    ffmpeg = find_tool("ffmpeg", config)
    settings = LoudnessSettings.from_config(config)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Work files sit next to the output: on the same disk (so the finished file moves into
    # place in one step) and not in a RAM-backed /tmp, since a long book's audio is large.
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".dogear-") as tmp:
        work = Path(tmp)
        normalized = _normalize_chapters(chapters, work, settings, config)
        # Marker times come from the normalized files, which are exactly what gets joined.
        durations = [probe_duration(wav, config) for wav in normalized]
        listing = write_concat_list(normalized, work)
        meta = work / "metadata.txt"
        meta.write_text(
            ffmetadata(metadata, [c.title for c in chapters], durations), encoding="utf-8"
        )
        cover = write_cover(metadata.cover, work)
        partial = work / "book.m4b"
        cmd = [ffmpeg, "-y", "-v", "error", "-nostdin", "-f", "concat", "-safe", "0"]
        cmd += ["-i", str(listing), "-i", str(meta)]
        cmd += cover.input_args() if cover else []
        cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
        if cover:
            cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
        cmd += ["-c:a", "aac", "-b:a", config["audio"]["m4b_bitrate"]]
        language = iso639_2(metadata.language)
        if language:
            cmd += ["-metadata:s:a:0", f"language={language}"]
        # faststart puts the index first, so players can start and seek before reading it all.
        cmd += ["-movflags", "+faststart", "-f", "mp4", str(partial)]
        run_tool(cmd)
        os.replace(partial, output)
    log.info("Built %s with %d chapters", output.name, len(chapters))


def _normalize_chapters(
    chapters: list[ChapterAudio], work: Path, settings: LoudnessSettings, config: Config
) -> list[Path]:
    """Each chapter at the target loudness, as a WAV in `work`, all at one sample rate."""
    ffmpeg = find_tool("ffmpeg", config)
    # The first chapter's rate for all of them, so the joined stream stays in time.
    sample_rate = probe_sample_rate(chapters[0].path, config)
    normalized = []
    for number, chapter in enumerate(chapters, start=1):
        audio_filter = normalize_filter(
            chapter.path, f"Chapter {number} of {len(chapters)}", settings, config
        )
        wav = work / f"{number:05d}.wav"
        run_tool(
            [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(chapter.path)]
            + ["-map", "0:a:0", "-af", audio_filter, "-ar", str(sample_rate)]
            + ["-c:a", "pcm_s16le", str(wav)]
        )
        normalized.append(wav)
    return normalized


def ffmetadata(metadata: Metadata, titles: list[str], durations: list[float]) -> str:
    """ffmpeg's FFMETADATA1 text: book tags plus one [CHAPTER] per title."""
    tags = {"title": metadata.title.strip(), **book_tags(metadata)}
    tags["media_type"] = _MEDIA_TYPE_AUDIOBOOK
    lines = [";FFMETADATA1"]
    lines += [f"{key}={_escape(value)}" for key, value in tags.items() if value]
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
