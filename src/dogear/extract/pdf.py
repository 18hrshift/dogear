"""Read a PDF into a `Book`: metadata, print pages, chapters, and paragraphs.

pypdf reads the document catalog (metadata, bookmarks, page labels, encryption) and
pdfplumber reads the text with its positions and sizes. Each file is opened once per
library, and the pages are read in a single pass that every later step reuses.
PyMuPDF is not used because it is AGPL.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
from pdfminer.psparser import PSException
from pdfplumber.utils.exceptions import PdfminerException
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import Destination

from dogear.config import Config
from dogear.document import Book, Metadata
from dogear.errors import ConfigError, ExtractionError, ScannedPdfError
from dogear.extract.pdf_chapters import (
    Boundary,
    ChapterSource,
    check_methods,
    detect_chapters,
    is_section_label,
    mark_back_matter,
)
from dogear.extract.pdf_sections import build_sections
from dogear.extract.pdf_text import Line, Page, measure_layout, merge_drop_caps, strip_furniture

log = logging.getLogger(__name__)

OCR_HINT = "Run `dogear ocr <file>` first to add a text layer, then open the new file."
_DAMAGED_HINT = (
    "Check that the file opens in a PDF reader. If it does, save a new copy from there "
    "and open that copy instead."
)
_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")


@dataclass(frozen=True)
class PdfSettings:
    """The [pdf] config table, checked."""

    chapter_detection: tuple[str, ...]
    page_split_size: int
    heading_size_ratio: float
    min_chars_per_page: float
    running_line_min_pages: int
    running_line_min_share: float
    paragraph_gap_ratio: float
    paragraph_indent_ratio: float

    @classmethod
    def from_config(cls, config: Config) -> PdfSettings:
        table = config["pdf"]
        check_methods(table["chapter_detection"])
        settings = cls(
            chapter_detection=tuple(table["chapter_detection"]),
            page_split_size=table["page_split_size"],
            heading_size_ratio=table["heading_size_ratio"],
            min_chars_per_page=table["min_chars_per_page"],
            running_line_min_pages=table["running_line_min_pages"],
            running_line_min_share=table["running_line_min_share"],
            paragraph_gap_ratio=table["paragraph_gap_ratio"],
            paragraph_indent_ratio=table["paragraph_indent_ratio"],
        )
        _require("page_split_size", settings.page_split_size >= 1, "at least 1")
        _require("heading_size_ratio", settings.heading_size_ratio > 1, "more than 1")
        _require("min_chars_per_page", settings.min_chars_per_page >= 0, "0 or more")
        _require("running_line_min_pages", settings.running_line_min_pages >= 2, "at least 2")
        _require(
            "running_line_min_share", 0 < settings.running_line_min_share <= 1, "between 0 and 1"
        )
        _require("paragraph_gap_ratio", settings.paragraph_gap_ratio > 1, "more than 1")
        _require("paragraph_indent_ratio", settings.paragraph_indent_ratio > 0, "more than 0")
        return settings


def _require(key: str, ok: bool, what: str) -> None:
    if not ok:
        raise ConfigError(f"Setting 'pdf.{key}' must be {what}.")


@dataclass(frozen=True)
class _Catalog:
    """What pypdf reads from the file, apart from the text."""

    metadata: Metadata
    outline: list[list[tuple[int, str]]]
    labels: list[str]


def extract(path: Path, config: Config) -> Book:
    settings = PdfSettings.from_config(config)
    catalog = _read_catalog(path)
    pages = _read_pages(path, catalog.labels)
    _require_text_layer(path, pages, settings.min_chars_per_page)
    layout = measure_layout(
        pages,
        heading_ratio=settings.heading_size_ratio,
        gap_ratio=settings.paragraph_gap_ratio,
        indent_ratio=settings.paragraph_indent_ratio,
    )
    pages = strip_furniture(
        pages,
        layout,
        is_label=is_section_label,
        min_pages=settings.running_line_min_pages,
        min_share=settings.running_line_min_share,
    )
    source = ChapterSource(pages, catalog.outline, layout, settings.page_split_size)
    found = detect_chapters(settings.chapter_detection, source)
    if found is None:
        log.warning("No chapters found in %s, so it will be one section", path.name)
        boundaries = [Boundary(0, catalog.metadata.title)]
    else:
        boundaries = found[1]
    boundaries = mark_back_matter(boundaries, pages)
    sections = build_sections(pages, boundaries, layout, catalog.metadata.language)
    log.info("Read %d pages and %d sections from %s", len(pages), len(sections), path.name)
    return Book(metadata=catalog.metadata, sections=sections, source_path=path, source_format="pdf")


def _read_catalog(path: Path) -> _Catalog:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError(
                f"{path.name} is locked with a password.",
                hint="Open it with its password in a PDF reader, save a copy without the "
                "password, then open that copy.",
            )
        return _Catalog(
            metadata=_metadata(reader, path),
            outline=_outline(reader),
            labels=_labels(reader),
        )
    except PyPdfError as e:
        raise ExtractionError(
            f"Can't read {path.name}: it is damaged or not a PDF ({e}).", hint=_DAMAGED_HINT
        ) from e
    except OSError as e:
        raise ExtractionError(f"Can't open {path}: {e.strerror or e}.") from e


def _metadata(reader: PdfReader, path: Path) -> Metadata:
    info = reader.metadata
    title = " ".join(str(info.title or "").split()) if info else ""
    author = str(info.author or "") if info else ""
    return Metadata(
        title=title or path.stem,
        authors=[name.strip() for name in author.split(";") if name.strip()],
        language=_language(reader),
    )


def _language(reader: PdfReader) -> str | None:
    lang = reader.root_object.get("/Lang")
    if lang is None:
        return None
    tag = str(_resolve(lang)).strip()
    if _LANGUAGE_TAG.fullmatch(tag):
        return tag
    log.warning("Ignoring the PDF's language %r: it isn't a language tag such as 'en-GB'", tag)
    return None


def _outline(reader: PdfReader) -> list[list[tuple[int, str]]]:
    """Bookmarks that point at a page, grouped by depth: [top level, children, ...].

    pypdf lists an entry's children as a nested list right after the entry.
    """
    try:
        outline = reader.outline
    except PyPdfError as e:
        log.warning("Ignoring the PDF's bookmarks: they are damaged (%s)", e)
        return []
    levels: list[list[tuple[int, str]]] = []
    siblings: list[list[Any]] = [outline]
    while siblings:
        entries: list[tuple[int, str]] = []
        children: list[list[Any]] = []
        for group in siblings:
            for item in group:
                if isinstance(item, list):
                    children.append(item)
                elif isinstance(item, Destination):
                    page = reader.get_destination_page_number(item)
                    title = " ".join(str(item.title or "").split())
                    if page is not None and page >= 0 and title:
                        entries.append((page, title))
        levels.append(entries)
        siblings = children
    return levels


def _labels(reader: PdfReader) -> list[str]:
    """Printed page numbers from the PDF's page labels, or 1, 2, 3... if it has none."""
    count = len(reader.pages)
    if "/PageLabels" not in reader.root_object:
        return [str(i + 1) for i in range(count)]
    try:
        labels = list(reader.page_labels)
    except PyPdfError as e:
        log.warning("Ignoring the PDF's page labels: they are damaged (%s)", e)
        return [str(i + 1) for i in range(count)]
    # A label range may print nothing; a page marker still needs a name.
    return [label.strip() or str(i + 1) for i, label in enumerate(labels)]


