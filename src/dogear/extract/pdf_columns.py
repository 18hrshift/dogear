"""Put the lines of pages set in columns in reading order.

pdfplumber reads a page in rows across its whole width, so two columns side by side come
out interleaved, or as single lines holding a line of each. This module finds the
columns and reads each one top to bottom, left to right. It runs after running headers
and footers are removed, so a header that sits over one column is never read as that
column's first line.

How a page is read:

- When a page is read, each row is cut into parts at gaps at least a gutter wide
  (`Line.parts`). Rows that pdfplumber kept apart, because the columns' lines don't
  line up, are single parts.
- A gutter is tried where at least `min_lines` parts start at the same place, with room
  for a column on each side. The leftmost place is tried first; on a page of three
  columns that splits off the first column, and the other two are split next.
- A row with a part that crosses the gutter spans the columns, like a title above them;
  it is read where it sits. The rows between two spanning rows are a block, and a block
  with at least `min_lines` lines on each side, each side wide enough, is read as
  columns. Each side is checked again for columns of its own.

A page that has no such block is left exactly as read. Figures take part like rows of
one part each: a figure in a column is read in that column, and one across the gutter
spans it. They never make a column on their own: only lines count.

Known limits: a table with wide, evenly spaced columns is read one column at a time, as
text columns are. A line short enough to stay on one side of the gutter joins that
column: right for the short last line of a paragraph above the columns, wrong for a
short heading set directly below them, which is read before the next column.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import groupby

from dogear.extract.pdf_text import Figure, Line, Page, common_size, merge_lines

log = logging.getLogger(__name__)

# Part edges are compared to a gutter rounded to the nearest point.
_ROUNDING = 1.0


@dataclass(frozen=True)
class ColumnRules:
    """The [pdf] column settings, in units of the page's main font size."""

    gap_ratio: float
    min_lines: int
    min_width_ratio: float


def order_columns(page: Page, rules: ColumnRules) -> Page:
    """`page` with its lines and figures in reading order, numbered in `seq`, and each
    line's column or full-width run of text numbered in `Line.flow`."""
    if not page.lines:
        return replace(page, figures=tuple(replace(f, seq=i) for i, f in enumerate(page.figures)))
    unit = common_size(page.lines)
    finder = _Finder(rules.gap_ratio * unit, rules.min_lines, rules.min_width_ratio * unit)
    lines: list[Line] = []
    figures: list[Figure] = []
    flows = [flow for flow in finder.order(_items(page)) if flow]
    for n, flow in enumerate(flows):
        for thing in flow:
            seq = len(lines) + len(figures)
            if isinstance(thing, Figure):
                figures.append(replace(thing, seq=seq))
            else:
                lines.append(replace(thing, flow=n, seq=seq))
    return replace(page, lines=tuple(lines), figures=tuple(figures))


Piece = Line | Figure


@dataclass(frozen=True)
class _Item:
    """A row of the page or a figure, or the part of a row on one side of a gutter."""

    whole: Piece  # the row as one line, when it isn't cut, or the figure
    pieces: tuple[Piece, ...]  # its parts, left to right


def _items(page: Page) -> list[_Item]:
    """The page's rows as read, with each figure before the first row that starts below
    its top."""
    figures = sorted(page.figures, key=lambda figure: figure.top)
    items = []
    for line in page.lines:
        while figures and figures[0].top <= line.top:
            items.append(_Item(figures[0], (figures[0],)))
            figures.pop(0)
        row = replace(line, parts=())
        items.append(_Item(row, line.parts or (row,)))
    return items + [_Item(figure, (figure,)) for figure in figures]


@dataclass(frozen=True)
class _Finder:
    gap: float
    min_lines: int
    min_width: float

    def order(self, items: Sequence[_Item]) -> list[list[Piece]]:
        """The rows' lines in reading order, as flows: each a column or a run of rows
        read where they sit."""
        if sum(len(item.pieces) for item in items) >= 2 * self.min_lines:
            for gutter in self._gutters(items):
                found = self._split(items, gutter)
                if found is not None:
                    return found
        return [[item.whole for item in items]]

    def _gutters(self, items: Sequence[_Item]) -> list[float]:
        """Where a column could start: a place where enough parts start, with room for a
        column and a gutter to its left and a column to its right."""
        pieces = [piece for item in items for piece in item.pieces]
        left = min(piece.x0 for piece in pieces)
        right = max(piece.x1 for piece in pieces)
        starts = Counter(round(piece.x0) for piece in pieces if isinstance(piece, Line))
        return sorted(
            x
            for x, count in starts.items()
            if count >= self.min_lines
            and left + self.min_width + self.gap <= x <= right - self.min_width
        )

    def _split(self, items: Sequence[_Item], gutter: float) -> list[list[Piece]] | None:
        """The flows in reading order with columns split at `gutter`, or None when no
        block of rows forms columns there."""

        def side(piece: Piece) -> int | None:  # 0: left, 1: right, None: across
            if piece.x1 <= gutter - self.gap + _ROUNDING:
                return 0
            if piece.x0 >= gutter - _ROUNDING:
                return 1
            return None

        def spans(item: _Item) -> bool:
            return any(side(piece) is None for piece in item.pieces)

        out: list[list[Piece]] = []
        loose: list[_Item] = []  # rows read where they sit, between column blocks
        found = False
        for spanning, run in groupby(items, key=spans):
            group = list(run)
            if not spanning:
                left = _side_items(group, lambda piece: side(piece) == 0)
                right = _side_items(group, lambda piece: side(piece) == 1)
                if self._columns(left) and self._columns(right):
                    out += self.order(loose) + self.order(left) + self.order(right)
                    loose = []
                    found = True
                    continue
            loose += group
        if not found:
            return None
        log.debug("Columns split at x=%.0f", gutter)
        return out + self.order(loose)

    def _columns(self, items: Sequence[_Item]) -> bool:
        """Whether one side of a block has enough lines, and is wide enough, to be a column."""
        text = [[p for p in item.pieces if isinstance(p, Line)] for item in items]
        pieces = [piece for row in text for piece in row]
        if sum(bool(row) for row in text) < self.min_lines:
            return False
        return max(p.x1 for p in pieces) - min(p.x0 for p in pieces) >= self.min_width


def _side_items(items: Sequence[_Item], on_side: Callable[[Piece], bool]) -> list[_Item]:
    """The part of each item on one side of a gutter, skipping items with nothing there.
    Only rows of text have more than one part, so a cut item is always a line."""
    out = []
    for item in items:
        pieces = tuple(piece for piece in item.pieces if on_side(piece))
        if pieces == item.pieces:
            out.append(item)
        elif pieces:
            lines = [piece for piece in pieces if isinstance(piece, Line)]
            out.append(_Item(merge_lines(lines), pieces))
    return out
