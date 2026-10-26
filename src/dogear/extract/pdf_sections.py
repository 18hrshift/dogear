"""Build document sections from cleaned PDF pages and the boundaries between them.

Each page is first cut into runs of body text and subheadings (`pdf_headings`), so that
subheading styles can be ranked across the whole book before any section is written.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby

from dogear.document import Block, Heading, PageMarker, Paragraph, Section, SectionKind
from dogear.extract.pdf_chapters import PATTERN_LINES, Boundary
from dogear.extract.pdf_headings import Run, Style, find_subheadings, heading_levels
from dogear.extract.pdf_text import (
    HEADING_MAX_LINES,
    KeepHyphen,
    Layout,
    Line,
    Page,
    continues,
    join_lines,
    leading_heading_lines,
    split_paragraphs,
)

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
    if any(page.lines for page in front):
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
        if run.style is not None
    )
    return [_write(plan, _BlockWriter(layout, levels, keep_hyphen), lang) for plan in plans]


@dataclass(frozen=True)
class _PagePlan:
    """A page of a section, around the section's title if it is printed here."""

    label: str
    before: list[Run]
    title: tuple[Line, ...]  # empty when the title isn't on this page
    after: list[Run]


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
        planned.append(
            _PagePlan(
                page.label,
                find_subheadings(page.lines[:start], layout),
                page.lines[start : start + count],
                find_subheadings(page.lines[start + count :], layout),
            )
        )
    return _SectionPlan(title, kind, _page_span(pages), planned)


def _write(plan: _SectionPlan, writer: _BlockWriter, lang: str | None) -> Section:
    for page in plan.pages:
        writer.page(page.label, page.before)
        if page.title:
            writer.heading(page.title, level=1)
            writer.same_page(page.after)
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
    each column, in case the text that follows carries it on."""

    def __init__(
        self, layout: Layout, levels: dict[Style, int], keep_hyphen: KeepHyphen | None
    ) -> None:
        self.layout = layout
        self._levels = levels
        self._keep_hyphen = keep_hyphen
        self._blocks: list[Block] = []
        self._open: tuple[Line, ...] = ()

    def page(self, label: str, runs: Sequence[Run]) -> None:
        body = runs[0].lines if runs and runs[0].style is None else ()
        flows = _flows(body)
        first = split_paragraphs(flows[0], self.layout) if flows else None
        if first is None or not continues(self._open, first, self.layout):
            self._flush()
        # A paragraph carried on from the last page is still open, so this page's marker
        # goes before the whole of it: jumping to the page starts a little early, never late.
        self._blocks.append(PageMarker(label))
        self._runs(runs)

    def same_page(self, runs: Sequence[Run]) -> None:
        self._flush()
        self._runs(runs)

    def heading(self, lines: Sequence[Line], level: int) -> None:
        self._flush()
        self._blocks.append(Heading(level=level, text=self._join(lines)))

    def finish(self) -> list[Block]:
        self._flush()
        return self._blocks

    def _runs(self, runs: Sequence[Run]) -> None:
        for run in runs:
            if run.style is not None:
                self.heading(run.lines, self._levels[run.style])
                continue
            for flow in _flows(run.lines):
                self._text(flow)

    def _text(self, lines: Sequence[Line]) -> None:
        """Paragraphs from one flow of text, the first carrying on the open one if it can."""
        text = split_paragraphs(lines, self.layout)
        paragraphs = list(text.paragraphs)
        if continues(self._open, text, self.layout):
            paragraphs[0] = self._open + paragraphs[0]
            self._open = ()
        else:
            self._flush()
        for group in paragraphs[:-1]:
            self._blocks.append(Paragraph(self._join(group)))
        self._open = paragraphs[-1] if paragraphs else ()

    def _flush(self) -> None:
        if self._open:
            self._blocks.append(Paragraph(self._join(self._open)))
            self._open = ()

    def _join(self, lines: Sequence[Line]) -> str:
        return join_lines((line.text for line in lines), self._keep_hyphen)


def _flows(lines: Sequence[Line]) -> list[tuple[Line, ...]]:
    """`lines` split where one flow of text, such as a column, ends and the next begins."""
    return [tuple(flow) for _, flow in groupby(lines, key=lambda line: line.flow)]
