"""Attach printed captions to the figures on PDF pages.

A caption is the paragraph right after its figure in reading order, or right before it,
that opens with a label such as "Figure 3." or "Plate IV:". The label must end in
punctuation or a dash, or the caption must be set in a size other than body text, so a
paragraph that opens "Figure 3 shows" stays a paragraph. An attached caption leaves the
page's lines, so it is read once, with its image. A caption that doesn't look like this
stays a paragraph next to the image.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence
from dataclasses import replace
from itertools import takewhile

from dogear.extract.pdf_text import Layout, Line, Page, split_paragraphs

log = logging.getLogger(__name__)

_LABEL = re.compile(
    r"(?:figure|fig\.|plate|illustration|map|chart|diagram)\s+[\divxlc]+[a-z]?"
    r"(?P<end>[.:]|\s*[\u2013\u2014-](?:\s|$))?",  # a dash: hyphen, en, or em
    re.IGNORECASE,
)


def is_caption_start(line: Line, layout: Layout) -> bool:
    label = _LABEL.match(line.text)
    return label is not None and (label.group("end") is not None or not layout.is_body(line))


def attach_captions(pages: Sequence[Page], layout: Layout) -> list[Page]:
    """Pages with each figure's caption moved from the page's lines to the figure."""
    return [_attach(page, layout) if page.figures else page for page in pages]


def _attach(page: Page, layout: Layout) -> Page:
    figures = sorted(page.figures, key=lambda figure: figure.seq)
    taken: set[int] = set()  # seq of each line moved into a caption
    attached = []
    for i, figure in enumerate(figures):
        previous = figures[i - 1].seq if i else -1
        following = figures[i + 1].seq if i + 1 < len(figures) else math.inf
        free = [line for line in page.lines if line.seq not in taken]
        after = [line for line in free if figure.seq < line.seq < following]
        before = [line for line in free if previous < line.seq < figure.seq]
        caption = _caption(after, layout, first=True) or _caption(before, layout, first=False)
        taken |= {line.seq for line in caption}
        attached.append(replace(figure, caption=caption))
    if taken:
        log.debug("Page %s: attached %d caption lines to figures", page.label, len(taken))
    lines = tuple(line for line in page.lines if line.seq not in taken)
    return replace(page, lines=lines, figures=tuple(attached))


def _caption(lines: Sequence[Line], layout: Layout, *, first: bool) -> tuple[Line, ...]:
    """The first paragraph of `lines` (or the last), if it is a caption."""
    if not lines:
        return ()
    near = lines if first else lines[::-1]
    flow = list(takewhile(lambda line: line.flow == near[0].flow, near))  # one column's worth
    paragraphs = split_paragraphs(flow if first else flow[::-1], layout).paragraphs
    group = paragraphs[0] if first else paragraphs[-1]
    return group if is_caption_start(group[0], layout) else ()
