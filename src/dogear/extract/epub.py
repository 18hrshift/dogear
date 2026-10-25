"""Read an EPUB (2 or 3) into a `dogear.document.Book`.

The archive is read in memory with `zipfile` and every XML file goes through
`safe_xml.parse_xml`, so a book can't make Dogear touch the network or other files.
Each XHTML file in the reading order (the spine) becomes one Section.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from lxml import etree

from dogear.config import Config
from dogear.document import Book, Footnote, Heading, Paragraph, Section, SectionKind
from dogear.errors import ExtractionError
from dogear.extract.epub_nav import Navigation, read_navigation
from dogear.extract.epub_package import (
    DAMAGED_HINT,
    XHTML_MEDIA_TYPE,
    EpubArchive,
    Package,
    find_package_path,
    read_encrypted_paths,
    read_package,
)
from dogear.extract.xhtml import lang_of, local_name, semantics
from dogear.extract.xhtml_blocks import body_blocks

log = logging.getLogger(__name__)

# How epub:type tokens (and DPUB-ARIA doc-* roles) on a document's <body> or its top-level
# <section> elements, or on the book's landmark links, set a section's kind. In order:
#   1. A matter token on the document itself.
#   2. The landmarks: a matter token there, then a specific token there.
#   3. A specific token on the document itself.
#   4. Otherwise "body".
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

DRM_HINT = (
    "Dogear needs a DRM-free copy. Many stores and public-domain libraries sell or give "
    "away DRM-free EPUBs, and libraries for print-disabled readers can provide accessible "
    "copies."
)


def extract(path: Path, config: Config) -> Book:
    """Read the EPUB at `path`. `config` is accepted for the extractor interface."""
    with EpubArchive(path) as archive:
        opf_path = find_package_path(archive)
        encrypted = read_encrypted_paths(archive)
        if opf_path in encrypted:
            raise _drm_error(archive.name)
        package = read_package(archive, opf_path, fallback_title=path.stem)
        content = {i.path for i in package.manifest.values() if i.media_type == XHTML_MEDIA_TYPE}
        if content & encrypted:
            raise _drm_error(archive.name)
        sections = _read_sections(archive, package, read_navigation(archive, package))
    if not sections:
        raise ExtractionError(
            f"{path.name} has no readable text: every document in its reading order is empty.",
            hint="If it's a picture book or a scan, it has no text for Dogear to read aloud.",
        )
    return Book(
        metadata=package.metadata,
        sections=sections,
        source_path=path,
        source_format="epub",
    )


def _drm_error(name: str) -> ExtractionError:
    return ExtractionError(
        f"{name} is protected by DRM (copy protection), so Dogear can't read its text.",
        hint=DRM_HINT,
    )


def _read_sections(archive: EpubArchive, package: Package, nav: Navigation) -> list[Section]:
    note_markers: dict[tuple[str, str], str] = {}
    sections: list[Section] = []
    for ref in package.spine:
        item = package.manifest.get(ref.idref)
        if item is None:
            raise ExtractionError(
                f"The reading order of {archive.name} names '{ref.idref}', "
                "which isn't in the book's list of files.",
                hint=DAMAGED_HINT,
            )
        if "nav" in item.properties:
            log.info("Skipped %s as content: it is the navigation document.", item.href)
            continue
        if not ref.linear:
            log.info('Skipped %s: the book marks it linear="no" (outside the reading order).', item.href)
            continue
        if item.media_type != XHTML_MEDIA_TYPE:
            log.warning(
                "Skipped %s in %s: Dogear can't read %s documents.",
                item.href,
                archive.name,
                item.media_type or "untyped",
            )
            continue
        if item.path is None or not archive.has(item.path):
            raise ExtractionError(
                f"{archive.name} lists {item.href} in its reading order, but the file is missing.",
                hint=DAMAGED_HINT,
            )
        section = _read_section(archive, item.path, nav, package, note_markers, len(sections) + 1)
        if section is None:
            log.debug("Skipped %s: it has no content.", item.path)
        else:
            sections.append(section)
    _link_notes(sections, note_markers)
    return sections


def _read_section(
    archive: EpubArchive,
    doc_path: str,
    nav: Navigation,
    package: Package,
    note_markers: dict[tuple[str, str], str],
    number: int,
) -> Section | None:
    root = archive.parse(doc_path)
    body = root.find("{*}body")
    if body is None:
        raise ExtractionError(f"{doc_path} in {archive.name} has no <body>.", hint=DAMAGED_HINT)
    lang = lang_of(body, lang_of(root, package.metadata.language))
    blocks = body_blocks(
        body,
        doc_path=doc_path,
        section_lang=lang,
        page_labels=nav.page_labels.get(doc_path, {}),
        note_markers=note_markers,
    )
    if not blocks:
        return None
    first_heading = next((b.text for b in blocks if isinstance(b, Heading)), "")
    return Section(
        title=nav.titles.get(doc_path) or " ".join(first_heading.split()) or f"Section {number}",
        kind=section_kind(body, nav.landmarks.get(doc_path, frozenset())),
        blocks=blocks,
        lang=lang,
        source=doc_path,
    )


def section_kind(body: etree._Element, landmark_tokens: frozenset[str]) -> SectionKind:
    """Front, body, or back matter, decided as described at MATTER_KINDS."""
    top_sections = [c for c in body if isinstance(c.tag, str) and local_name(c) == "section"]
    own = [semantics(el) for el in [body, *top_sections]]
    for tokens in own:
        if kind := _kind_for(tokens, MATTER_KINDS):
            return kind
    landmark = _kind_for(landmark_tokens, MATTER_KINDS) or _kind_for(landmark_tokens, SPECIFIC_KINDS)
    if landmark:
        return landmark
    for tokens in own:
        if kind := _kind_for(tokens, SPECIFIC_KINDS):
            return kind
    return "body"


def _kind_for(tokens: frozenset[str], mapping: dict[str, SectionKind]) -> SectionKind | None:
    return next((kind for token, kind in mapping.items() if token in tokens), None)


def _link_notes(sections: list[Section], note_markers: dict[tuple[str, str], str]) -> None:
    """Label notes with the marker printed where they're referenced, and report problems."""
    found: dict[str, str] = {}  # note id -> file it was first found in
    for section in sections:
        for i, block in enumerate(section.blocks):
            if not isinstance(block, Footnote):
                continue
            first = found.setdefault(block.note_id, section.source)
            if first != section.source:
                log.warning(
                    "Note id %r is used in both %s and %s, so references to it are ambiguous.",
                    block.note_id,
                    first,
                    section.source,
                )
            marker = note_markers.get((section.source, block.note_id))
            if marker:
                section.blocks[i] = replace(block, label=marker)
    missing = {
        ref
        for section in sections
        for block in section.blocks
        if isinstance(block, Paragraph)
        for ref in block.note_refs
        if ref not in found
    }
    if missing:
        log.warning(
            "%d note references point to notes that aren't in the reading order (for example "
            "%r), so those notes won't be read.",
            len(missing),
            sorted(missing)[0],
        )
