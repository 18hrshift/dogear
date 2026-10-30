"""What every XHTML document in a Dogear EPUB shares: namespaces, the page skeleton, and
writing it out.
"""

from __future__ import annotations

from lxml import etree

from dogear.output.xml_text import xml_safe

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
EPUB_TYPE = f"{{{EPUB_NS}}}type"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# The book's one stylesheet, beside the documents that link to it.
STYLESHEET = "dogear.css"


def new_document(title: str, lang: str) -> tuple[etree._Element, etree._Element]:
    """An empty XHTML document in `lang`, linked to the stylesheet. Returns (html, body)."""
    html = etree.Element(f"{{{XHTML_NS}}}html", nsmap={None: XHTML_NS, "epub": EPUB_NS})
    set_lang(html, lang)
    head = add(html, "head")
    add(head, "title", text=title)
    add(head, "link", {"rel": "stylesheet", "type": "text/css", "href": STYLESHEET})
    return html, add(html, "body")


def add(
    parent: etree._Element, tag: str, attrs: dict[str, str] | None = None, text: str | None = None
) -> etree._Element:
    """A new XHTML element at the end of `parent`."""
    safe = {name: xml_safe(value) for name, value in (attrs or {}).items()}
    element = etree.SubElement(parent, f"{{{XHTML_NS}}}{tag}", safe)
    element.text = None if text is None else xml_safe(text)
    return element


def set_lang(element: etree._Element, lang: str | None) -> None:
    """Mark `element` as being in `lang`. HTML reads `lang` and XML reads `xml:lang`, so
    both are set, to the same value as the format requires."""
    if lang:
        element.set(XML_LANG, lang)
        element.set("lang", lang)


def serialize(html: etree._Element) -> bytes:
    return etree.tostring(
        html, xml_declaration=True, encoding="utf-8", doctype="<!DOCTYPE html>", pretty_print=True
    )
