"""The EPUB navigation document: the table of contents, the print page list, and
landmarks.

Players move through a talking book by its table of contents, so every heading in the
book is in it, nested by level. Levels arrive settled (`readalong.outline`): the first
is 1 and none is more than one deeper than the one before.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from dogear.output.epub3_xhtml import EPUB_TYPE, add, new_document, set_lang
from dogear.output.language_tag import language_tag
from dogear.readalong.model import SectionText

NAV_FILE = "nav.xhtml"


@dataclass(frozen=True)
class TextDocument:
    """A section and where its content document is, relative to the navigation document."""

    section: SectionText
    href: str
    lang: str  # the document's language


def navigation_document(documents: list[TextDocument], lang: str) -> etree._Element:
    html, body = new_document("Contents", lang)
    toc = add(body, "nav", {EPUB_TYPE: "toc", "role": "doc-toc", "id": "toc"})
    add(toc, "h1", text="Contents")
    _contents(toc, documents, lang)
    pages = [(doc.href, page) for doc in documents for page in doc.section.pages()]
    if pages:
        attrs = {EPUB_TYPE: "page-list", "role": "doc-pagelist", "id": "page-list"}
        page_list = add(body, "nav", {**attrs, "hidden": "hidden"})
        add(page_list, "h2", text="Pages")
        listing = add(page_list, "ol")
        for href, page in pages:
            add(add(listing, "li"), "a", {"href": f"{href}#{page.id}"}, page.label)
    landmarks = add(body, "nav", {EPUB_TYPE: "landmarks", "id": "landmarks", "hidden": "hidden"})
    add(landmarks, "h2", text="Landmarks")
    listing = add(landmarks, "ol")
    for kind, href, label in _landmarks(documents):
        add(add(listing, "li"), "a", {EPUB_TYPE: kind, "href": href}, label)
    return html


def _contents(nav: etree._Element, documents: list[TextDocument], lang: str) -> None:
    """Every heading, as nested lists: a heading one level deeper than the one before it
    goes in a list inside that one's entry."""
    lists = [add(nav, "ol")]  # lists[n] holds the entries at level n + 1
    entry = None
    for doc in documents:
        for heading in doc.section.headings():
            if heading.level > len(lists) + 1 or (heading.level > len(lists) and entry is None):
                raise ValueError(
                    f"Heading {heading.id} is at level {heading.level} right after level "
                    f"{len(lists) if entry is not None else 0}; levels must not skip."
                )
            if heading.level > len(lists):
                lists.append(add(entry, "ol"))
            del lists[heading.level :]
            entry = add(lists[-1], "li")
            link = add(entry, "a", {"href": f"{doc.href}#{heading.id}"}, heading.text)
            heading_lang = language_tag(heading.lang) or doc.lang
            if heading_lang != lang:
                set_lang(link, heading_lang)


def _landmarks(documents: list[TextDocument]) -> list[tuple[str, str, str]]:
    """(epub:type, href, label) for the title page, if there is one, and where reading
    starts: the first body section, or else the first section after the title page."""
    landmarks = []
    titles = [doc for doc in documents if doc.section.number == 0]
    if titles:
        landmarks.append(("titlepage", titles[0].href, "Title page"))
    rest = [doc for doc in documents if doc.section.number != 0] or documents
    start = next((doc for doc in rest if doc.section.kind == "body"), rest[0])
    landmarks.append(("bodymatter", start.href, "Start reading"))
    return landmarks
