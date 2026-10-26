"""Build document sections from cleaned PDF pages and the boundaries between them."""

from __future__ import annotations

import re
from collections.abc import Sequence

from dogear.document import Block, Heading, PageMarker, Paragraph, Section, SectionKind
from dogear.extract.pdf_chapters import PATTERN_LINES, Boundary
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
    sections = []

    def add(title: str, kind: SectionKind, span: Sequence[Page], heading: str | None) -> None:
        writer = _BlockWriter(layout, keep_hyphen)
        sections.append(_section(title, kind, span, heading, writer, lang))

    front = pages[: boundaries[0].page]
    if any(page.lines for page in front):
        add(FRONT_MATTER_TITLE, "front", front, None)
    ends = [b.page for b in boundaries[1:]] + [len(pages)]
    for boundary, end in zip(boundaries, ends, strict=True):
        add(boundary.title, boundary.kind, pages[boundary.page : end], boundary.title)
    return sections


def _section(
    title: str,
    kind: SectionKind,
    pages: Sequence[Page],
    heading_title: str | None,
    writer: _BlockWriter,
    lang: str | None,
) -> Section:
    layout = writer.layout
    for i, page in enumerate(pages):
        span = find_heading(page.lines, heading_title, layout) if i == 0 and heading_title else None
        if span is None:
            writer.page(page.label, page.lines)
            continue
        start, count = span
        writer.page(page.label, page.lines[:start])
        writer.heading(page.lines[start : start + count])
        writer.same_page(page.lines[start + count :])
    return Section(
        title=title, kind=kind, blocks=writer.finish(), lang=lang, source=_page_span(pages)
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
    """Collects a section's blocks, holding back each page's last paragraph in case the
    next page carries it on."""

    def __init__(self, layout: Layout, keep_hyphen: KeepHyphen | None) -> None:
        self.layout = layout
        self._keep_hyphen = keep_hyphen
        self._blocks: list[Block] = []
        self._open: tuple[Line, ...] = ()

    def page(self, label: str, lines: Sequence[Line]) -> None:
        text = split_paragraphs(lines, self.layout)
        paragraphs = list(text.paragraphs)
        if continues(self._open, text, self.layout):
            # The paragraph started on the previous page. Its marker goes before the whole
            # merged paragraph, so jumping to this page starts a little early, never late.
            paragraphs[0] = self._open + paragraphs[0]
            self._open = ()
        else:
            self._flush()
        self._blocks.append(PageMarker(label))
        self._add(paragraphs)

    def same_page(self, lines: Sequence[Line]) -> None:
        self._flush()
        self._add(list(split_paragraphs(lines, self.layout).paragraphs))

    def heading(self, lines: Sequence[Line]) -> None:
        self._flush()
        self._blocks.append(Heading(level=1, text=self._join(lines)))

    def finish(self) -> list[Block]:
        self._flush()
        return self._blocks

    def _add(self, paragraphs: list[tuple[Line, ...]]) -> None:
        for lines in paragraphs[:-1]:
            self._blocks.append(Paragraph(self._join(lines)))
        self._open = paragraphs[-1] if paragraphs else ()

    def _flush(self) -> None:
        if self._open:
            self._blocks.append(Paragraph(self._join(self._open)))
            self._open = ()

    def _join(self, lines: Sequence[Line]) -> str:
        return join_lines((line.text for line in lines), self._keep_hyphen)
