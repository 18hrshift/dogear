"""Turn a book file into a `dogear.document.Book`.

Each format module exposes `extract(path, config) -> Book`. Book files come from anywhere,
so extractors treat them as untrusted input: no network access, no external entities,
and nothing is unpacked to disk.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from dogear.config import Config
from dogear.document import Book
from dogear.errors import ScannedPdfError, UnsupportedFormatError
from dogear.render.progress import Report

log = logging.getLogger(__name__)

Extractor = Callable[[Path, Config], Book]


def _epub(path: Path, config: Config) -> Book:
    from dogear.extract import epub

    return epub.extract(path, config)


def _pdf(path: Path, config: Config) -> Book:
    from dogear.extract import pdf

    return pdf.extract(path, config)


def _kindle(path: Path, config: Config) -> Book:
    from dogear.extract import calibre

    return calibre.extract(path, config)


EXTRACTORS: dict[str, Extractor] = {
    ".epub": _epub,
    ".pdf": _pdf,
    ".mobi": _kindle,
    ".azw3": _kindle,
    ".azw": _kindle,
}


def extract_book(path: Path, config: Config, report: Report | None = None) -> Book:
    """The book in `path`. A scanned PDF is read with OCR first if pdf.auto_ocr is on,
    which can take many minutes: `report` hears how that goes (else it is logged)."""
    if not path.is_file():
        raise UnsupportedFormatError(
            f"No such file: {path}", hint="Check the file name and the folder it is in."
        )
    extractor = EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        supported = ", ".join(sorted(EXTRACTORS))
        raise UnsupportedFormatError(
            f"Dogear can't read {path.suffix or 'files without an extension'} files yet.",
            hint=f"Supported formats: {supported}.",
        )
    try:
        return extractor(path, config)
    except ScannedPdfError:
        if not config["pdf"]["auto_ocr"]:
            raise
    from dogear.extract import pdf

    return pdf.extract_scanned(path, config, report or log.info)
