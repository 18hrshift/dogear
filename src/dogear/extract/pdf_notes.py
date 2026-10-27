"""Footnotes printed at the foot of PDF pages, and the markers in the text that point at them.

Before running footers are removed, `note_lines` picks out the lines that are surely
notes, so that a one-line note that repeats from page to page ("1 Ibid.") is never
taken for a footer. Then two steps, either side of column ordering:

1. `find_notes` works on a page's lines as printed, top to bottom, after running footers
   are gone. The lines at the foot of the page set smaller than body text are a note
   block when the page shows they are notes: a small raised marker in the body that
   matches a marker opening a line of the block, or markers raised in the block itself.
   A line opening with a marker ("1", "*", "†", "¹") starts a note. Numbered notes must
   count up, so a line inside a note that happens to start with a number stays in it.
   Lines at the top of a block before any marker carry on the last note of the page
   before, when that note didn't end a sentence or these lines start in lowercase. The
   block leaves the page's lines and becomes `Page.notes`, so it no longer interrupts a
   paragraph that runs on to the next page.
2. `link_note_refs` works on lines in reading order. A raised marker in the text that
   matches a note on the same page is taken out of the text and recorded in
   `Line.note_refs`. Raised digits that match no note, such as exponents, stay.

Note ids are "page12-note1": the page in the file and the note's place on it, so they are
unique in the book even where every page numbers its notes from 1.

Limits: a block with no raised marker on either side (notes and references set as plain
"1" at body height) is read as paragraphs. Notes set at the foot of each column, rather
than across the page, run together as one block. A reference whose note starts on the
next page keeps its marker in the text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from dogear.extract.pdf_page import SUPERSCRIPT_DIGITS
from dogear.extract.pdf_text import (
    Layout,
    Line,
    Page,
    PageNote,
    ends_sentence,
    remove_spans,
    same_size,
)

log = logging.getLogger(__name__)

# A marker set on the line, not raised: "1 ", "12. ", "* ", "†) ". Some text must follow.
_PLAIN_MARKER = re.compile(r"(\d{1,3}|[*†‡§¶‖]{1,3})[.)]?\s+(?=\S)")
_ASCII_DIGITS = str.maketrans(SUPERSCRIPT_DIGITS, "0123456789")


def marker_label(text: str) -> str:
    """A marker as compared between text and notes: "¹" and "1" are the same."""
    return text.strip().translate(_ASCII_DIGITS)


def note_lines(page: Page, layout: Layout) -> list[Line]:
    """The page's lines that are surely footnotes, even before running footers are gone:
    from the first small line opening with a marker that the page points at, down
    through the small lines set close under it. A page number or footer below the notes
    is set apart from them, so it is not included."""
    lines = page.lines
    marks = {
        marker_label(line.text[s:e])
        for line in lines
        if not _note_size(line, layout)
        for s, e in line.raised
    }
    for i, line in enumerate(lines):
        start = _marker(line, i) if _note_size(line, layout) else None
        if start is None or not (start.raised or start.label in marks):
            continue
        end = i + 1
        while (
            end < len(lines)
            and _note_size(lines[end], layout)
            and lines[end].bottom - lines[end - 1].bottom <= layout.paragraph_gap
        ):
            end += 1
        return list(lines[i:end])
    return []


def find_notes(pages: Sequence[Page], layout: Layout) -> list[Page]:
    """Pages with the note block at each one's foot moved from its lines to `Page.notes`."""
    out: list[Page] = []
    for page in pages:
        follows = out and out[-1].index == page.index - 1 and out[-1].notes
        previous = out[-1] if follows else None
        page, carried = _take_notes(page, previous.notes[-1] if previous else None, layout)
        if previous and carried:
            *others, last = previous.notes
            out[-1] = replace(previous, notes=(*others, replace(last, lines=last.lines + carried)))
        out.append(page)
    found = sum(len(page.notes) for page in out)
    if found:
        log.info("Found %d footnotes", found)
    return out


