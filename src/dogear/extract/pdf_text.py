"""Turn the lines on PDF pages into clean paragraph text.

Works on lines that `dogear.extract.pdf` has already read, so nothing here opens a file.
Cleanup removes print layout only, such as line-end hyphens; `pdf_furniture` removes page
numbers and running headers. Words are never rewritten; speech normalization happens later.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
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
_SPLIT_WORD = re.compile(r"[^\W\d_]-$")  # a letter, then a hyphen, at the end of a line
_OPEN_DASH = re.compile(r"\S[—–]$")  # a dash touching the last word, as in "and then—"
_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]]*$|[—–-][\"'”’»]+$")
_SOFT_HYPHEN = "\u00ad"
_OPENING_QUOTES = "\"'\u201c\u2018\u00ab"


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

    @property
    def paragraph_gap(self) -> float:
        """Baseline-to-baseline distance beyond which two lines are in separate blocks."""
        return self.line_pitch * self.gap_ratio


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


def merge_drop_caps(lines: Sequence[Line]) -> tuple[Line, ...]:
    """Put a drop cap, a large first letter set beside the opening lines, back on its word.

    pdfplumber reads the letter as a line of its own, after the line it starts. The lines
    beside it are indented to make room; they are moved back to the letter's margin so
    the paragraph doesn't look like it starts over.
    """
    result = list(lines)
    for cap in lines:
        if len(cap.text.lstrip(_OPENING_QUOTES)) != 1 or not cap.text[-1].isalpha():
            continue
        beside = [
            line
            for line in result
            if line is not cap
            and line.x0 >= cap.x1 - _SIZE_SLACK
            and line.bottom > cap.top
            and line.top < cap.bottom
            and line.size < cap.size
            and not same_size(line.size, cap.size)
        ]
        if not beside:
            continue  # nothing beside it: a heading such as "I", not a drop cap
        first = min(beside, key=lambda line: line.top)
        for line in beside:
            merged = replace(line, x0=cap.x0)
            if line is first:
                merged = replace(merged, text=cap.text + line.text, chars=line.chars + cap.chars)
            result[result.index(line)] = merged
        result.remove(cap)
    return tuple(result)


def leading_heading_lines(lines: Sequence[Line], layout: Layout) -> int:
    """How many lines at the start of `lines` are set in heading type."""
    count = 0
    while count < min(HEADING_MAX_LINES, len(lines)) and layout.is_heading(lines[count]):
        count += 1
    text = "".join(line.text for line in lines[:count])
    # One large letter is a drop cap or an ornament, not a heading.
    return count if sum(c.isalnum() for c in text) >= 2 else 0


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
    if line.bottom - prev.bottom > layout.paragraph_gap:
        return True
    if not _indented(line, margin, layout):
        return False
    # An indented line after a line at the margin is a first-line indent. After another
    # indented line it starts a paragraph only if that one ended a sentence short of the
    # margin, as one-line dialogue does; otherwise both belong to an indented block such
    # as a quotation.
    if line.x0 - prev.x0 >= layout.indent:
        return True
    return prev.x1 <= right - layout.indent and _SENTENCE_END.search(prev.text) is not None


def continues(previous: Sequence[Line], page: PageText, layout: Layout) -> bool:
    """Whether a page's first paragraph carries on `previous`, the last page's last one."""
    if not previous or not page.paragraphs or page.indented_start:
        return False
    last, first = previous[-1], page.paragraphs[0][0]
    if not same_size(last.size, first.size):
        return False
    return not _SENTENCE_END.search(last.text) or first.text[:1].islower()
