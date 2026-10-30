"""Spoken structure: what a section sounds like, as a list of utterances.

Structure a sighted reader sees (headings, paragraphs, images, notes, scene breaks) is
turned into words and pauses a listener can hear. Longer pauses mark bigger breaks: a
sentence, a paragraph, a heading, a scene, a chapter. Every choice here comes from the
[narration] settings.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field, replace

from dogear.config import Config
from dogear.document import (
    Block,
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    PageMarker,
    Paragraph,
    SceneBreak,
    Section,
    Table,
)
from dogear.speech.normalize import SpeechRules, normalize_for_speech, normalize_heading
from dogear.speech.sentences import SentenceRules, split_sentences

log = logging.getLogger(__name__)

_ENDS_CLAUSE = (".", "!", "?", ":", ";", ",", "…")


@dataclass(frozen=True)
class Utterance:
    text: str  # display text, for read-along output; "" for a pure pause
    spoken: str  # what the voice says; "" for a pure pause
    pause_ms: int  # silence after it


@dataclass(frozen=True)
class Passage:
    """Where one block sits among a section's utterances, so read-along text can show it.

    `parts` are ranges of utterance indexes. What each part holds depends on the block:

    - Heading, Paragraph, Footnote: one part, the block's sentences.
    - ListBlock: one part per item.
    - Table: the introduction ("Table: Prices."), then one part per body row read aloud.
      When tables are skipped, only the introduction, which then holds the "not read"
      sentence too.
    - Image: the description, then the caption. Either may be empty.
    - PageMarker: one part, "Page 42." when pages are announced, otherwise empty.
    - SceneBreak: no parts.

    An empty part still has a position: the index of the utterance that follows it.
    Blocks that add nothing to the narration (a note already read, a decorative image)
    have no passage, except page markers and scene breaks, which mark places.
    """

    block: Block
    parts: tuple[range, ...]


@dataclass(frozen=True)
class SectionNarration:
    number: int  # 1-based, as `dogear outline` shows it; 0 for the title track
    section: Section
    utterances: list[Utterance]
    passages: list[Passage] = field(default_factory=list)  # in reading order

    def words(self) -> int:
        return sum(len(u.spoken.split()) for u in self.utterances)


def narrate_book(book: Book, config: Config) -> list[SectionNarration]:
    """Every section's narration, leaving out sections that end up with nothing to say."""
    narrator = _Narrator(book, config)
    narrations = []
    for number, section in enumerate(book.sections, start=1):
        read_earlier = set(narrator.read_notes)
        utterances, passages = narrator.section(section)
        if narrator.has_content(utterances, section, read_earlier):
            narrations.append(SectionNarration(number, section, utterances, passages))
        else:
            log.info(
                "Section %d, %s, was left out of the audio: its notes are read where the "
                "text refers to them.",
                number,
                section.title,
            )
    return narrations


def narrate_title(book: Book, config: Config) -> SectionNarration:
    """A short opening track: the book's title, then who wrote it."""
    metadata = book.metadata
    words = config["narration"]["words"]
    blocks: list[Block] = [Heading(1, metadata.title)]
    if metadata.authors:
        blocks.append(Paragraph(f"{words['by']} {_join(metadata.authors, words['and'])}."))
    section = Section(metadata.title, kind="front", blocks=blocks)
    utterances, passages = _Narrator(book, config).section(section)
    return SectionNarration(0, section, utterances, passages)


def opens_with_title(narration: SectionNarration, title: str) -> bool:
    """Whether a section starts by saying the book's title, as most title pages do."""
    first = narration.passages[0].block if narration.passages else None
    return isinstance(first, Heading) and _words(first.text) == _words(title)


