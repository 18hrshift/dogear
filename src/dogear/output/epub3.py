"""An EPUB 3 talking book: the book's text and its audio in step (Media Overlays).

Not built yet; this is the contract `make.py` calls.
"""

from __future__ import annotations

from pathlib import Path

from dogear.config import Config
from dogear.document import Metadata
from dogear.readalong.model import SectionText


def build_epub3(
    sections: list[SectionText], metadata: Metadata, path: Path, config: Config
) -> None:
    """Write the talking book to `path`, a .epub file.

    `sections` come from `readalong.build_readalong`, in reading order, with their audio
    already encoded by `talking_audio` (each `section.audio.path` is the MP3 to put in
    the book) and the syncs that tie their text to it, in seconds.
    """
    raise NotImplementedError("EPUB 3 output is not built yet")