def link_note_refs(pages: Sequence[Page]) -> list[Page]:
    """Pages with each raised marker that matches a note on its page taken out of the
    text and recorded in `Line.note_refs`."""
    return [_link(page) if page.notes else page for page in pages]


@dataclass(frozen=True)
class _Start:
    """A line of a note block that opens a note."""

    index: int  # in the block
    label: str
    text: str  # the line's text after the marker
    raised: bool  # the marker is set raised


def _take_notes(
    page: Page, last_note: PageNote | None, layout: Layout
) -> tuple[Page, tuple[Line, ...]]:
    """The page without its note block, and the lines that carry on `last_note`."""
    lines = page.lines
    top = len(lines)
    while top > 0 and _note_size(lines[top - 1], layout):
        top -= 1
    if top in (0, len(lines)):  # no block, or a page all in small type
        return page, ()
    body, block = lines[:top], lines[top:]
    body_marks = {marker_label(line.text[s:e]) for line in body for s, e in line.raised}
    starts = _starts(block, body_marks)
    first = starts[0].index if starts else len(block)
    carried = block[:first] if last_note and _carries_on(last_note, block[:first]) else ()
    shown = any(start.label in body_marks or start.raised for start in starts)
    notes = _notes(page, block, starts) if shown else ()
    kept = (*body, *block[len(carried) : first], *(() if notes else block[first:]))
    return replace(page, lines=kept, notes=notes), carried


def _note_size(line: Line, layout: Layout) -> bool:
    return line.size < layout.body_size and not same_size(line.size, layout.body_size)


def _starts(block: Sequence[Line], body_marks: set[str]) -> list[_Start]:
    starts: list[_Start] = []
    number: int | None = None  # the last numbered note's number
    for i, line in enumerate(block):
        start = _marker(line, i)
        if start is None:
            continue
        if start.label.isdigit():
            follows = number is None or int(start.label) == number + 1
            if not (follows or start.label in body_marks):
                continue  # a line of the note above that starts with a number
            number = int(start.label)
        starts.append(start)
    return starts


def _marker(line: Line, index: int) -> _Start | None:
    """The marker opening `line`, if any, with text after it."""
    for start, end in line.raised:
        if start == 0:
            text = line.text[end:].strip()
            return _Start(index, marker_label(line.text[:end]), text, True) if text else None
    plain = _PLAIN_MARKER.match(line.text)
    if plain:
        return _Start(index, marker_label(plain.group(1)), line.text[plain.end() :], False)
    return None


def _carries_on(note: PageNote, lines: Sequence[Line]) -> bool:
    return bool(lines) and (not ends_sentence(note.lines[-1].text) or lines[0].text[:1].islower())


def _notes(page: Page, block: Sequence[Line], starts: Sequence[_Start]) -> tuple[PageNote, ...]:
    notes = []
    ends = [start.index for start in starts[1:]] + [len(block)]
    for n, (start, end) in enumerate(zip(starts, ends, strict=True), start=1):
        first = replace(block[start.index], text=start.text, raised=())
        lines = (first, *block[start.index + 1 : end])
        notes.append(PageNote(f"page{page.index + 1}-note{n}", start.label, lines))
    return tuple(notes)


def _link(page: Page) -> Page:
    ids: dict[str, str] = {}
    for note in page.notes:
        ids.setdefault(note.label, note.note_id)
    lines = []
    for line in page.lines:
        spans = [(s, e) for s, e in line.raised if marker_label(line.text[s:e]) in ids]
        linked = remove_spans(line, spans) if spans else line
        if linked.text.strip():  # a line that was only a marker keeps it
            refs = tuple(ids[marker_label(line.text[s:e])] for s, e in spans)
            line = replace(linked, note_refs=line.note_refs + refs)
        lines.append(line)
    return replace(page, lines=tuple(lines))
