"""Read one pdfplumber page into a `Page`: its lines and its figures.

Lines come from pdfplumber's text map, the same one its `extract_text_lines` uses, so a
line's text and box are exactly what that method gives. Building them here keeps what it
drops: the character behind every letter, which shows where a line has a gap wide enough
to be a column gutter, and which letters are bold.

Figures are the page's images that cover at least a set share of the page. Smaller ones
are decoration, such as ornaments and rules. An image with text on top of it is a page
background, or the picture of a scanned page under its text layer, so it is not a figure
either. Vector drawings are not images and are not found.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from dogear.extract.pdf_text import Figure, Line, Page, common_size, merge_drop_caps

log = logging.getLogger(__name__)

Char = dict[str, Any]
# One letter of a line's text and the character it came from. pdfplumber puts a space
# between words without a character behind it; one character can give several letters
# ("ﬁ" gives "f" and "i").
Cell = tuple[str, Char | None]
Box = tuple[float, float, float, float]  # x0, top, x1, bottom

# Font names such as "Times-Bold", "ABCDEF+Minion-Semibold", or "Arial-BlackItalic".
_BOLD_FONT = re.compile(r"bold|black|heavy|demi", re.IGNORECASE)


@dataclass(frozen=True)
class ReadSettings:
    """The [pdf] settings that apply while reading a page."""

    column_gap_ratio: float  # a gutter is this many times the page's main font size
    image_min_page_share: float  # a figure covers at least this share of the page


def read_page(plumber_page: Any, index: int, label: str, settings: ReadSettings) -> Page:
    rows = [row for cells in _rows(plumber_page.get_textmap().tuples) if (row := _row(cells))]
    lines = [line for line, _ in rows]
    if lines:
        gap = settings.column_gap_ratio * common_size(lines)
        lines = [replace(line, parts=_parts(cells, gap)) for line, cells in rows]
    lines = merge_drop_caps(lines)
    return Page(
        index=index,
        label=label,
        lines=lines,
        has_images=bool(plumber_page.images),
        figures=_figures(plumber_page, lines, settings.image_min_page_share),
    )


def _figures(plumber_page: Any, lines: Sequence[Line], min_share: float) -> tuple[Figure, ...]:
    x0, top, x1, bottom = plumber_page.bbox
    page_area = (x1 - x0) * (bottom - top)
    boxes = []
    for image in plumber_page.images:
        box = (
            max(image["x0"], x0),
            max(image["top"], top),
            min(image["x1"], x1),
            min(image["bottom"], bottom),
        )
        if box[0] < box[2] and box[1] < box[3]:  # some of it is on the page
            boxes.append(box)
    figures = []
    for box in _merge_overlapping(boxes):
        if _area(box) < min_share * page_area:
            log.debug(
                "Page %d: skipped a small image, taken as decoration", plumber_page.page_number
            )
        elif any(_inside(line, box) for line in lines):
            log.debug("Page %d: skipped an image with text on it", plumber_page.page_number)
        else:
            figures.append(Figure(top=box[1], bottom=box[3], x0=box[0], x1=box[2]))
    return tuple(figures)


def _merge_overlapping(boxes: list[Box]) -> list[Box]:
    """Overlapping or touching boxes made one, as when a picture is drawn in tiles."""
    merged: list[Box] = []
    for box in boxes:
        while overlap := next((m for m in merged if _touch(m, box)), None):
            merged.remove(overlap)
            box = (
                min(box[0], overlap[0]),
                min(box[1], overlap[1]),
                max(box[2], overlap[2]),
                max(box[3], overlap[3]),
            )
        merged.append(box)
    return merged


def _touch(a: Box, b: Box) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _area(box: Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _inside(line: Line, box: Box) -> bool:
    """Whether the middle of `line` is inside `box`."""
    x, y = (line.x0 + line.x1) / 2, (line.top + line.bottom) / 2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _rows(tuples: Sequence[Cell]) -> list[list[Cell]]:
    """The text map split into rows, as `extract_text_lines` splits it."""
    rows: list[list[Cell]] = [[]]
    for letter, char in tuples:
        if letter == "\n" and char is None:
            rows.append([])
        else:
            rows[-1].append((letter, char))
    return rows


def _row(cells: Sequence[Cell]) -> tuple[Line, list[Cell]] | None:
    """The line `extract_text_lines` makes of a row, with whitespace collapsed, and the
    cells behind that text. None for a row with no text."""
    marks = [i for i, (letter, _) in enumerate(cells) if letter != " "]
    if not marks:
        return None
    span = cells[marks[0] : marks[-1] + 1]
    text = _collapse(span)
    box = [char for _, char in span if char is not None]
    if not text or not box:
        return None
    return _line(text, box), text


def _collapse(cells: Sequence[Cell]) -> list[Cell]:
    """Cells with each run of whitespace made one plain space, and none at either end."""
    out: list[Cell] = []
    for letter, char in cells:
        if not letter.isspace():
            out.append((letter, char))
        elif out and out[-1] != (" ", None):
            out.append((" ", None))
    if out and out[-1] == (" ", None):
        out.pop()
    return out


def _line(cells: Sequence[Cell], box: Sequence[Char]) -> Line:
    """A line of the text in `cells`, measured over the characters in `box`."""
    chars = [char for _, char in cells if char is not None]
    sizes = Counter(round(char["size"], 1) for char in chars)
    return Line(
        text="".join(letter for letter, _ in cells),
        top=min(char["top"] for char in box),
        bottom=max(char["bottom"] for char in box),
        x0=min(char["x0"] for char in box),
        x1=max(char["x1"] for char in box),
        size=sizes.most_common(1)[0][0],
        chars=len(chars),
        bold=2 * sum(bool(_BOLD_FONT.search(char["fontname"])) for char in chars) > len(chars),
    )


def _parts(cells: Sequence[Cell], gap: float) -> tuple[Line, ...]:
    """The row cut where the space between two words is at least `gap` wide, or ()."""
    pieces: list[list[Cell]] = [[]]
    previous: Char | None = None
    for letter, char in cells:
        if char is not None:
            between_words = pieces[-1][-1:] == [(" ", None)]
            if between_words and previous and char["x0"] - previous["x1"] >= gap:
                pieces[-1].pop()  # the space before the gap
                pieces.append([])
            previous = char
        pieces[-1].append((letter, char))
    if len(pieces) < 2:
        return ()
    return tuple(_line(piece, [char for _, char in piece if char is not None]) for piece in pieces)
