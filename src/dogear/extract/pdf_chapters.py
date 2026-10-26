"""Find where sections start in a PDF: the chapter detection cascade and back matter.

Each method returns boundaries, the pages where sections begin, in page order. Methods run
in the order `[pdf] chapter_detection` gives, and the first to find two or more wins.
All of them read pages that `pdf_text.strip_furniture` has already cleaned, so a page's
first line is its first line of real text, not a running header.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from dogear.document import SectionKind
from dogear.errors import ConfigError
from dogear.extract.pdf_text import ROMAN, Layout, Page, join_lines, leading_heading_lines

log = logging.getLogger(__name__)

_UNITS = "one|two|three|four|five|six|seven|eight|nine"
_TEENS = "ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
# A chapter number as digits, a roman numeral, or words up to "ninety-nine".
NUMBER = rf"(?:\d+|{ROMAN}|(?:{_TENS})(?:[- ](?:{_UNITS}))?|{_TEENS}|{_UNITS})"

# A line that is only a chapter label, such as "Chapter 3", "CHAPTER XII" or "Chapter Ten".
CHAPTER_DIVIDER = re.compile(rf"chapter\s+{NUMBER}[.:]?", re.IGNORECASE)

# Ported from audiobook-maker. Any of a page's first lines starting this way opens a section.
CHAPTER_PATTERNS = (
    re.compile(rf"^chapter\s+{NUMBER}\b", re.IGNORECASE),
    re.compile(rf"^part\s+{NUMBER}\b", re.IGNORECASE),
    re.compile(
        r"^(prologue|epilogue|introduction|preface|afterword|foreword"
        r"|acknowledgements?|conclusion|appendix)\b",
        re.IGNORECASE,
    ),
)
# How many of a page's first lines the pattern method looks at.
PATTERN_LINES = 5

_BACK_MATTER = re.compile(
    r"(acknowledge?ments?|bibliography|notes|endnotes|index|about the author"
    r"|by the same author|glossary|appendix|appendices|references|further reading)\b",
    re.IGNORECASE,
)
# A back-matter heading is short; a longer line starting "Notes ..." is a sentence.
_BACK_MATTER_MAX_WORDS = 8


class Boundary(NamedTuple):
    page: int  # 0-based page index
    title: str
    kind: SectionKind = "body"


@dataclass(frozen=True)
class ChapterSource:
    """Everything the detection methods look at."""

    pages: Sequence[Page]
    # Bookmarks by depth, top level first, each as (page index, title).
    outline: Sequence[Sequence[tuple[int, str]]]
    layout: Layout
    page_split_size: int


Method = Callable[[ChapterSource], list[Boundary]]


def is_back_matter_heading(text: str) -> bool:
    text = text.strip()
    return (
        _BACK_MATTER.match(text) is not None
        and text[:1].isupper()
        and len(text.split()) <= _BACK_MATTER_MAX_WORDS
    )


def is_section_label(text: str) -> bool:
    """Lines that detection relies on even in body type: "Chapter 3", "Notes", "Index"."""
    text = text.strip()
    return CHAPTER_DIVIDER.fullmatch(text) is not None or is_back_matter_heading(text)


def by_bookmarks(source: ChapterSource) -> list[Boundary]:
    """Bookmarks that point at a page, in page order, one per page.

    Uses the shallowest bookmark level with entries on two or more pages. Usually that is
    the top level. A book whose top level is one entry (the book's title) uses the level
    below it, its chapters. Two parts holding chapters stay two parts: a deeper level is
    used only when the one above it has fewer than two.
    """
    for level in source.outline:
        found = _bookmark_level(level, len(source.pages))
        if len(found) >= 2:
            return found
    return []


def _bookmark_level(entries: Sequence[tuple[int, str]], page_count: int) -> list[Boundary]:
    found: list[Boundary] = []
    for page, title in sorted(entries, key=lambda entry: entry[0]):
        if 0 <= page < page_count and not (found and found[-1].page == page):
            found.append(Boundary(page, title))
    return found


def by_chapter_dividers(source: ChapterSource) -> list[Boundary]:
    """Pages whose first line is only "Chapter N"."""

    def title(page: Page) -> str | None:
        first = page.lines[0].text.strip()
        return first if CHAPTER_DIVIDER.fullmatch(first) else None

    return _scan(source.pages, title)


def by_font_size(source: ChapterSource) -> list[Boundary]:
    """Pages that open with a line in heading type. The heading is the title."""

    def title(page: Page) -> str | None:
        count = leading_heading_lines(page.lines, source.layout)
        return join_lines(line.text for line in page.lines[:count]) if count else None

    return _scan(source.pages, title)


def by_pattern(source: ChapterSource) -> list[Boundary]:
    """Pages with a line like "Chapter 3", "Part One" or "Prologue" near the top."""

    def title(page: Page) -> str | None:
        for line in page.lines[:PATTERN_LINES]:
            text = line.text.strip()
            if any(pattern.match(text) for pattern in CHAPTER_PATTERNS):
                return text
        return None

    return _scan(source.pages, title)


def by_page_split(source: ChapterSource) -> list[Boundary]:
    """A part every `page_split_size` pages. Never fails: a short book is one part."""
    starts = range(0, len(source.pages), source.page_split_size)
    return [Boundary(start, f"Part {n}") for n, start in enumerate(starts, start=1)]


METHODS: dict[str, Method] = {
    "bookmarks": by_bookmarks,
    "chapter_dividers": by_chapter_dividers,
    "font_size": by_font_size,
    "pattern": by_pattern,
    "page_split": by_page_split,
}
# Accepted even when it finds a single section.
_ALWAYS_ACCEPTED = {"page_split"}


def check_methods(names: Sequence[str]) -> None:
    valid = ", ".join(METHODS)
    if not names:
        raise ConfigError(
            "Setting 'pdf.chapter_detection' lists no methods.", hint=f"Use some of: {valid}."
        )
    for name in names:
        if name not in METHODS:
            raise ConfigError(
                f"Unknown PDF chapter detection method '{name}' in 'pdf.chapter_detection'.",
                hint=f"Valid methods: {valid}.",
            )


def detect_chapters(
    names: Sequence[str], source: ChapterSource
) -> tuple[str, list[Boundary]] | None:
    """The first method in `names` to find two or more sections, with its boundaries."""
    check_methods(names)
    for name in names:
        boundaries = METHODS[name](source)
        if len(boundaries) >= 2 or (boundaries and name in _ALWAYS_ACCEPTED):
            log.info("Chapter detection '%s' found %d sections", name, len(boundaries))
            return name, boundaries
        log.debug("Chapter detection '%s' found %d sections", name, len(boundaries))
    return None


def mark_back_matter(boundaries: Sequence[Boundary], pages: Sequence[Page]) -> list[Boundary]:
    """Classify front and back matter instead of dropping it.

    A boundary titled like back matter ("Notes", "Index") is back matter, or front matter
    when it comes before the first chapter. After the last boundary, each page that opens
    with a back-matter heading ends the section before it and starts a back section.
    """
    is_back = [is_back_matter_heading(b.title) for b in boundaries]
    first_body = is_back.index(False) if False in is_back else len(boundaries)
    marked = [
        b._replace(kind=("front" if i < first_body < len(boundaries) else "back")) if back else b
        for i, (b, back) in enumerate(zip(boundaries, is_back, strict=True))
    ]
    for page in pages[marked[-1].page + 1 :] if marked else ():
        first = page.lines[0].text.strip() if page.lines else ""
        if is_back_matter_heading(first) and not _same_title(first, marked[-1].title):
            marked.append(Boundary(page.index, first, "back"))
    return marked


def _scan(pages: Sequence[Page], title_of: Callable[[Page], str | None]) -> list[Boundary]:
    found: list[Boundary] = []
    for page in pages:
        title = title_of(page) if page.lines else None
        # The same title on the next pages is a running header that survived cleanup.
        if title and not (found and _same_title(title, found[-1].title)):
            found.append(Boundary(page.index, title))
    return found


def _same_title(a: str, b: str) -> bool:
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())
