"""Reading a scanned PDF with OCR for Dogear to read, kept in the cache folder, so that
stopping part way loses nothing and reading the same file again needs no OCR at all.

`<cache>/ocr/<key>/` holds one PDF for each page read so far (`page-00001.pdf` and on):
the words Tesseract found, as invisible text where they are printed, without the
picture of the page, which Dogear doesn't read. Each is written under a temporary name
and renamed when complete. Once every page is read they are joined (pypdf) into
`text-layer.pdf`, written the same way, and the page files are deleted. The key is the
SHA-256 of the PDF's bytes together with the [ocr] settings and Tesseract's version, so
changing any of them reads the book again.

One run at a time works in a key's folder, holding the lock on its `in-use.lock`
(file_lock.py) while it reads pages or joins them. Another run on the same file waits,
saying so, then uses what the first one made. A run holding the lock first deletes the
temporary files of runs that were killed part way.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import time
from collections.abc import Iterator
from pathlib import Path

import pypdfium2
from pypdf import PdfWriter
from pypdf.errors import PyPdfError

from dogear.book_summary import count
from dogear.config import Config
from dogear.errors import ExtractionError
from dogear.file_lock import FileLock
from dogear.ocr.page import WORK_PREFIX, ocr_page, open_pdf
from dogear.ocr.progress import PROGRESS_EVERY_PAGES, TAKES_A_WHILE, OcrProgress
from dogear.ocr.settings import OcrSettings
from dogear.ocr.tesseract import Tesseract, find_tesseract
from dogear.paths import cache_dir
from dogear.render.progress import Report

FOLDER = "ocr"
LOCK_NAME = "in-use.lock"
TEXT_LAYER = "text-layer.pdf"
PARTIAL = ".part"
# Changes when what is kept changes, so an older cache is never read as a newer one.
FORMAT = 1
WAIT_POLL_SECONDS = 1.0
ALREADY_READ = "This PDF is scanned. Dogear read it with OCR before, so it uses that text."


def text_layer(path: Path, config: Config, report: Report) -> Path:
    """The text of the scanned PDF at `path`, read with OCR: a PDF with a page for each of
    its pages, holding that page's words where they are printed. Reads only the pages that
    weren't read before, reporting how it goes."""
    settings = OcrSettings.from_config(config)
    tesseract = find_tesseract(config, settings)
    folder = cache_dir(config) / FOLDER / cache_key(path, settings, tesseract)
    joined = folder / TEXT_LAYER
    if joined.is_file():  # complete: it's only ever renamed into place
        report(ALREADY_READ)
        return joined
    document = open_pdf(path)
    try:
        total = len(document)
        folder.mkdir(parents=True, exist_ok=True)
        with _working_in(folder, total, report):
            if joined.is_file():  # made by a run this one waited for
                report(ALREADY_READ)
                return joined
            _clear_leftovers(folder)
            _read_pages(document, folder, tesseract, settings, report)
            _join(folder, total, joined)
    finally:
        document.close()
    return joined


def cache_key(path: Path, settings: OcrSettings, tesseract: Tesseract) -> str:
    """What the text read from `path` with these settings is kept under."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    facts = {
        "format": FORMAT,
        "pdf": digest.hexdigest(),
        "language": settings.language,
        "dpi": settings.dpi,
        "max_page_pixels": settings.max_page_pixels,
        "tesseract": tesseract.version,
    }
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode("utf-8")).hexdigest()


def page_file(folder: Path, index: int) -> Path:
    return folder / f"page-{index + 1:05d}.pdf"


def _read_pages(
    document: pypdfium2.PdfDocument,
    folder: Path,
    tesseract: Tesseract,
    settings: OcrSettings,
    report: Report,
) -> None:
    total = len(document)
    missing = [index for index in range(total) if not page_file(folder, index).is_file()]
    if not missing:  # read before, but not joined
        report(ALREADY_READ)
        return
    report(
        f"This PDF is scanned, so Dogear is reading its {count(total, 'page')} with OCR, "
        f"{TAKES_A_WHILE}."
    )
    if len(missing) < total:
        report(
            f"Dogear read {total - len(missing):,} of the {total:,} pages before, so it "
            f"carries on from page {missing[0] + 1}."
        )
    progress = OcrProgress(total, total - len(missing), report)
    for index in missing:
        try:
            ocr_page(document, index, page_file(folder, index), tesseract, settings, text_only=True)
        except KeyboardInterrupt:
            report(
                f"Stopped reading with OCR at page {index + 1} of {total:,}. The pages read "
                "so far are kept, so running the same command again carries on from there."
            )
            raise
        progress.page_done()


def _join(folder: Path, total: int, joined: Path) -> None:
    """Join the pages into `joined`, then delete them. A page that can't be read was
    damaged in the cache folder; it's deleted, so the next run reads it again."""
    writer = PdfWriter()
    for index in range(total):
        page = page_file(folder, index)
        try:
            writer.append(str(page))
        except (PyPdfError, OSError, ValueError) as e:
            page.unlink(missing_ok=True)
            raise ExtractionError(
                f"The text Dogear read from page {index + 1} with OCR was damaged in its "
                f"cache folder ({e}).",
                hint="Try again: Dogear reads that page again.",
            ) from None
    partial = joined.with_name(f"{joined.name}.{os.getpid()}{PARTIAL}")
    with partial.open("wb") as file:
        writer.write(file)
    os.replace(partial, joined)
    for index in range(total):
        page_file(folder, index).unlink(missing_ok=True)


@contextlib.contextmanager
def _working_in(folder: Path, total: int, report: Report) -> Iterator[None]:
    """Hold the folder's lock, waiting for as long as another run holds it."""
    path = folder / LOCK_NAME
    lock = FileLock.try_acquire(path)
    if lock is None:
        report(
            "Another Dogear is reading this PDF with OCR now. This one waits for it to "
            "finish, then uses the text it read."
        )
        lock = _wait(path, folder, total, report)
    try:
        yield
    finally:
        lock.release()


def _wait(path: Path, folder: Path, total: int, report: Report) -> FileLock:
    """The lock, once the other run lets go of it. Meanwhile, how far that run has got is
    reported as often as it would report it itself."""
    told = _pages_read(folder)
    while (lock := FileLock.try_acquire(path)) is None:
        time.sleep(WAIT_POLL_SECONDS)
        done = _pages_read(folder)
        if done >= told + PROGRESS_EVERY_PAGES:
            report(f"The other Dogear has read {done:,} of {total:,} pages with OCR.")
            told = done
    return lock


def _pages_read(folder: Path) -> int:
    return sum(1 for _ in folder.glob("page-*.pdf"))


def _clear_leftovers(folder: Path) -> None:
    """Delete what runs that were killed part way left behind. Only for a run holding
    the folder's lock: no other run is using these."""
    for leftover in folder.iterdir():
        if leftover.name.startswith(WORK_PREFIX) and leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)
        elif leftover.name.endswith(PARTIAL):
            leftover.unlink(missing_ok=True)