def _words(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", "", text).casefold().split()


class _Narrator:
    def __init__(self, book: Book, config: Config) -> None:
        self.settings = config["narration"]
        self.pauses = config["narration"]["pauses"]
        self.words = config["narration"]["words"]
        self.speech = SpeechRules.from_config(config)
        self.sentences = SentenceRules.from_config(config)
        self.language = book.metadata.language
        self.notes = {
            b.note_id: b for s in book.sections for b in s.blocks if isinstance(b, Footnote)
        }
        self.read_notes: set[str] = set()
        self.title_level = _title_level(book)
        self._passages: list[Passage] = []

    def has_content(
        self, utterances: list[Utterance], section: Section, read_earlier: set[str]
    ) -> bool:
        """False for a section whose only content was notes already read in earlier sections.

        `read_earlier` must be taken before narrating the section: narrating it marks its
        own notes as read, and those were read here, not elsewhere.
        """
        spoken_blocks = [b for b in section.blocks if not isinstance(b, PageMarker | SceneBreak)]
        all_notes_read = all(
            isinstance(b, Heading) or (isinstance(b, Footnote) and b.note_id in read_earlier)
            for b in spoken_blocks
        )
        has_notes = any(isinstance(b, Footnote) for b in spoken_blocks)
        return not (has_notes and all_notes_read) and any(u.spoken for u in utterances)

    def section(self, section: Section) -> tuple[list[Utterance], list[Passage]]:
        out = [Utterance("", "", self.pauses["section_start_ms"])]
        self._passages = []
        lang = section.lang or self.language
        top = _first_heading_level(section)
        if top is None:
            top = self.title_level
            self._add_heading(out, Heading(top, section.title), lang)
        end_notes: list[Footnote] = []
        for block in _heading_first(section.blocks):
            self._block(out, block, block_lang(block, lang), end_notes)
        if end_notes:
            self._add_heading(out, Heading(min(top + 1, 6), self.words["notes"]), lang)
            for note in end_notes:
                self._note(out, note, block_lang(note, lang))
        _extend_pause(out, self.pauses["section_end_ms"])
        return out, self._passages

    def _block(self, out: list[Utterance], block, lang: str | None, end_notes: list) -> None:
        match block:
            case Heading():
                self._add_heading(out, block, lang)
            case Paragraph(text=text, note_refs=refs):
                part = self._sentences(out, text, lang, self.pauses["paragraph_ms"])
                self._passages.append(Passage(block, (part,)))
                if self.settings["footnotes"] == "after_paragraph":
                    for note_id in refs:
                        if note_id in self.notes and note_id not in self.read_notes:
                            note = self.notes[note_id]
                            self._note(out, note, block_lang(note, lang))
            case ListBlock(items=items, ordered=ordered):
                parts = []
                for n, item in enumerate(items, start=1):
                    # The number is said ("1: Buy milk.", which stays one utterance where
                    # "1. Buy milk." would split in two) but not shown: a list shows its own.
                    prefix = f"{n}: " if ordered else ""
                    parts.append(self._sentences(out, _sentence(item), lang, 0, prefix))
                    _extend_pause(out, self.pauses["list_item_ms"])
                _extend_pause(out, self.pauses["paragraph_ms"])
                self._passages.append(Passage(block, tuple(parts)))
            case Table():
                self._table(out, block, lang)
            case Image():
                self._image(out, block, lang)
            case Footnote(note_id=note_id):
                mode = self.settings["footnotes"]
                if mode == "end_of_section":
                    end_notes.append(block)
                elif mode != "skip" and note_id not in self.read_notes:
                    self._note(out, block, lang)
            case PageMarker(label=label):
                part = range(len(out), len(out))
                if self.settings["announce_pages"]:
                    part = self._sentences(out, f"{self.words['page']} {label}.", lang, 0)
                    _extend_pause(out, self.pauses["sentence_ms"])
                self._passages.append(Passage(block, (part,)))
            case SceneBreak():
                _extend_pause(out, self.pauses["scene_break_ms"])
                self._passages.append(Passage(block, ()))
            case _:
                raise TypeError(f"not a block: {block!r}")

    def _add_heading(self, out: list[Utterance], heading: Heading, lang: str | None) -> None:
        start = len(out)
        self._heading(out, heading.text, lang)
        self._passages.append(Passage(heading, (range(start, len(out)),)))

    def _heading(self, out: list[Utterance], text: str, lang: str | None) -> None:
        if out[-1].spoken:
            _extend_pause(out, self.pauses["paragraph_ms"])  # a breath before it, too
        spoken = normalize_heading(text, self.speech, lang)
        if not spoken.endswith(_ENDS_CLAUSE):
            spoken += "."  # so the voice closes the heading instead of trailing off
        out.append(Utterance(text, spoken, self.pauses["heading_ms"]))

    def _sentences(
        self, out: list[Utterance], text: str, lang: str | None, end_ms: int, prefix: str = ""
    ) -> range:
        """Add `text` sentence by sentence. `prefix` is said before the first, not shown."""
        start = len(out)
        for n, sentence in enumerate(split_sentences(text, self.sentences)):
            said = prefix + sentence if n == 0 else sentence
            spoken = normalize_for_speech(said, self.speech, lang)
            out.append(Utterance(sentence, spoken, self.pauses["sentence_ms"]))
        _extend_pause(out, end_ms)
        return range(start, len(out))

    def _note(self, out: list[Utterance], note: Footnote, lang: str | None) -> None:
        self.read_notes.add(note.note_id)
        part = self._sentences(
            out, f"{self.words['note']}: {note.text}", lang, self.pauses["paragraph_ms"]
        )
        self._passages.append(Passage(note, (part,)))

    def _image(self, out: list[Utterance], image: Image, lang: str | None) -> None:
        label = self.words["image"]
        start = len(out)
        description = caption = range(start, start)
        if image.alt:
            description = self._sentences(out, _sentence(f"{label}: {image.alt}"), lang, 0)
        elif image.caption or (image.alt is None and self.settings["announce_undescribed_images"]):
            description = self._sentences(out, f"{label}.", lang, 0)
        if image.caption:
            caption = self._sentences(out, _sentence(image.caption), lang, 0)
        else:
            caption = range(len(out), len(out))
        _extend_pause(out, self.pauses["paragraph_ms"])
        if len(out) > start:
            self._passages.append(Passage(image, (description, caption)))

    def _table(self, out: list[Utterance], table: Table, lang: str | None) -> None:
        label = self.words["table"]
        intro = f"{label}: {table.caption}" if table.caption else f"{label}."
        start = len(out)
        self._sentences(out, _sentence(intro), lang, self.pauses["sentence_ms"])
        if self.settings["tables"] == "skip":
            self._sentences(out, self.words["table_skipped"], lang, self.pauses["paragraph_ms"])
            self._passages.append(Passage(table, (range(start, len(out)),)))
            return
        parts = [range(start, len(out))]
        headers = table.rows[0] if table.header_rows else ()
        for n, row in enumerate(table.rows[table.header_rows :], start=1):
            parts.append(
                self._sentences(out, _row_text(self.words["row"], n, headers, row), lang, 0)
            )
            _extend_pause(out, self.pauses["list_item_ms"])
        _extend_pause(out, self.pauses["paragraph_ms"])
        self._passages.append(Passage(table, tuple(parts)))


def block_lang(block, section_lang: str | None) -> str | None:
    return getattr(block, "lang", None) or section_lang


def _heading_first(blocks: list[Block]) -> list[Block]:
    """Blocks in reading order, except that page markers before a section's opening heading
    come right after it: a talking book's sections start with their heading."""
    leading = 0
    while leading < len(blocks) and isinstance(blocks[leading], PageMarker):
        leading += 1
    if 0 < leading < len(blocks) and isinstance(blocks[leading], Heading):
        return [blocks[leading], *blocks[:leading], *blocks[leading + 1 :]]
    return blocks


def _first_heading_level(section: Section) -> int | None:
    """The level of the heading a section opens with, or None if it opens with something else."""
    for block in section.blocks:
        if not isinstance(block, PageMarker):
            return block.level if isinstance(block, Heading) else None
    return None


def _title_level(book: Book) -> int:
    """The heading level for a section title Dogear adds: the level most sections open with."""
    levels = Counter(_first_heading_level(s) for s in book.sections)
    levels.pop(None, None)
    return levels.most_common(1)[0][0] if levels else 1


def _join(names: list[str], and_word: str) -> str:
    """'A', 'A and B', or 'A, B and C'."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} {and_word} {names[-1]}"


def _row_text(row_word: str, n: int, headers: tuple[str, ...], row: tuple[str, ...]) -> str:
    cells = []
    for i, cell in enumerate(row):
        if not cell.strip():
            continue
        header = headers[i].strip() if i < len(headers) else ""
        cells.append(f"{header}: {cell}" if header and header != cell else cell)
    return _sentence(f"{row_word} {n}: " + "; ".join(cells))


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith(_ENDS_CLAUSE) else text + "."


def _extend_pause(out: list[Utterance], ms: int) -> None:
    """Make the silence after the last utterance at least `ms` long."""
    if out and ms > out[-1].pause_ms:
        out[-1] = replace(out[-1], pause_ms=ms)
