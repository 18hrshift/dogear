"""Remove print furniture from PDF pages: page numbers and running headers and footers.

Works on lines that `dogear.extract.pdf` has already read. A page's edge is its first or
last lines, read from the edge inward, so the same rules serve headers and footers.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from dogear.extract.pdf_text import ROMAN, Layout, Line, Page

log = logging.getLogger(__name__)

_PAGE_NUMBER = re.compile(rf"[\[(\-–—\s]*(?:\d{{1,4}}|{ROMAN})[\])\-–—\s]*")
_EDGE_ROMAN = re.compile(rf"^{ROMAN}\b|\b{ROMAN}$")
_DIGITS = re.compile(r"\d+")


def is_page_number(text: str) -> bool:
    return _PAGE_NUMBER.fullmatch(text) is not None


def running_key(text: str) -> str:
    """Text compared across pages to spot running headers: digits and case ignored."""
    text = _EDGE_ROMAN.sub("#", text.strip())  # before casefolding: only lowercase numerals
    return " ".join(_DIGITS.sub("#", text.casefold()).split())


def strip_furniture(
    pages: Sequence[Page],
    layout: Layout,
    *,
    is_label: Callable[[str], bool],
    min_pages: int,
    min_share: float,
    max_lines: int,
) -> list[Page]:
    """Drop page numbers and running headers and footers from the top and bottom of pages.

    A running header or footer is a block of up to `max_lines` lines at a page's edge, set
    apart from the text block by more than a paragraph gap, such as the book's title with
    the chapter's title under it. A line in that block is running when its `running_key`
    comes back at a page edge on at least `min_pages` pages, and on at least `min_share` of
    the pages from its first appearance to its last. The share keeps a line that happens
    to repeat far apart, such as a scene-break ornament.

    Each line is judged on its own, and removal stops at the first line that stays, so a
    first line of real text is never removed unless it repeats like a header. Lines in
    heading type are never removed. Lines that `is_label` (such as "Chapter 3") are matched
    on their exact text instead, and their first appearance is kept, because that is where
    the section opens; chapter detection depends on it.
    """
    edges = _Edges(layout, is_label, max_lines)
    tops: list[tuple[int, Line]] = []
    bottoms: list[tuple[int, Line]] = []
    for page in pages:
        tops += [(page.index, line) for line in edges.candidates(page.lines)]
        bottoms += [(page.index, line) for line in edges.candidates(page.lines[::-1])]
    headers = _running(tops, edges.key, is_label, min_pages, min_share)
    footers = _running(bottoms, edges.key, is_label, min_pages, min_share)
    cleaned = []
    for page in pages:
        start = edges.trim(page.lines, headers, page.index)
        rest = page.lines[start:]
        end = len(rest) - edges.trim(rest[::-1], footers, page.index)
        cleaned.append(replace(page, lines=rest[:end]))
    removed = sum(len(page.lines) for page in pages) - sum(len(page.lines) for page in cleaned)
    log.info("Removed %d page-number, header, and footer lines", removed)
    return cleaned


@dataclass(frozen=True)
class _Edges:
    """The rules for one edge of a page. Each method gets the page's lines in order from
    that edge inward: as printed for the top, reversed for the bottom."""

    layout: Layout
    is_label: Callable[[str], bool]
    max_lines: int

    def key(self, line: Line) -> str:
        # The prefix keeps a label's exact text apart from normalized keys.
        if self.is_label(line.text):
            return f"label:{line.text.casefold()}"
        return running_key(line.text)

    def candidates(self, edge: Sequence[Line]) -> list[Line]:
        """The lines that may be a running header or footer here, for counting."""
        start = 0
        while start < len(edge) and self._page_number(edge[start:], self.max_lines):
            start += 1
        edge = edge[start:]
        found = []
        for i in range(min(self.max_lines, len(edge))):
            line = edge[i]
            heading = self.layout.is_heading(line)
            # A large "Notes" opening counts as the first "NOTES" header, so it is the one kept.
            if (not heading and self._apart(edge[i:], self.max_lines - i)) or (
                heading and self.is_label(line.text)
            ):
                found.append(line)
        return found

    def trim(self, edge: Sequence[Line], running: dict[str, int | None], index: int) -> int:
        """How many lines to drop from this edge of page `index`."""
        start = used = 0
        while start < len(edge):
            rest = edge[start:]
            budget = self.max_lines - used
            # A page number doesn't use up the budget, so one can sit beside a full header.
            if self._page_number(rest, max(budget, 1)):
                start += 1
            elif budget > 0 and self._running(rest, budget, running, index):
                start += 1
                used += 1
            else:
                break
        return start

    def _page_number(self, edge: Sequence[Line], budget: int) -> bool:
        line = edge[0]
        return (
            not self.layout.is_heading(line)
            and not self.is_label(line.text)
            and is_page_number(line.text)
            and self._apart(edge, budget)
        )

    def _running(
        self, edge: Sequence[Line], budget: int, running: dict[str, int | None], index: int
    ) -> bool:
        line = edge[0]
        if self.layout.is_heading(line) or not self._apart(edge, budget):
            return False
        k = self.key(line)
        return k in running and running[k] != index

    def _apart(self, edge: Sequence[Line], budget: int) -> bool:
        """Whether `edge[0]` is in a block of at most `budget` lines at the edge that is set
        apart from the lines after it by more than a paragraph gap."""
        for size in range(1, budget + 1):
            if size >= len(edge):
                return True
            if abs(edge[size].bottom - edge[size - 1].bottom) > self.layout.paragraph_gap:
                return True
        return False


def _running(
    edges: Sequence[tuple[int, Line]],
    key: Callable[[Line], str],
    is_label: Callable[[str], bool],
    min_pages: int,
    min_share: float,
) -> dict[str, int | None]:
    """Running line keys, each mapped to the one page where it is kept (None: nowhere)."""
    pages_by_key: dict[str, list[int]] = defaultdict(list)
    labels: set[str] = set()
    for index, line in edges:
        k = key(line)
        if not pages_by_key[k] or pages_by_key[k][-1] != index:  # once per page
            pages_by_key[k].append(index)
        if is_label(line.text):
            labels.add(k)
    running: dict[str, int | None] = {}
    for k, indexes in pages_by_key.items():
        span = indexes[-1] - indexes[0] + 1
        if len(indexes) >= min_pages and len(indexes) / span >= min_share:
            log.debug("Running header or footer on %d pages: %r", len(indexes), k)
            running[k] = indexes[0] if k in labels else None
    return running
