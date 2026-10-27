"""A folder of MP3s, one per chapter, with ID3 tags, the cover, and an M3U playlist.

This is the output for anything that plays audio files: car stereos, talking-book
players, and phones. Numbered file names keep the reading order even on players that
ignore the playlist.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from dogear.config import Config
from dogear.document import Metadata
from dogear.errors import OutputFolderError
from dogear.output.chapter import ChapterAudio
from dogear.output.cover import CoverInput, write_cover
from dogear.output.ffmpeg import probe_duration
from dogear.output.filenames import safe_filename, track_filenames
from dogear.output.folder_record import claim_folder, finish_folder
from dogear.output.languages import iso639_2
from dogear.output.loudness import LoudnessSettings, normalize_filter
from dogear.output.playlist import EXTENSION, PlaylistEntry, write_playlist
from dogear.output.tags import book_tags
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)


def build_mp3_folder(
    chapters: list[ChapterAudio],
    metadata: Metadata,
    folder: Path,
    config: Config,
    *,
    normalized: bool = False,
) -> list[Path]:
    """Write one loudness-normalized MP3 per chapter and a playlist into `folder`.
    `normalized` means `normalize_chapters` already set the loudness, so it's kept.

    Returns the MP3 paths in reading order. The folder is created if needed. Files that
    Dogear didn't make there are left alone; see `folder_record`.
    """
    if not chapters:
        raise ValueError("no chapters to package")
    ffmpeg = find_tool("ffmpeg", config)
    settings = LoudnessSettings.from_config(config)
    names = track_filenames([c.title for c in chapters], ".mp3")
    playlist_name = safe_filename(metadata.title, EXTENSION, fallback="playlist")
    _make_folder(folder)
    stale = claim_folder(folder, metadata, [*names, playlist_name])
    paths: list[Path] = []
    entries: list[PlaylistEntry] = []
    with tempfile.TemporaryDirectory(dir=folder, prefix=".dogear-") as tmp:
        work = Path(tmp)
        cover = write_cover(metadata.cover, work)
        for number, (chapter, name) in enumerate(zip(chapters, names, strict=True), start=1):
            label = f"Chapter {number} of {len(chapters)}"
            audio_filter = (
                "anull" if normalized else normalize_filter(chapter.path, label, settings, config)
            )
            # Encode into the work folder first, so a failed run never leaves a cut-off
            # track under a real name.
            partial = work / name
            run_tool(
                [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(chapter.path)]
                + (cover.input_args() if cover else [])
                + ["-map", "0:a:0", "-map_metadata", "-1", "-af", audio_filter]
                + ["-c:a", "libmp3lame", "-q:a", str(config["audio"]["mp3_quality"])]
                + _cover_args(cover)
                + _tag_args(metadata, chapter.title, number, len(chapters))
                + ["-f", "mp3", str(partial)]
            )
            seconds = probe_duration(partial, config)
            final = folder / name
            os.replace(partial, final)
            paths.append(final)
            entries.append(PlaylistEntry(name, chapter.title, seconds))
    write_playlist(folder / playlist_name, entries)
    finish_folder(folder, metadata, [*names, playlist_name], stale)
    log.info("Wrote %d MP3 files and %s to %s", len(paths), playlist_name, folder)
    return paths


def _make_folder(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        raise OutputFolderError(
            f"{folder} is a file, not a folder.",
            hint="Choose a folder for the MP3 files, or a name that doesn't exist yet.",
        ) from None


def _cover_args(cover: CoverInput | None) -> list[str]:
    if cover is None:
        return []
    # ID3 picture type comes from the stream comment: "Cover (front)" is type 3.
    return ["-map", "1:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"] + [
        "-metadata:s:v:0",
        "title=Cover",
        "-metadata:s:v:0",
        "comment=Cover (front)",
    ]


def _tag_args(metadata: Metadata, title: str, number: int, total: int) -> list[str]:
    tags = {"title": title.strip(), **book_tags(metadata), "track": f"{number}/{total}"}
    language = iso639_2(metadata.language)
    if language:
        tags["language"] = language
    args = []
    for key, value in tags.items():
        if value:
            args += ["-metadata", f"{key}={value}"]
    # ID3v2.3 rather than ffmpeg's default 2.4, which older Windows and many car stereos
    # can't read.
    return args + ["-id3v2_version", "3"]
