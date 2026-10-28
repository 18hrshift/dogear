"""What the talking book says about its own accessibility, decided from what is in it.

The claims (EPUB Accessibility 1.1, schema.org terms) describe this book, not the one it
was made from, and claim nothing that isn't there:

- No pictures are included, only the words that described them, so the book is text
  and audio and claims no alternative text: there is no visual content to stand in for.
- Its audio is complete, and its text fully in step with it, only when every sentence,
  heading, and table row shown is also read aloud. A skipped table, for one, isn't.
- Page navigation is claimed only when there are print page numbers, and their source
  is named. The source is the book Dogear read, by its identifier, since the page
  numbers are that book's. A book with no identifier is named by title and authors.
- No conformance to an accessibility standard is claimed: nobody has checked this book.
"""

from __future__ import annotations

from dogear.document import Metadata
from dogear.readalong.model import (
    HeadingText,
    ImageText,
    ListText,
    NoteText,
    ParagraphText,
    SectionText,
    TableText,
    TextItem,
)


def accessibility_metadata(
    sections: list[SectionText], metadata: Metadata, narrator: str
) -> list[tuple[str, str]]:
    """(property, value) pairs for the package's metadata, in order."""
    complete = _all_read_aloud(sections)
    pages = any(section.pages() for section in sections)
    headings = any(section.headings() for section in sections)
    tables_skipped = any(_table_unread(item) for s in sections for item in s.items)
    properties = [("schema:accessMode", "textual"), ("schema:accessMode", "auditory")]
    properties.append(("schema:accessModeSufficient", "textual"))
    if complete:
        properties.append(("schema:accessModeSufficient", "auditory"))
    features = ["tableOfContents", "readingOrder"]
    features += ["structuralNavigation"] if headings else []
    features += ["synchronizedAudioText"] if complete else []
    features += ["pageBreakMarkers", "pageNavigation"] if pages else []
    properties += [("schema:accessibilityFeature", feature) for feature in features]
    properties.append(("schema:accessibilityHazard", "none"))
    summary = _summary(narrator, complete, tables_skipped, pages)
    properties.append(("schema:accessibilitySummary", summary))
    if pages:
        properties.append(("pageBreakSource", page_source(metadata)))
    return properties


def page_source(metadata: Metadata) -> str:
    """Where the print page numbers come from: the source book's identifier, or failing
    that its title and authors."""
    if metadata.identifier and metadata.identifier.strip():
        return metadata.identifier.strip()
    authors = ", ".join(a.strip() for a in metadata.authors if a.strip())
    return f"{metadata.title.strip()}, by {authors}" if authors else metadata.title.strip()


def _summary(narrator: str, complete: bool, tables_skipped: bool, pages: bool) -> str:
    sentences = [
        f"A talking book: the text, read aloud by {narrator}, with each sentence "
        "highlighted as it is read."
    ]
    if not complete:
        sentences.append(
            "Some text is shown but not read aloud."
            + (" Tables were left out of the narration." if tables_skipped else "")
        )
    sentences.append(
        "Pictures are not included; where the source book described one, the description "
        "is part of the text."
    )
    if pages:
        sentences.append("Print page numbers from the source book are marked and listed.")
    sentences.append(
        "The narration was made automatically by Dogear and has not been checked by a "
        "person, and the book has not been evaluated against an accessibility standard."
    )
    return " ".join(sentences)


def _all_read_aloud(sections: list[SectionText]) -> bool:
    """Whether every sentence, heading, and table row shown is also read aloud."""
    for section in sections:
        synced = {sync.target for sync in section.syncs}
        for item in section.items:
            ids = _shown_ids(item)
            if ids is None or not ids <= synced:
                return False
    return True


def _shown_ids(item: TextItem) -> set[str] | None:
    """Ids of the parts of `item` a reader sees, or None when some part has none."""
    match item:
        case HeadingText(id=id_):
            return {id_}
        case ParagraphText(sentences=s) | NoteText(sentences=s):
            return {x.id for x in s}
        case ListText(items=items):
            return {x.id for entry in items for x in entry}
        case ImageText(description=description, caption=caption):
            return {x.id for x in description + caption}
        case TableText(caption=caption, rows=rows):
            if _table_unread(item):
                return None
            return {x.id for x in caption} | {row.id for row in rows if row.id}
    return set()  # page breaks and scene breaks show no text of their own


def _table_unread(item: TextItem) -> bool:
    """A table whose rows are shown but not read: skipped, or only header rows."""
    if not isinstance(item, TableText):
        return False
    return any(row.id is None for row in item.rows) or (bool(item.header_rows) and not item.rows)
