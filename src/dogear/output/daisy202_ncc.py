"""The NCC of a DAISY 2.02 book: its metadata and every place a listener can move to.

The body lists every heading (h1 to h6, at the book-wide levels the read-along model
settled, so none skips a level) and every print page, in reading order, each linking to
the SMIL `par` where it begins. The first entry is the title: the title track's heading,
or the first section's opening heading when there's no title track, as DAISY Pipeline 2
does. The head holds the metadata DAISY 2.02 requires, with the counts its validator
checks.

dc:publisher is the source book's publisher, as DAISY Pipeline 2's EPUB converter writes
it, and "Unknown" when the book names none (the spec makes the field mandatory).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from lxml import etree

from dogear.output import daisy202_xhtml as x
from dogear.output.daisy202_clock import whole_seconds
from dogear.output.daisy202_plan import BookPlan
from dogear.output.daisy202_text import PAGE_CLASSES
from dogear.readalong.model import HeadingText, PageText


@dataclass(frozen=True)
class Entry:
    """One place in the NCC: a heading or a print page."""

    tag: str  # h1 to h6, or span for a page
    id: str
    href: str  # the SMIL par it starts at
    text: str
    css_class: str | None = None  # a page's kind; "title" for the first heading


def ncc_entries(book: BookPlan) -> list[Entry]:
    """Every heading and page in reading order, the first marked as the title."""
    entries: list[Entry] = []
    plans = book.sections
    for i, plan in enumerate(plans):
        syncs = plan.section.syncs
        for item in plan.section.items:
            if isinstance(item, HeadingText):
                href = f"{plan.smil}#{syncs[item.sync].id}"
                entries.append(Entry(f"h{item.level}", item.id, href, item.text))
            elif isinstance(item, PageText):
                href = _page_href(book, i, item)
                entries.append(Entry("span", item.id, href, item.label, PAGE_CLASSES[item.kind]))
    # The plan checked that the first section opens with a level 1 heading.
    first = entries[0]
    entries[0] = Entry(first.tag, first.id, first.href, first.text, "title")
    return entries


def ncc_document(book: BookPlan, today: date) -> etree._Element:
    entries = ncc_entries(book)
    html, head, body = x.document(book.title, book.language)
    pages = [e for e in entries if e.tag == "span"]
    kinds = Counter(page.css_class for page in pages)
    metas = [
        ("dc:title", book.title),
        *(("dc:creator", creator) for creator in book.creators),
        ("dc:date", today.isoformat()),
        ("dc:format", "Daisy 2.02"),
        ("dc:identifier", book.identifier),
        ("dc:language", book.language),
        ("dc:publisher", book.publisher),
        ("ncc:charset", "utf-8"),
        ("ncc:generator", book.generator),
        ("ncc:narrator", book.narrator),
        ("ncc:multimediaType", "audioFullText"),
        ("ncc:totalTime", whole_seconds(book.total)),
        ("ncc:depth", str(max(int(e.tag[1]) for e in entries if e.tag != "span"))),
        ("ncc:tocItems", str(len(entries))),
        ("ncc:files", str(len(book.files()))),
        ("ncc:pageFront", str(kinds[PAGE_CLASSES["front"]])),
        ("ncc:pageNormal", str(kinds[PAGE_CLASSES["normal"]])),
        ("ncc:pageSpecial", str(kinds[PAGE_CLASSES["special"]])),
    ]
    if book.source:
        metas.append(("dc:source", book.source))
    # The validator compares ncc:maxPageNormal with the last page in the NCC when that
    # page is a normal one, so it's declared only then.
    if pages and pages[-1].css_class == PAGE_CLASSES["normal"]:
        metas.append(("ncc:maxPageNormal", str(int(pages[-1].text))))
    for name, content in metas:
        scheme = _SCHEMES.get(name)
        x.meta(head, name, content, **({"scheme": scheme} if scheme else {}))
    for entry in entries:
        el = x.element(entry.tag, body, id=entry.id)
        if entry.css_class:
            el.set("class", entry.css_class)
        link = x.element("a", el, href=entry.href)
        link.text = x.text(entry.text)
    return html


# The formats the spec gives these values in, declared as it shows them.
_SCHEMES = {"dc:date": "yyyy-mm-dd", "ncc:totalTime": "hh:mm:ss"}


def _page_href(book: BookPlan, i: int, page: PageText) -> str:
    """Where a page begins: the first words after its break.

    A page break at the very end of a section begins with the next section's first
    words; at the end of the book, with the book's last words.
    """
    plans = book.sections
    if page.sync is not None:
        plan, sync = plans[i], plans[i].section.syncs[page.sync]
    elif i + 1 < len(plans):
        plan, sync = plans[i + 1], plans[i + 1].section.syncs[0]
    else:
        plan, sync = plans[i], plans[i].section.syncs[-1]
    return f"{plan.smil}#{sync.id}"
