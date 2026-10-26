"""Read an EPUB's navigation: the table of contents, landmarks, and the print page list.

EPUB 3 books have a navigation document (XHTML with `nav` elements). EPUB 2 books have an
NCX file instead. Both are read into the same `Navigation`, keyed by archive path.

A table-of-contents entry's depth counts only the entries that link somewhere: an EPUB 3
heading with no link (`<li><span>Part One</span><ol>...`) groups its children without
adding a level, because it can't start a section.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from lxml import etree

from dogear.errors import ExtractionError
from dogear.extract.epub_package import EpubArchive, Package
from dogear.extract.xhtml import EPUB_TYPE, plain_text, resolve_href

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TocEntry:
    path: str  # archive path of the file it points into
    fragment: str  # id of the element where it starts, or "" for the start of the file
    title: str  # may be empty
    depth: int  # 1 for a top-level entry


@dataclass
class Navigation:
    # Table-of-contents entries in the order the book lists them.
    toc: list[TocEntry] = field(default_factory=list)
    # epub:type tokens of the landmark links that point into each file.
    landmarks: dict[str, frozenset[str]] = field(default_factory=dict)
    # Print page labels by file, then by the id of the element where the page begins.
    page_labels: dict[str, dict[str, str]] = field(default_factory=dict)


def read_navigation(archive: EpubArchive, package: Package) -> Navigation:
    """The book's navigation, or an empty one (with a warning) if it can't be read."""
    path = package.nav_path or package.ncx_path
    if path is None:
        log.info("%s has no table of contents.", archive.name)
        return Navigation()
    if not archive.has(path):
        log.warning("The table of contents (%s) is missing from %s.", path, archive.name)
        return Navigation()
    try:
        root = archive.parse(path)
    except ExtractionError as e:
        log.warning("%s Dogear will read the book without its table of contents.", e.message)
        return Navigation()
    if package.nav_path:
        return _from_nav_document(root, path)
    return _from_ncx(root, path)


def _from_nav_document(root: etree._Element, nav_path: str) -> Navigation:
    nav = Navigation()
    toc_read = False
    for nav_el in root.iter("{*}nav"):
        types = set((nav_el.get(EPUB_TYPE) or "").split())
        if "toc" in types and not toc_read:
            toc_read = True
            nav.toc = list(_toc_entries(nav_el, nav_path))
        links = list(_links(nav_el, nav_path))
        if "landmarks" in types:
            for path, _, _, tokens in links:
                nav.landmarks[path] = nav.landmarks.get(path, frozenset()) | tokens
        if "page-list" in types:
            for path, fragment, text, _ in links:
                _add_page(nav, path, fragment, text)
    return nav


def _toc_entries(nav_el: etree._Element, nav_path: str) -> Iterator[TocEntry]:
    """Entries of a toc nav element. Depth counts the list items around it that hold a link."""
    linked: set[etree._Element] = set()
    for a in nav_el.iter("{*}a"):  # document order: parents before children
        href = a.get("href")
        target = resolve_href(nav_path, href) if href else None
        if target is None:
            continue
        items = list(a.iterancestors("{*}li"))
        if items:
            linked.add(items[0])
        depth = max(1, sum(1 for li in items if li in linked))
        yield TocEntry(target[0], target[1], plain_text(a), depth)


def _links(nav_el: etree._Element, nav_path: str) -> Iterator[tuple[str, str, str, frozenset[str]]]:
    """(path, fragment, link text, epub:type tokens) for each link in a nav element."""
    for a in nav_el.iter("{*}a"):
        href = a.get("href")
        target = resolve_href(nav_path, href) if href else None
        if target is None:
            continue
        tokens = frozenset((a.get(EPUB_TYPE) or "").split())
        yield target[0], target[1], plain_text(a), tokens


def _from_ncx(root: etree._Element, ncx_path: str) -> Navigation:
    nav = Navigation()
    nav_map = root.find("{*}navMap")
    linked: set[etree._Element] = set()  # navPoints whose own target resolves
    points = nav_map.iter("{*}navPoint") if nav_map is not None else ()
    for point in points:  # document order: parents before children
        target = _ncx_target(point, ncx_path)
        if target is None:
            continue
        linked.add(point)
        depth = sum(1 for anc in point.iterancestors("{*}navPoint") if anc in linked) + 1
        nav.toc.append(TocEntry(target[0], target[1], _ncx_label(point), depth))
    for page in root.iter("{*}pageTarget"):
        target = _ncx_target(page, ncx_path)
        if target is not None:
            _add_page(nav, target[0], target[1], _ncx_label(page) or page.get("value") or "")
    return nav


def _ncx_label(el: etree._Element) -> str:
    text = el.find("{*}navLabel/{*}text")
    return plain_text(text) if text is not None else ""


def _ncx_target(el: etree._Element, ncx_path: str) -> tuple[str, str] | None:
    content = el.find("{*}content")
    src = content.get("src") if content is not None else None
    return resolve_href(ncx_path, src) if src else None


def _add_page(nav: Navigation, path: str, fragment: str, label: str) -> None:
    if fragment and label:
        nav.page_labels.setdefault(path, {})[fragment] = label
