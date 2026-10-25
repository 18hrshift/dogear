"""Add a text layer to a scanned PDF so the PDF extractor can read it.

Each page is rendered to an image, Tesseract turns it into a one-page PDF with the image
plus invisible text in the right positions, and the pages are joined. Keeping positions
and sizes means chapter detection by font size and layout still works afterwards.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

import pypdfium2
from pypdf import PdfReader, PdfWriter

from dogear.config import Config
from dogear.errors import DogearError, ExtractionError, ToolFailedError
from dogear.tools import find_tool, run_tool

log = logging.getLogger(__name__)

Progress = Callable[[int, int], None]  # (pages done, total pages)


def default_output_path(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}_ocr.pdf")


def ocr_pdf(
    input_pdf: Path, output_pdf: Path, config: Config, progress: Progress | None = None
) -> int:
    """OCR every page of `input_pdf` into `output_pdf`. Returns the page count."""
    if input_pdf.resolve() == output_pdf.resolve():
        raise DogearError(
            "The OCR output would overwrite the original PDF.", hint="Choose another output file."
        )
    tesseract = find_tool("tesseract", config)
    dpi, language = config["ocr"]["dpi"], config["ocr"]["language"]
    source = _open(input_pdf)
    writer = PdfWriter()
    total = len(source)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(total):
                page_pdf = _ocr_page(source[index], index, Path(tmp), tesseract, dpi, language)
                writer.append(str(page_pdf))
                if progress:
                    progress(index + 1, total)
    finally:
        source.close()
    _copy_metadata(input_pdf, writer)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as f:
        writer.write(f)
    log.info("OCR finished: %d pages written to %s", total, output_pdf)
    return total


def _open(path: Path) -> pypdfium2.PdfDocument:
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


def _ocr_page(
    page: pypdfium2.PdfPage, index: int, tmp: Path, tesseract: str, dpi: int, language: str
) -> Path:
    image = tmp / f"page{index:05d}.png"
    page.render(scale=dpi / 72).to_pil().save(image)
    out_base = tmp / f"page{index:05d}"
    try:
        run_tool([tesseract, str(image), str(out_base), "-l", language, "--dpi", str(dpi), "pdf"])
    except ToolFailedError as e:
        if "Failed loading language" in e.message:
            raise ToolFailedError(
                e.message,
                hint=f"Tesseract doesn't have the language data for '{language}'. Install it "
                "(for example: sudo apt install tesseract-ocr-fra) or change ocr.language.",
            ) from None
        raise
    finally:
        image.unlink(missing_ok=True)
    return out_base.with_suffix(".pdf")


def _copy_metadata(input_pdf: Path, writer: PdfWriter) -> None:
    try:
        metadata = PdfReader(str(input_pdf)).metadata
    except Exception as e:  # metadata is a nicety; a broken info dict shouldn't stop OCR
        log.warning("Couldn't copy metadata from %s: %s", input_pdf.name, e)
        return
    if metadata:
        writer.add_metadata({k: str(v) for k, v in metadata.items()})
