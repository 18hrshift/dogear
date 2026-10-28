"""The audio of a talking book: one MP3 per section that every player can play.

Constant bitrate, mono, 44.1 kHz. DAISY 2.02 discourages variable bitrate; DAISY 3
players only have to play 44.1, 22.05, and 11.025 kHz; and EPUB's core MP3 type is
MPEG-1 audio (32, 44.1, or 48 kHz), which the voice's own 24 kHz isn't. 44.1 kHz is the
one rate all three accept. Resampling doesn't move anything in time, so the syncs, kept
in seconds, still line up.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dogear.config import Config
from dogear.readalong.model import SectionText
from dogear.tools import find_tool, run_tool

SAMPLE_RATE = 44100


def encode_talking_audio(
    sections: list[SectionText], work: Path, config: Config
) -> list[SectionText]:
    """The sections with their audio as MP3s in `work`, ready to copy into a book."""
    ffmpeg = find_tool("ffmpeg", config)
    bitrate = config["audio"]["talking_book_bitrate"]
    encoded = []
    for number, section in enumerate(sections, start=1):
        mp3 = work / f"talking-{number:05d}.mp3"
        run_tool(
            [ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(section.audio.path)]
            + ["-map", "0:a:0", "-map_metadata", "-1", "-ac", "1", "-ar", str(SAMPLE_RATE)]
            + ["-c:a", "libmp3lame", "-b:a", bitrate]
            # No ID3 tag: players read the book's own metadata, and a plain MP3 is the
            # safest thing to hand an old hardware player.
            + ["-id3v2_version", "0", "-f", "mp3", str(mp3)]
        )
        encoded.append(replace(section, audio=replace(section.audio, path=mp3)))
    return encoded
