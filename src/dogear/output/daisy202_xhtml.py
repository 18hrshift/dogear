"""XHTML 1.0 Transitional, as DAISY 2.02 wants its NCC and text documents written.

Shared by the NCC and the text documents: the document skeleton, language tags that
validators accept, text that XML can hold, and writing a file that older players, some of
which read it as plain HTML, can still parse.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lxml import etree

log = logging.getLogger(__name__)

NS = "http://www.w3.org/1999/xhtml"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
DOCTYPE = (
    '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
    '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">'
)

# Elements HTML writes without an end tag. Any other element left empty is written
# with one (<p></p>, not <p/>), which an HTML parser would read as an unclosed start tag.
_VOID = {"meta", "link", "hr", "br", "img", "col", "area", "base", "input", "param"}
# xsd:language, which the DAISY validator checks dc:language and lang against.
_LANGUAGE = re.compile(r"[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*")
# Characters XML 1.0 can't hold at all, such as control codes a PDF may carry.
_NOT_XML = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


def element(tag: str, parent: etree._Element | None = None, **attrs: str) -> etree._Element:
    """An XHTML element, added to `parent` when given."""
    name = f"{{{NS}}}{tag}"
    if parent is None:
        return etree.Element(name, attrs)
    return etree.SubElement(parent, name, attrs)


def text(value: str) -> str:
    """`value` with any characters XML can't hold taken out."""
    return _NOT_XML.sub("", value)


def document(title: str, lang: str) -> tuple[etree._Element, etree._Element, etree._Element]:
    """A new document's html, head, and body, with its title and character set."""
    html = etree.Element(f"{{{NS}}}html", nsmap={None: NS})
    set_lang(html, lang)
    head = element("head", html)
    element("meta", head, **{"http-equiv": "Content-Type", "content": "text/html; charset=utf-8"})
    element("title", head).text = text(title)
    return html, head, element("body", html)


def meta(head: etree._Element, name: str, content: str, **attrs: str) -> None:
    element("meta", head, name=name, content=text(content), **attrs)


def set_lang(el: etree._Element, lang: str) -> None:
    """Both xml:lang and lang, as XHTML 1.0 asks, for parsers of either kind."""
    el.set(XML_LANG, lang)
    el.set("lang", lang)


def language_tag(tag: str | None, where: str) -> str | None:
    """A book's language tag in the form validators accept, or None if it has none.

    'en_US' becomes 'en-US'. A tag that still isn't a language tag is reported and left
    out, so the text takes its surroundings' language. `where` names it in that report.
    """
    if tag is None or not tag.strip():
        return None
    cleaned = tag.strip().replace("_", "-")
    if _LANGUAGE.fullmatch(cleaned):
        return cleaned
    log.warning("Ignoring the language %r of %s: it isn't a language tag.", tag, where)
    return None


def write(html: etree._Element, path: Path) -> None:
    """Write the document as UTF-8 XHTML with its doctype."""
    for el in html.iter():
        if etree.QName(el).localname not in _VOID and el.text is None and len(el) == 0:
            el.text = ""
    etree.ElementTree(html).write(
        str(path), encoding="utf-8", xml_declaration=True, doctype=DOCTYPE, pretty_print=True
    )