def _resolve(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def _read_pages(path: Path, labels: list[str]) -> list[Page]:
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) != len(labels):
                log.warning(
                    "pypdf and pdfplumber disagree on the page count of %s (%d vs %d); "
                    "page labels may be off",
                    path.name,
                    len(labels),
                    len(pdf.pages),
                )
            pages = []
            for index, plumber_page in enumerate(pdf.pages):
                label = labels[index] if index < len(labels) else str(index + 1)
                pages.append(_read_page(plumber_page, index, label))
                plumber_page.close()  # frees the parsed page; big books stay small in memory
            return pages
    except (PdfminerException, PSException) as e:
        raise ExtractionError(
            f"Can't read the text in {path.name}: it is damaged ({e}).", hint=_DAMAGED_HINT
        ) from e


def _read_page(plumber_page: Any, index: int, label: str) -> Page:
    lines = []
    for raw in plumber_page.extract_text_lines(strip=True, return_chars=True):
        chars = [c for c in raw["chars"] if not c["text"].isspace()]
        text = " ".join(raw["text"].split())
        if not text or not chars:
            continue
        sizes = Counter(round(c["size"], 1) for c in chars)
        lines.append(
            Line(
                text=text,
                top=raw["top"],
                bottom=raw["bottom"],
                x0=raw["x0"],
                x1=raw["x1"],
                size=sizes.most_common(1)[0][0],
                chars=len(chars),
            )
        )
    return Page(
        index=index,
        label=label,
        lines=merge_drop_caps(lines),
        has_images=bool(plumber_page.images),
    )


def _require_text_layer(path: Path, pages: list[Page], min_chars: float) -> None:
    if not pages:
        raise ExtractionError(f"{path.name} has no pages.", hint=_DAMAGED_HINT)
    average = sum(page.char_count for page in pages) / len(pages)
    if average < min_chars or average == 0:
        raise ScannedPdfError(
            f"{path.name} has almost no text (about {average:.0f} characters a page), so it "
            "is probably scanned page images.",
            hint=OCR_HINT,
        )
    pictures = [page.label for page in pages if page.has_images and not page.lines]
    if pictures:
        log.warning(
            "Pages %s of %s are pictures with no text. Any words on them will be missing; "
            "if they are scanned pages, run `dogear ocr` on the file first.",
            ", ".join(pictures),
            path.name,
        )
