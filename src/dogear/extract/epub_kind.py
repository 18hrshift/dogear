"""Decide whether a stretch of an EPUB is front, body, or back matter.

The book says so with epub:type tokens (and DPUB-ARIA doc-* roles) on a document's <body>
or its top-level <section> elements, or on its landmark links. In order:
  1. A matter token on the document itself.
  2. The landmarks: a matter token there, then a specific token there.
  3. A specific token on the document itself.
When none of these is present, the caller picks a default from where the content sits.
"""

from __future__ import annotations

from lxml import etree

from dogear.document import SectionKind
from dogear.extract.xhtml import local_name, semantics

MATTER_KINDS: dict[str, SectionKind] = {
    "frontmatter": "front",
    "bodymatter": "body",
    "backmatter": "back",
}
SPECIFIC_KINDS: dict[str, SectionKind] = {
    "cover": "front",
    "titlepage": "front",
    "halftitlepage": "front",
    "copyright-page": "front",
    "seriespage": "front",
    "dedication": "front",
    "epigraph": "front",
    "toc": "front",
    "imprint": "front",
    "foreword": "front",
    "preface": "front",
    "appendix": "back",
    "colophon": "back",
    "index": "back",
    "glossary": "back",
    "bibliography": "back",
    "endnotes": "back",
    "rearnotes": "back",
}


def marked_kind(body: etree._Element, landmark_tokens: frozenset[str]) -> SectionKind | None:
    """The kind the book marks `body` as, decided as described above, or None if unmarked."""
    top_sections = [c for c in body if isinstance(c.tag, str) and local_name(c) == "section"]
    own = [semantics(el) for el in [body, *top_sections]]
    for tokens in own:
        if kind := _kind_for(tokens, MATTER_KINDS):
            return kind
    for mapping in (MATTER_KINDS, SPECIFIC_KINDS):
        if kind := _kind_for(landmark_tokens, mapping):
            return kind
    for tokens in own:
        if kind := _kind_for(tokens, SPECIFIC_KINDS):
            return kind
    return None


def _kind_for(tokens: frozenset[str], mapping: dict[str, SectionKind]) -> SectionKind | None:
    return next((kind for token, kind in mapping.items() if token in tokens), None)
