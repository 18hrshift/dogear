"""Book-level tags that every output format writes the same way."""

from __future__ import annotations

from dogear.document import Metadata

GENRE = "Audiobook"


def book_tags(metadata: Metadata) -> dict[str, str]:
    """album, artist, album_artist and genre, as ffmpeg names them. Empty values are left out."""
    authors = ", ".join(a.strip() for a in metadata.authors if a.strip())
    tags = {
        "album": metadata.title.strip(),
        "artist": authors,
        "album_artist": authors,
        "genre": GENRE,
    }
    return {key: value for key, value in tags.items() if value}
