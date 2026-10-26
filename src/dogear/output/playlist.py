"""The M3U playlist that lists an MP3 folder's tracks in reading order.

Format choices, for the widest range of players:

- Extension `.m3u`, not `.m3u8`. Car stereos and hardware talking-book players often
  recognize only `.m3u`, and `.m3u8` is also the extension of HTTP Live Streaming
  playlists, which some players handle as a stream.
- UTF-8 text without a byte-order mark. Phones, VLC, and foobar2000 read UTF-8 playlists;
  a byte-order mark can hide the `#EXTM3U` header from simple parsers. A player that reads
  `.m3u` in a legacy Windows code page garbles non-English titles, but the tracks still
  play in order from the numbered file names.
- Windows (CRLF) line endings, the form most playlists in the wild use, so firmware
  parsers expect it and desktop parsers accept it.
- Paths relative to the playlist (file names only), so the folder can be copied anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXTENSION = ".m3u"


@dataclass(frozen=True)
class PlaylistEntry:
    filename: str  # relative to the playlist
    title: str
    seconds: float


def m3u_text(entries: list[PlaylistEntry]) -> str:
    """Extended M3U: a header, then an #EXTINF line and a file name per track."""
    lines = ["#EXTM3U"]
    for entry in entries:
        title = " ".join(entry.title.split())  # a line break would end the entry early
        lines.append(f"#EXTINF:{round(entry.seconds)},{title}")
        lines.append(entry.filename)
    return "\r\n".join(lines) + "\r\n"


def write_playlist(path: Path, entries: list[PlaylistEntry]) -> None:
    # newline="" writes the CRLFs as they are, on every platform.
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(m3u_text(entries))
