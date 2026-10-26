"""Read one pdfplumber page into a `Page`.

Lines come from pdfplumber's text map, the same one its `extract_text_lines` uses, so a
line's text and box are exactly what that method gives. Building them here keeps what it
drops: the character behind every letter, which shows where a line has a gap wide enough
to be a column gutter.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from dogear.extract.pdf_text import Line, Page, common_size, merge_drop_caps

Char = dict[str, Any]
# One letter of a line's text and the character it came from. pdfplumber puts a space
# between words without a character behind it; one character can give several letters
# ("ﬁ" gives "f" and "i").
Cell = tuple[str, Char | None]


@dataclass(frozen=True)
class ReadSettings:
    """The [pdf] settings that apply while reading a page."""

    column_gap_ratio: float  # a gutter is this many times the page's main font size


def read_page(plumber_page: Any, index: int, label: str, settings: ReadSettings) -> Page:
    rows = [row for cells in _rows(plumber_page.get_textmap().tuples) if (row := _row(cells))]
    lines = [line for line, _ in rows]
    if lines:
        gap = settings.column_gap_ratio * common_size(lines)
        lines = [replace(line, parts=_parts(cells, gap)) for line, cells in rows]
    return Page(
        index=index,
        label=label,
        lines=merge_drop_caps(lines),
        has_images=bool(plumber_page.images),
    )


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
