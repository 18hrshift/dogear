"""Find subheadings inside a PDF section: lines set larger or bolder than body text.

A section's own title is found by `pdf_sections.find_heading` and becomes a level-1
heading. Inside a section, up to `HEADING_MAX_LINES` lines in one heading style are a
subheading. A heading style is a size at least `Layout.subheading_size`, or bold in
body size or larger when body text is not bold. Lines in chapter-level type that are not
a section's title, such as a second story starting partway down a page, are subheadings
too.

Styles are ranked across the whole book, largest first and bold before regular, and
the ranks become heading levels 2 to 6, so the same style is the same level in every
chapter.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import groupby

from dogear.extract.pdf_text import HEADING_MAX_LINES, Layout, Line, same_size

Style = tuple[float, bool]  # font size, bold
_TOP_LEVEL = 2  # level 1 is the section's title
_BOTTOM_LEVEL = 6


@dataclass(frozen=True)
class Run:
    """Consecutive lines of a page: body text, or one subheading."""

    lines: tuple[Line, ...]
    style: Style | None = None  # the subheading's style; None for body text


def heading_style(line: Line, layout: Layout) -> Style | None:
    """The line's heading style, or None when it is set like body text or smaller."""
    if layout.is_subheading_size(line):
        return line.size, line.bold
    body_size_or_more = line.size >= layout.body_size or same_size(line.size, layout.body_size)
    if line.bold and not layout.body_bold and body_size_or_more:
        return line.size, True
    return None


def find_subheadings(lines: Sequence[Line], layout: Layout) -> list[Run]:
    """`lines` as runs of body text and subheadings, in order.

    More than `HEADING_MAX_LINES` lines in a row in one heading style are body text set
    for emphasis, not a heading. So is a single letter or symbol, such as an ornament.
    """

    def key(line: Line) -> tuple[Style | None, int]:  # a heading never spans two columns
        return heading_style(line, layout), line.flow

    runs: list[Run] = []
    for (style, _), group in groupby(lines, key=key):
        group = tuple(group)
        if style is not None and len(group) <= HEADING_MAX_LINES and _has_words(group):
            runs.append(Run(group, style))
        elif runs and runs[-1].style is None:
            runs[-1] = Run(runs[-1].lines + group)
        else:
            runs.append(Run(group))
    return runs


def heading_levels(styles: Iterable[Style]) -> dict[Style, int]:
    """Heading levels for the subheading styles used in a book: 2 for the largest, then
    3, and so on. Levels stop at 6, so the smallest styles may share it."""
    ranked = sorted(set(styles), key=lambda style: (-style[0], not style[1]))
    return {style: min(_TOP_LEVEL + rank, _BOTTOM_LEVEL) for rank, style in enumerate(ranked)}


def _has_words(lines: Sequence[Line]) -> bool:
    return sum(c.isalnum() for line in lines for c in line.text) >= 2
