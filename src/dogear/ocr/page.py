"""Reading one page of a PDF with OCR: draw it, hand the picture to Tesseract, keep the
one-page PDF it makes. `dogear ocr` and reading a scanned PDF automatically (cache.py)
both read pages this way.

A page is drawn at ocr.dpi unless that would make a picture bigger than
ocr.max_page_megapixels: a PDF can declare a page many feet across, and drawing it at 300
dpi could fill the computer's memory. Such a page is drawn at a lower resolution, and the
log says so.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pypdfium2

from dogear.errors import ExtractionError, ToolFailedError
from dogear.ocr.settings import OcrSettings
from dogear.ocr.tesseract import Tesseract, read_image

log = logging.getLogger(__name__)

WORK_PREFIX = "work-"  # the folder a page is read in, deleted after it
T = TypeVar("T")


def open_pdf(path: Path) -> pypdfium2.PdfDocument:
    """The PDF at `path`, open to draw its pages. Close it when done."""
    try:
        document = pypdfium2.PdfDocument(str(path))
    except pypdfium2.PdfiumError as e:
        raise ExtractionError(
            f"Couldn't open {path.name} as a PDF ({e}).",
            hint="The file may be damaged or password-protected.",
        ) from None
    if len(document) == 0:
        document.close()
        raise ExtractionError(f"{path.name} has no pages.")
    return document


def ocr_page(
    document: pypdfium2.PdfDocument,
    index: int,
    output: Path,
    tesseract: Tesseract,
    settings: OcrSettings,
    *,
    text_only: bool,
) -> None:
    """Read page `index` into `output`, a one-page PDF (see tesseract.read_image). The
    work is done in a new folder beside `output`, so `output` is renamed into place
    complete, or not written at all. A text-only page is drawn in grays: its picture
    isn't kept, and Tesseract reads gray as well as color."""
    dpi = _dpi(document, index, settings)
    folder = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=output.parent))
    try:
        picture = folder / "page.png"
        _draw(document, index, dpi, picture, grayscale=text_only)
        try:
            made = read_image(
                tesseract,
                picture,
                folder / "page",
                dpi=dpi,
                settings=settings,
                text_only=text_only,
            )
        except ToolFailedError as e:
            raise ToolFailedError(
                f"Tesseract couldn't read page {index + 1}. {e.message}",
                hint=_damaged_page_hint(index),
            ) from None
        os.replace(made, output)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def page_dpi(width_points: float, height_points: float, settings: OcrSettings) -> int:
    """The resolution to draw a page this size at: ocr.dpi, or less for a page so big that
    its picture would be over ocr.max_page_megapixels."""
    square_inches = (width_points / 72) * (height_points / 72)
    if square_inches * settings.dpi**2 <= settings.max_page_pixels:
        return settings.dpi
    return max(1, math.floor(math.sqrt(settings.max_page_pixels / square_inches)))


def _dpi(document: pypdfium2.PdfDocument, index: int, settings: OcrSettings) -> int:
    width, height = _page(document, index, lambda page: page.get_size())
    dpi = page_dpi(width, height, settings)
    if dpi < settings.dpi:
        log.warning(
            "Page %d is %s by %s inches, too big to read at %d dpi, so it is read at %d dpi.",
            index + 1,
            _inches(width),
            _inches(height),
            settings.dpi,
            dpi,
        )
    return dpi


def _inches(points: float) -> str:
    """'8.5', or '11' rather than '11.0'."""
    return f"{points / 72:.1f}".removesuffix(".0")


def _draw(
    document: pypdfium2.PdfDocument, index: int, dpi: int, picture: Path, *, grayscale: bool
) -> None:
    def draw(page: pypdfium2.PdfPage) -> None:
        page.render(scale=dpi / 72, grayscale=grayscale).to_pil().save(picture)

    _page(document, index, draw)


def _page(document: pypdfium2.PdfDocument, index: int, use: Callable[[pypdfium2.PdfPage], T]) -> T:
    """What `use` makes of page `index`, with a damaged page reported by its number."""
    try:
        page = document[index]
        try:
            return use(page)
        finally:
            page.close()
    except pypdfium2.PdfiumError as e:
        raise ExtractionError(
            f"Dogear couldn't draw page {index + 1} to read it with OCR ({e}).",
            hint=_damaged_page_hint(index),
        ) from None


def _damaged_page_hint(index: int) -> str:
    return (
        f"Check that page {index + 1} shows properly in a PDF reader. If it doesn't, save a "
        "new copy of the PDF from a reader that opens it, and use that copy."
    )
