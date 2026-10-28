"""Reading a built EPUB back in tests: its zip entries, and its XML parsed with lxml."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "x": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
    "smil": "http://www.w3.org/ns/SMIL",
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
}
EPUB_TYPE = f"{{{NS['epub']}}}type"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def milliseconds(clock: str) -> int:
    """A SMIL clock value such as 0:01:02.345 in milliseconds."""
    hours, minutes, seconds = clock.split(":")
    return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


class Epub:
    def __init__(self, path: Path) -> None:
        with zipfile.ZipFile(path) as book:
            self.entries = book.infolist()
            self.files = {entry.filename: book.read(entry) for entry in self.entries}
        container = self.xml("META-INF/container.xml")
        [self.package_path] = container.xpath("//c:rootfile/@full-path", namespaces=NS)
        self.root = self.package_path.rsplit("/", 1)[0] + "/"
        self.package = self.xml(self.package_path)

    def xml(self, name: str) -> etree._Element:
        return etree.fromstring(self.files[name])

    def xpath(self, element: etree._Element, path: str) -> list:
        return element.xpath(path, namespaces=NS)

    def meta(self, prop: str) -> list[str]:
        """Values of the package's top-level <meta property=prop>, in order."""
        return self.xpath(self.package, f"//opf:meta[@property='{prop}' and not(@refines)]/text()")

    def refined(self, prop: str) -> dict[str, str]:
        """{refined id: value} for <meta property=prop refines=...>."""
        metas = self.xpath(self.package, f"//opf:meta[@property='{prop}' and @refines]")
        return {m.get("refines").lstrip("#"): m.text for m in metas}

    def dc(self, name: str) -> list[str]:
        return self.xpath(self.package, f"//dc:{name}/text()")

    def items(self) -> dict[str, etree._Element]:
        return {item.get("id"): item for item in self.xpath(self.package, "//opf:item")}

    def spine(self) -> list[etree._Element]:
        """The manifest items of the spine, in reading order."""
        items = self.items()
        return [items[ref] for ref in self.xpath(self.package, "//opf:itemref/@idref")]

    def doc(self, href: str) -> etree._Element:
        return self.xml(self.root + href)

    def ids(self, href: str) -> set[str]:
        return set(self.xpath(self.doc(href), "//@id"))

    def nav(self) -> etree._Element:
        [href] = [i.get("href") for i in self.items().values() if i.get("properties") == "nav"]
        return self.doc(href)

    def overlays(self) -> list[tuple[str, etree._Element]]:
        """(SMIL item id, its parsed SMIL) for each spine document, in reading order."""
        items = self.items()
        return [
            (doc.get("media-overlay"), self.doc(items[doc.get("media-overlay")].get("href")))
            for doc in self.spine()
        ]

    def clips(self, smil: etree._Element) -> list[tuple[int, int]]:
        audios = self.xpath(smil, "//smil:audio")
        return [(milliseconds(a.get("clipBegin")), milliseconds(a.get("clipEnd"))) for a in audios]
