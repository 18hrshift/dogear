"""Build document sections from cleaned PDF pages and the boundaries between them.

Each page is first cut into runs of body text and subheadings (`pdf_headings`), with its
figures where they sit in reading order, so that subheading styles can be ranked across
the whole book before any section is written.

A figure never splits a paragraph: one that sits inside a paragraph, or between a
paragraph and its continuation on the next page or column, comes right after it. A page's
footnotes come after the paragraph its text ends with, in the same way.

Only paragraphs carry note references, as in the EPUB extractor: a marker in a heading or
a caption is still taken out of its text, and its note is still read, but the link is
lost (logged at debug level).
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby

from dogear.document import (
    Block,
    Footnote,
    Heading,
    Image,
    PageMarker,
    Paragraph,
    Section,
    SectionKind,
)
from dogear.extract.pdf_chapters import PATTERN_LINES, Boundary
from dogear.extract.pdf_headings import Run, Style, find_subheadings, heading_levels
from dogear.extract.pdf_text import (
    HEADING_MAX_LINES,
    Figure,
    KeepHyphen,
    Layout,
    Line,
    Page,
    PageNote,
    continues,
    join_lines,
    leading_heading_lines,
    split_paragraphs,
)

log = logging.getLogger(__name__)

FRONT_MATTER_TITLE = "Front matter"


def build_sections(
    pages: Sequence[Page],
    boundaries: Sequence[Boundary],
    layout: Layout,
    lang: str | None,
    keep_hyphen: KeepHyphen | None = None,
) -> list[Section]:
    """One section per boundary, plus front matter for any text before the first one.

    `keep_hyphen` decides line-end hyphens before lowercase letters; see `join_lines`.
    """
    plans = []
    front = pages[: boundaries[0].page]
    if any(page.lines or page.figures or page.notes for page in front):
        plans.append(_plan(FRONT_MATTER_TITLE, "front", front, None, layout))
    ends = [b.page for b in boundaries[1:]] + [len(pages)]
    for boundary, end in zip(boundaries, ends, strict=True):
        span = pages[boundary.page : end]
        plans.append(_plan(boundary.title, boundary.kind, span, boundary.title, layout))
    # Ranked over the whole book, so a style is the same level in every section.
    levels = heading_levels(
        run.style
        for plan in plans
        for page in plan.pages
        for run in (*page.before, *page.after)
        if isinstance(run, Run) and run.style is not None
    )
    return [_write(plan, _BlockWriter(layout, levels, keep_hyphen), lang) for plan in plans]


Part = Run | Figure


@dataclass(frozen=True)
class _PagePlan:
    """A page of a section, around the section's title if it is printed here."""

    label: str
    before: list[Part]
    title: tuple[Line, ...]  # empty when the title isn't on this page
    after: list[Part]
    notes: tuple[PageNote, ...]


@dataclass(frozen=True)
class _SectionPlan:
    title: str
    kind: SectionKind
    source: str
    pages: list[_PagePlan]


def _plan(
    title: str,
    kind: SectionKind,
    pages: Sequence[Page],
    heading_title: str | None,
    layout: Layout,
) -> _SectionPlan:
    planned = []
    for i, page in enumerate(pages):
        span = find_heading(page.lines, heading_title, layout) if i == 0 and heading_title else None
        start, count = span or (len(page.lines), 0)
        title_lines = page.lines[start : start + count]
        split = title_lines[0].seq if title_lines else math.inf
        planned.append(
            _PagePlan(
                page.label,
                _parts(page.lines[:start], [f for f in page.figures if f.seq < split], layout),
                title_lines,
                _parts(
                    page.lines[start + count :], [f for f in page.figures if f.seq > split], layout
                ),
                page.notes,
            )
        )
    return _SectionPlan(title, kind, _page_span(pages), planned)


def _parts(lines: Sequence[Line], figures: Sequence[Figure], layout: Layout) -> list[Part]:
    """Runs of body text and subheadings, with each figure where it sits in reading order."""
    parts: list[Part] = []
    waiting = sorted(figures, key=lambda figure: figure.seq)
    run: list[Line] = []
    for line in lines:
        while waiting and waiting[0].seq < line.seq:
            parts += find_subheadings(run, layout)
            parts.append(waiting.pop(0))
            run = []
        run.append(line)
    return parts + find_subheadings(run, layout) + waiting


def _write(plan: _SectionPlan, writer: _BlockWriter, lang: str | None) -> Section:
    for page in plan.pages:
        writer.page(page.label, page.before)
        if page.title:
            writer.heading(page.title, level=1)
            writer.same_page(page.after)
        writer.notes(page.notes)
    return Section(
        title=plan.title, kind=plan.kind, blocks=writer.finish(), lang=lang, source=plan.source
    )


