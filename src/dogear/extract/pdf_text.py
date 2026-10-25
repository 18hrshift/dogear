"""Turn the lines on PDF pages into clean paragraph text.

Works on lines that `dogear.extract.pdf` has already read, so nothing here opens a file.
Cleanup removes print layout only: page numbers, running headers and footers, and line-end
hyphens. Words are never rewritten; speech normalization happens later.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from itertools import pairwise

log = logging.getLogger(__name__)

# Two font sizes within this fraction of each other count as the same size.
_SAME_SIZE = 0.1
# Line sizes are rounded to 0.1 pt when read, so comparisons allow for that.
_SIZE_SLACK = 0.05
# Line spacing to assume when a book has no two consecutive body lines to measure.
_DEFAULT_LEADING = 1.2
# A heading set in large type wraps onto at most this many lines.
HEADING_MAX_LINES = 3

# A valid lowercase roman numeral such as "xiv". Lowercase only: "I", "IV" or "MIX" alone
# on a line are more often a chapter number or a word than a page number.
ROMAN = r"(?=[ivxlcdm])m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
_PAGE_NUMBER = re.compile(rf"[\[(\-–—\s]*(?:\d{{1,4}}|{ROMAN})[\])\-–—\s]*")
_EDGE_ROMAN = re.compile(rf"^{ROMAN}\b|\b{ROMAN}$")
_DIGITS = re.compile(r"\d+")
_SPLIT_WORD = re.compile(r"[^\W\d_]-$")  # a letter, then a hyphen, at the end of a line
_OPEN_DASH = re.compile(r"\S[—–]$")  # a dash touching the last word, as in "and then—"
_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]]*$|[—–-][\"'”’»]+$")
_SOFT_HYPHEN = "­"


@dataclass(frozen=True)
class Line:
    """One line of text as laid out, in PDF points measured from the page's top-left corner."""

    text: str
    top: float
    bottom: float
    x0: float
    x1: float
    size: float  # the most common character size in the line
    chars: int  # non-space characters


@dataclass(frozen=True)
class Page:
    index: int  # 0-based position in the file
    label: str  # the printed page number, such as "xii" or "42"
    lines: tuple[Line, ...]
    has_images: bool = False

    @property
    def char_count(self) -> int:
        return sum(line.chars for line in self.lines)


@dataclass(frozen=True)
class Layout:
    """Measurements of a book's body text, used to tell headings and paragraphs apart."""

    body_size: float
    heading_size: float
    line_pitch: float  # usual distance between the baselines of two body lines
    gap_ratio: float
    indent: float  # how far in, in points, a line must start to count as indented

    def is_heading(self, line: Line) -> bool:
        return line.size >= self.heading_size - _SIZE_SLACK

    def is_body(self, line: Line) -> bool:
        return same_size(line.size, self.body_size)


@dataclass(frozen=True)
class PageText:
    """A page's lines grouped into paragraphs."""

    paragraphs: tuple[tuple[Line, ...], ...]
    indented_start: bool  # the first line is indented, so it can't continue the last page


def same_size(a: float, b: float) -> bool:
    return abs(a - b) <= _SAME_SIZE * max(a, b) + _SIZE_SLACK


def measure_layout(
    pages: Sequence[Page], *, heading_ratio: float, gap_ratio: float, indent_ratio: float
) -> Layout:
    body = body_size(pages)
    return Layout(
        body_size=body,
        heading_size=body * heading_ratio,
        line_pitch=_line_pitch(pages, body),
        gap_ratio=gap_ratio,
        indent=body * indent_ratio,
    )


def body_size(pages: Sequence[Page]) -> float:
    """The font size that most characters are set in."""
    weights: Counter[float] = Counter()
    for page in pages:
        for line in page.lines:
            weights[line.size] += line.chars
    if not weights:
        raise ValueError("no text to measure")
    return weights.most_common(1)[0][0]


def _line_pitch(pages: Sequence[Page], body: float) -> float:
    # The most common baseline-to-baseline distance between body lines. The mode, not the
    # median, because books of short paragraphs have nearly as many gaps as plain lines.
    pitches: Counter[float] = Counter()
    for page in pages:
        for a, b in pairwise(page.lines):
            if same_size(a.size, body) and same_size(b.size, body) and b.bottom > a.bottom:
                pitches[round((b.bottom - a.bottom) * 2) / 2] += 1
    if not pitches:
        return body * _DEFAULT_LEADING
    # Ties go to the smaller distance: plain line spacing is never wider than a gap.
    return min(pitches.items(), key=lambda item: (-item[1], item[0]))[0]


