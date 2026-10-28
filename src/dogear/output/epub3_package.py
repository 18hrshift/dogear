"""The EPUB package document: the book's metadata, every file in it, and reading order."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from dogear.output.epub3_smil import clock
from dogear.output.epub3_xhtml import XML_LANG, xml_safe

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
PACKAGE_FILE = "package.opf"


@dataclass(frozen=True)
class Item:
    """One file in the book, relative to the package document."""

    id: str
    href: str
    media_type: str
    properties: str = ""
    media_overlay: str = ""  # id of the SMIL item that reads this document aloud


@dataclass(frozen=True)
class Package:
    identifier: str
    title: str
    authors: tuple[str, ...]
    language: str
    publisher: str | None
    modified: str  # when the book was made: CCYY-MM-DDThh:mm:ssZ
    narrator: str
    active_class: str  # the CSS class a reading app puts on the element being read
    overlays: tuple[tuple[str, int], ...]  # (SMIL item id, milliseconds it plays)
    accessibility: tuple[tuple[str, str], ...]  # (property, value)
    items: tuple[Item, ...]
    spine: tuple[str, ...]  # item ids in reading order


def package_document(package: Package) -> etree._Element:
    root = etree.Element(
        _opf("package"),
        {"version": "3.0", "unique-identifier": "uid", XML_LANG: package.language},
        nsmap={None: OPF_NS},
    )
    _metadata(etree.SubElement(root, _opf("metadata"), nsmap={"dc": DC_NS}), package)
    manifest = etree.SubElement(root, _opf("manifest"))
    for item in package.items:
        attrs = {"id": item.id, "href": item.href, "media-type": item.media_type}
        if item.properties:
            attrs["properties"] = item.properties
        if item.media_overlay:
            attrs["media-overlay"] = item.media_overlay
        etree.SubElement(manifest, _opf("item"), attrs)
    spine = etree.SubElement(root, _opf("spine"))
    for idref in package.spine:
        etree.SubElement(spine, _opf("itemref"), {"idref": idref})
    return root


def _metadata(metadata: etree._Element, package: Package) -> None:
    _dc(metadata, "identifier", package.identifier, id="uid")
    _dc(metadata, "title", package.title)
    for n, author in enumerate(package.authors, start=1):
        _dc(metadata, "creator", author, id=f"creator{n}")
        _meta(metadata, "role", "aut", refines=f"#creator{n}", scheme="marc:relators")
    _dc(metadata, "language", package.language)
    if package.publisher:
        _dc(metadata, "publisher", package.publisher)
    _meta(metadata, "dcterms:modified", package.modified)
    total = sum(ms for _, ms in package.overlays)
    _meta(metadata, "media:duration", clock(total))
    for item_id, ms in package.overlays:
        _meta(metadata, "media:duration", clock(ms), refines=f"#{item_id}")
    _meta(metadata, "media:narrator", package.narrator)
    _meta(metadata, "media:active-class", package.active_class)
    for name, value in package.accessibility:
        _meta(metadata, name, value)


def _dc(parent: etree._Element, name: str, text: str, **attrs: str) -> None:
    etree.SubElement(parent, f"{{{DC_NS}}}{name}", attrs).text = xml_safe(text)


def _meta(parent: etree._Element, prop: str, text: str, **attrs: str) -> None:
    etree.SubElement(parent, _opf("meta"), {"property": prop, **attrs}).text = xml_safe(text)


def _opf(name: str) -> str:
    return f"{{{OPF_NS}}}{name}"


def serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)
