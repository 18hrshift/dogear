"""Turn a book file into a `dogear.document.Book`.

Each format module exposes `extract(path, config) -> Book`. Book files come from anywhere,
so extractors treat them as untrusted input: no network access, no external entities,
and nothing is unpacked to disk.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dogear.config import Config
from dogear.document import Book
from dogear.errors import UnsupportedFormatError

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


def extract_book(path: Path, config: Config) -> Book:
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
    return extractor(path, config)
