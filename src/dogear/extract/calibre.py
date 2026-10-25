"""Read Kindle books (.mobi, .azw3, .azw) by converting them to EPUB with Calibre.

Calibre's `ebook-convert` writes the EPUB into a temporary folder that is removed as soon
as the EPUB has been read, so nothing is left behind.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import replace
from pathlib import Path

from dogear.config import Config
from dogear.document import Book
from dogear.errors import ExtractionError, ToolFailedError
from dogear.extract import epub
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)

# Long enough for a very large book on a slow machine. Not yet a config setting.
CONVERT_TIMEOUT_SECONDS = 600.0


def extract(path: Path, config: Config) -> Book:
    program = find_tool("ebook_convert", config)
    with tempfile.TemporaryDirectory(prefix="dogear-") as tmp:
        # Named after the original so a book with no title falls back to the right name.
        converted = Path(tmp) / f"{path.stem}.epub"
        log.info("Converting %s to EPUB with Calibre.", path.name)
        _convert(program, path, converted)
        if not converted.is_file():
            raise ExtractionError(
                f"Calibre finished converting {path.name} but didn't produce an EPUB.",
                hint="Try converting it to EPUB in Calibre yourself, then give Dogear the EPUB.",
            )
        book = epub.extract(converted, config)
    return replace(book, source_path=path, source_format=path.suffix.lower().lstrip("."))


def _convert(program: str, source: Path, target: Path) -> None:
    # Without --no-default-epub-cover, Calibre invents a cover image for books that have none.
    cmd = [program, str(source), str(target), "--no-default-epub-cover"]
    try:
        run_tool(cmd, timeout=CONVERT_TIMEOUT_SECONDS)
    except ToolFailedError as e:
        if "DRM" in e.message:
            raise ExtractionError(
                f"{source.name} is protected by DRM (copy protection), so Dogear can't read it.",
                hint=epub.DRM_HINT,
            ) from None
        raise