def leading_heading_lines(lines: Sequence[Line], layout: Layout) -> int:
    """How many lines at the start of `lines` are set in heading type."""
    count = 0
    while count < min(HEADING_MAX_LINES, len(lines)) and layout.is_heading(lines[count]):
        count += 1
    text = "".join(line.text for line in lines[:count])
    # One large letter is a drop cap or an ornament, not a heading.
    return count if sum(c.isalnum() for c in text) >= 2 else 0


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
) -> list[Page]:
    """Drop page numbers and running headers and footers from the top and bottom of pages.

    A first or last line is a running header or footer when its `running_key` comes back
    on at least `min_pages` pages, and on at least `min_share` of the pages from its first
    appearance to its last. The share keeps a line that happens to repeat far apart, such
    as a scene-break ornament.

    Lines in heading type are never removed. Lines that `is_label` (such as "Chapter 3")
    are matched on their exact text instead, and their first appearance is kept, because
    that is where the section opens; chapter detection depends on it.
    """

    def removable(line: Line) -> bool:
        return not layout.is_heading(line)

    def key(line: Line) -> str:
        # The prefix keeps a label's exact text apart from normalized keys.
        return f"label:{line.text.casefold()}" if is_label(line.text) else running_key(line.text)

    def page_number(line: Line) -> bool:
        return removable(line) and not is_label(line.text) and is_page_number(line.text)

    def drop(line: Line, running: dict[str, int | None], index: int) -> bool:
        if page_number(line):
            return True
        if not removable(line):
            return False
        k = key(line)
        return k in running and running[k] != index

    trimmed = [(page.index, _trim(page.lines, page_number, page_number)) for page in pages]
    tops = [(i, lines[0]) for i, lines in trimmed if lines and removable(lines[0])]
    bottoms = [(i, lines[-1]) for i, lines in trimmed if lines and removable(lines[-1])]
    headers = _running(tops, key, is_label, min_pages, min_share)
    footers = _running(bottoms, key, is_label, min_pages, min_share)
    cleaned = [
        replace(
            page,
            lines=_trim(
                page.lines,
                partial(drop, running=headers, index=page.index),
                partial(drop, running=footers, index=page.index),
            ),
        )
        for page in pages
    ]
    removed = sum(len(page.lines) for page in pages) - sum(len(page.lines) for page in cleaned)
    log.info("Removed %d page-number, header, and footer lines", removed)
    return cleaned


def _trim(
    lines: Sequence[Line], drop_top: Callable[[Line], bool], drop_bottom: Callable[[Line], bool]
) -> tuple[Line, ...]:
    start, end = 0, len(lines)
    while start < end and drop_top(lines[start]):
        start += 1
    while end > start and drop_bottom(lines[end - 1]):
        end -= 1
    return tuple(lines[start:end])


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


def join_lines(lines: Iterable[str]) -> str:
    """Join a paragraph's lines into one string, undoing line-end hyphenation.

    "beauti-" + "ful" becomes "beautiful". A hyphen before a capital or a digit is kept
    without a space ("Anglo-" + "Saxon" is "Anglo-Saxon"). Other lines join with a space.
    """
    text = ""
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            continue
        if not text:
            text = line
        elif text.endswith(_SOFT_HYPHEN):
            text = text[:-1] + line
        elif _SPLIT_WORD.search(text):
            text = (text[:-1] if line[0].islower() else text) + line
        elif _OPEN_DASH.search(text):
            text += line
        else:
            text += " " + line
    return text.replace(_SOFT_HYPHEN, "")


def split_paragraphs(lines: Sequence[Line], layout: Layout) -> PageText:
    """Group a page's lines into paragraphs by vertical gaps, indents, and size changes."""
    if not lines:
        return PageText((), False)
    body = [line for line in lines if layout.is_body(line)] or list(lines)
    # The leftmost body line marks the margin. Not the most common start: on a page of
    # one-line dialogue most lines are indented.
    margin = min(line.x0 for line in body)
    right = max(line.x1 for line in body)
    groups: list[list[Line]] = [[lines[0]]]
    for prev, line in pairwise(lines):
        if _starts_paragraph(prev, line, margin, right, layout):
            groups.append([line])
        else:
            groups[-1].append(line)
    return PageText(
        paragraphs=tuple(tuple(g) for g in groups),
        indented_start=_indented(lines[0], margin, layout),
    )


def _indented(line: Line, margin: float, layout: Layout) -> bool:
    return line.x0 - margin >= layout.indent


def _starts_paragraph(prev: Line, line: Line, margin: float, right: float, layout: Layout) -> bool:
    if not same_size(prev.size, line.size):
        return True
    if line.bottom - prev.bottom > layout.line_pitch * layout.gap_ratio:
        return True
    if not _indented(line, margin, layout):
        return False
    # An indented line after a line at the margin is a first-line indent. After another
    # indented line it starts a paragraph only if that line stopped short (one-line
    # dialogue); otherwise both belong to an indented block such as a quotation.
    return line.x0 - prev.x0 >= layout.indent or prev.x1 <= right - layout.indent


def continues(previous: Sequence[Line], page: PageText, layout: Layout) -> bool:
    """Whether a page's first paragraph carries on `previous`, the last page's last one."""
    if not previous or not page.paragraphs or page.indented_start:
        return False
    last, first = previous[-1], page.paragraphs[0][0]
    if not same_size(last.size, first.size):
        return False
    return not _SENTENCE_END.search(last.text) or first.text[:1].islower()
