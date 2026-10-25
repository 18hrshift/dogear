"""The structured book that every extractor produces and every later stage reads.

Text in this model is display text: what a sighted reader would see, minus layout noise
such as running headers or line-end hyphens. Spoken forms (expanded abbreviations,
numbers as words) are made later by `dogear.speech` and never stored here, so read-along
output can still show the original words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SectionKind = Literal["front", "body", "back"]
SECTION_KINDS: tuple[SectionKind, ...] = ("front", "body", "back")


def _require_text(value: str, what: str) -> None:
    if not value.strip():
        raise ValueError(f"{what} must not be empty")


@dataclass(frozen=True, kw_only=True)
class _TextBlock:
    # BCP 47 language tag, set only when it differs from the section's language.
    lang: str | None = None


@dataclass(frozen=True)
class Heading(_TextBlock):
    level: int  # 1 to 6, as in HTML
    text: str

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 6:
            raise ValueError(f"heading level must be 1-6, got {self.level}")
        _require_text(self.text, "heading text")


@dataclass(frozen=True)
class Paragraph(_TextBlock):
    text: str
    # Ids of Footnote blocks referenced in this paragraph, in reading order. The printed
    # markers ("1", "*") are removed from `text` so they are not spoken mid-sentence.
    note_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.text, "paragraph text")


@dataclass(frozen=True)
class ListBlock(_TextBlock):
    items: tuple[str, ...]
    ordered: bool = False

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("list must have at least one item")
        for item in self.items:
            _require_text(item, "list item")


@dataclass(frozen=True)
class Table(_TextBlock):
    rows: tuple[tuple[str, ...], ...]
    header_rows: int = 0
    caption: str = ""

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("table must have at least one row")
        if not 0 <= self.header_rows <= len(self.rows):
            raise ValueError("header_rows is out of range")


@dataclass(frozen=True)
class Image(_TextBlock):
    # None: the source gave no description. "": marked decorative on purpose.
    alt: str | None
    caption: str = ""


@dataclass(frozen=True)
class Footnote(_TextBlock):
    note_id: str
    text: str
    label: str = ""  # the marker as printed, such as "1" or "*"

    def __post_init__(self) -> None:
        _require_text(self.note_id, "footnote id")
        _require_text(self.text, "footnote text")


@dataclass(frozen=True)
class PageMarker:
    """Where a print page begins. Used for navigation, not spoken by default."""

    label: str  # as printed: "42", "xii"

    def __post_init__(self) -> None:
        _require_text(self.label, "page label")


Block = Heading | Paragraph | ListBlock | Table | Image | Footnote | PageMarker


def block_text(block: Block) -> str:
    """The readable words in a block, for word counts and previews."""
    match block:
        case Heading(text=text) | Paragraph(text=text) | Footnote(text=text):
            return text
        case ListBlock(items=items):
            return "\n".join(items)
        case Table(rows=rows, caption=caption):
            cells = "\n".join(" ".join(row) for row in rows)
            return f"{caption}\n{cells}".strip()
        case Image(alt=alt, caption=caption):
            return f"{alt or ''}\n{caption}".strip()
        case PageMarker():
            return ""
    raise TypeError(f"not a block: {block!r}")


def _word_count(text: str) -> int:
    return len(text.split())


@dataclass
class Section:
    """A top-level navigation unit, usually a chapter. Each becomes one audio track."""

    title: str
    kind: SectionKind = "body"
    blocks: list[Block] = field(default_factory=list)
    lang: str | None = None
    source: str = ""  # where it came from, such as "chapter01.xhtml" or "pages 5-12"

    def __post_init__(self) -> None:
        _require_text(self.title, "section title")
        if self.kind not in SECTION_KINDS:
            raise ValueError(f"section kind must be one of {SECTION_KINDS}, got {self.kind!r}")

    def word_count(self) -> int:
        return sum(_word_count(block_text(b)) for b in self.blocks)

    def page_labels(self) -> list[str]:
        return [b.label for b in self.blocks if isinstance(b, PageMarker)]

    def slug(self, index: int) -> str:
        """Filesystem-safe name such as '01_chapter_one'."""
        safe = "".join(c if c.isalnum() or c == " " else "" for c in self.title.lower())
        return f"{index:02d}_{'_'.join(safe.split()) or 'section'}"


@dataclass
class Metadata:
    title: str
    authors: list[str] = field(default_factory=list)
    language: str | None = None  # BCP 47, such as "en" or "en-GB"
    identifier: str | None = None
    publisher: str | None = None


@dataclass
class Book:
    metadata: Metadata
    sections: list[Section]
    source_path: Path
    source_format: str  # "epub", "pdf", "mobi", ...

    def word_count(self) -> int:
        return sum(s.word_count() for s in self.sections)
