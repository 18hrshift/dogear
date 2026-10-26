"""Parse XML from untrusted book files without touching the network or the disk.

Book files come from anywhere, so the parser never loads a DTD, never fetches anything,
and refuses external entities: a reference such as `<!ENTITY x SYSTEM "file:///...">`
is a parse error, never the contents of that file. Entities declared inside the document
are expanded by libxml2, whose amplification limit stops "billion laughs" bombs.

XHTML in real EPUBs often uses HTML entities such as `&nbsp;` or `&mdash;` with no usable
DTD, which XML alone can't read. Before parsing, `html_entities_to_numeric` rewrites each
HTML named entity as the numeric reference for the same characters (`&#xA0;`). The table
is Python's own HTML5 list, so nothing outside the document is consulted. The five
entities XML defines itself (`&amp;` and friends) and unknown names are left as they are.
"""

from __future__ import annotations

import codecs
import html.entities
import re

from lxml import etree

from dogear.errors import ExtractionError

_XML_ENTITIES = frozenset({"amp", "lt", "gt", "quot", "apos"})
_ENTITY_BYTES = re.compile(rb"&([A-Za-z][A-Za-z0-9]*);")
_ENTITY_TEXT = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")


def parse_xml(data: bytes, what: str, hint: str) -> etree._Element:
    """Root element of `data`. `what` names the file in the error if it isn't valid XML."""
    parser = etree.XMLParser(
        resolve_entities="internal",
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    try:
        return etree.fromstring(html_entities_to_numeric(data), parser)
    except etree.XMLSyntaxError as e:
        raise ExtractionError(f"{what} isn't well-formed XML ({e.msg}).", hint=hint) from None


def html_entities_to_numeric(data: bytes) -> bytes:
    """`data` with HTML named entities rewritten as numeric character references."""
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return data  # Not seen in EPUBs; lxml reports any entity it can't read.
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return data  # lxml gives the better error for broken UTF-16.
        return _ENTITY_TEXT.sub(_numeric_text, text).encode("utf-16")
    # Entity names are ASCII, and in UTF-8 and the legacy single- and double-byte
    # encodings an ASCII byte is always that ASCII character, so bytes are safe to edit.
    return _ENTITY_BYTES.sub(_numeric_bytes, data)


def _numeric(name: str) -> str | None:
    if name in _XML_ENTITIES:
        return None
    chars = html.entities.html5.get(f"{name};")
    if chars is None:
        return None
    return "".join(f"&#x{ord(c):X};" for c in chars)


def _numeric_bytes(match: re.Match[bytes]) -> bytes:
    numeric = _numeric(match.group(1).decode("ascii"))
    return match.group(0) if numeric is None else numeric.encode("ascii")


def _numeric_text(match: re.Match[str]) -> str:
    numeric = _numeric(match.group(1))
    return match.group(0) if numeric is None else numeric