def find_heading(lines: Sequence[Line], title: str, layout: Layout) -> tuple[int, int] | None:
    """Where a section's first page prints its heading, as (first line, line count).

    Leading lines in heading type win. Otherwise look near the top for lines that spell
    out the title, as body-size "Chapter 3" labels in scanned books do.
    """
    count = leading_heading_lines(lines, layout)
    if count:
        return 0, count
    want = _comparable(title)
    for start in range(min(PATTERN_LINES, len(lines))):
        for count in range(1, HEADING_MAX_LINES + 1):
            got = _comparable(join_lines(line.text for line in lines[start : start + count]))
            if got == want:
                return start, count
            if start + count >= len(lines) or not want.startswith(got):
                break
    return None


def _comparable(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def _page_span(pages: Sequence[Page]) -> str:
    first, last = pages[0].label, pages[-1].label
    return f"page {first}" if len(pages) == 1 else f"pages {first}-{last}"


class _BlockWriter:
    """Collects a section's blocks, holding back the last paragraph of each page, and of
    each column, in case the text that follows carries it on. Figures and notes found
    while a paragraph is held back wait for it."""

    def __init__(
        self, layout: Layout, levels: dict[Style, int], keep_hyphen: KeepHyphen | None
    ) -> None:
        self.layout = layout
        self._levels = levels
        self._keep_hyphen = keep_hyphen
        self._blocks: list[Block] = []
        self._open: tuple[Line, ...] = ()
        self._waiting: list[Block] = []  # figures and notes to place after the open paragraph

    def page(self, label: str, parts: Sequence[Part]) -> None:
        run = next((part for part in parts if isinstance(part, Run)), None)
        flows = _flows(run.lines) if run is not None and run.style is None else []
        opening = split_paragraphs(flows[0], self.layout) if flows else None
        if opening is None or not continues(self._open, opening, self.layout):
            self._flush()
        # A paragraph carried on from the last page is still open, so this page's marker
        # goes before the whole of it: jumping to the page starts a little early, never late.
        self._blocks.append(PageMarker(label))
        self._parts(parts)

    def same_page(self, parts: Sequence[Part]) -> None:
        self._flush()
        self._parts(parts)

    def heading(self, lines: Sequence[Line], level: int) -> None:
        self._flush()
        self._blocks.append(Heading(level=level, text=self._join(lines)))
        _drop_refs(lines, "a heading")

    def notes(self, notes: Sequence[PageNote]) -> None:
        for note in notes:
            self._place(Footnote(note.note_id, self._join(note.lines), label=note.label))

    def finish(self) -> list[Block]:
        self._flush()
        return self._blocks

    def _parts(self, parts: Sequence[Part]) -> None:
        for part in parts:
            if isinstance(part, Figure):
                self._figure(part)
            elif part.style is not None:
                self.heading(part.lines, self._levels[part.style])
            else:
                for flow in _flows(part.lines):
                    self._text(flow)

    def _figure(self, figure: Figure) -> None:
        # A PDF image has no description, so alt is None (not "": that means decorative).
        self._place(Image(alt=None, caption=self._join(figure.caption)))
        _drop_refs(figure.caption, "a caption")

    def _place(self, block: Block) -> None:
        """Add a figure or a note, after the open paragraph if there is one."""
        if self._open:
            self._waiting.append(block)
        else:
            self._blocks.append(block)

    def _text(self, lines: Sequence[Line]) -> None:
        """Paragraphs from one flow of text, the first carrying on the open one if it can."""
        text = split_paragraphs(lines, self.layout)
        paragraphs = list(text.paragraphs)
        if continues(self._open, text, self.layout):
            self._open += paragraphs.pop(0)
        for group in paragraphs:
            self._flush()
            self._open = group

    def _flush(self) -> None:
        if self._open:
            refs = dict.fromkeys(ref for line in self._open for ref in line.note_refs)
            self._blocks.append(Paragraph(self._join(self._open), note_refs=tuple(refs)))
            self._open = ()
        self._blocks += self._waiting
        self._waiting = []

    def _join(self, lines: Sequence[Line]) -> str:
        return join_lines((line.text for line in lines), self._keep_hyphen)


def _drop_refs(lines: Sequence[Line], where: str) -> None:
    refs = [ref for line in lines for ref in line.note_refs]
    if refs:
        log.debug(
            "Note references %s in %s can't be kept: only paragraphs carry them.", refs, where
        )


def _flows(lines: Sequence[Line]) -> list[tuple[Line, ...]]:
    """`lines` split where one flow of text, such as a column, ends and the next begins."""
    return [tuple(flow) for _, flow in groupby(lines, key=lambda line: line.flow)]
