"""Spoken structure: what a section sounds like, as a list of utterances.

Structure a sighted reader sees (headings, paragraphs, images, notes, scene breaks) is
turned into words and pauses a listener can hear. Longer pauses mark bigger breaks: a
sentence, a paragraph, a heading, a scene, a chapter. Every choice here comes from the
[narration] settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from dogear.config import Config
from dogear.document import (
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
from dogear.speech.normalize import SpeechRules, normalize_for_speech
from dogear.speech.sentences import SentenceRules, split_sentences

log = logging.getLogger(__name__)

_ENDS_CLAUSE = (".", "!", "?", ":", ";", ",", "…")


@dataclass(frozen=True)
class Utterance:
    text: str  # display text, for read-along output; "" for a pure pause
    spoken: str  # what the voice says; "" for a pure pause
    pause_ms: int  # silence after it


@dataclass(frozen=True)
class SectionNarration:
    number: int  # 1-based, as `dogear outline` shows it
    section: Section
    utterances: list[Utterance]

    def words(self) -> int:
        return sum(len(u.spoken.split()) for u in self.utterances)


def narrate_book(book: Book, config: Config) -> list[SectionNarration]:
    """Every section's narration, leaving out sections that end up with nothing to say."""
    narrator = _Narrator(book, config)
    narrations = []
    for number, section in enumerate(book.sections, start=1):
        utterances = narrator.section(section)
        if narrator.has_content(utterances, section):
            narrations.append(SectionNarration(number, section, utterances))
        else:
            log.info(
                "Section %d, %s, was left out of the audio: its notes are read where the "
                "text refers to them.",
                number,
                section.title,
            )
    return narrations


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

    def has_content(self, utterances: list[Utterance], section: Section) -> bool:
        """False for a section whose only content was notes already read elsewhere."""
        spoken_blocks = [b for b in section.blocks if not isinstance(b, PageMarker | SceneBreak)]
        all_notes_read = all(
            isinstance(b, Heading) or (isinstance(b, Footnote) and b.note_id in self.read_notes)
            for b in spoken_blocks
        )
        has_notes = any(isinstance(b, Footnote) for b in spoken_blocks)
        return not (has_notes and all_notes_read) and any(u.spoken for u in utterances)

    def section(self, section: Section) -> list[Utterance]:
        out = [Utterance("", "", self.pauses["section_start_ms"])]
        lang = section.lang or self.language
        if not _starts_with_heading(section):
            self._heading(out, section.title, lang)
        end_notes: list[Footnote] = []
        for block in section.blocks:
            self._block(out, block, block_lang(block, lang), end_notes)
        if end_notes:
            self._heading(out, self.words["notes"], lang)
            for note in end_notes:
                self._note(out, note, block_lang(note, lang))
        _extend_pause(out, self.pauses["section_end_ms"])
        return out

    def _block(self, out: list[Utterance], block, lang: str | None, end_notes: list) -> None:
        match block:
            case Heading(text=text):
                self._heading(out, text, lang)
            case Paragraph(text=text, note_refs=refs):
                self._sentences(out, text, lang, self.pauses["paragraph_ms"])
                if self.settings["footnotes"] == "after_paragraph":
                    for note_id in refs:
                        if note_id in self.notes and note_id not in self.read_notes:
                            note = self.notes[note_id]
                            self._note(out, note, block_lang(note, lang))
            case ListBlock(items=items, ordered=ordered):
                for n, item in enumerate(items, start=1):
                    self._sentences(out, f"{n}. {item}" if ordered else item, lang, 0)
                    _extend_pause(out, self.pauses["list_item_ms"])
                _extend_pause(out, self.pauses["paragraph_ms"])
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
                if self.settings["announce_pages"]:
                    self._sentences(out, f"{self.words['page']} {label}.", lang, 0)
                    _extend_pause(out, self.pauses["sentence_ms"])
            case SceneBreak():
                _extend_pause(out, self.pauses["scene_break_ms"])
            case _:
                raise TypeError(f"not a block: {block!r}")

    def _heading(self, out: list[Utterance], text: str, lang: str | None) -> None:
        if out[-1].spoken:
            _extend_pause(out, self.pauses["paragraph_ms"])  # a breath before it, too
        spoken = normalize_for_speech(text, self.speech, lang)
        if not spoken.endswith(_ENDS_CLAUSE):
            spoken += "."  # so the voice closes the heading instead of trailing off
        out.append(Utterance(text, spoken, self.pauses["heading_ms"]))

    def _sentences(self, out: list[Utterance], text: str, lang: str | None, end_ms: int) -> None:
        for sentence in split_sentences(text, self.sentences):
            spoken = normalize_for_speech(sentence, self.speech, lang)
            out.append(Utterance(sentence, spoken, self.pauses["sentence_ms"]))
        _extend_pause(out, end_ms)

    def _note(self, out: list[Utterance], note: Footnote, lang: str | None) -> None:
        self.read_notes.add(note.note_id)
        self._sentences(
            out, f"{self.words['note']}: {note.text}", lang, self.pauses["paragraph_ms"]
        )

    def _image(self, out: list[Utterance], image: Image, lang: str | None) -> None:
        label = self.words["image"]
        if image.alt:
            self._sentences(out, _sentence(f"{label}: {image.alt}"), lang, 0)
        elif image.caption or (image.alt is None and self.settings["announce_undescribed_images"]):
            self._sentences(out, f"{label}.", lang, 0)
        if image.caption:
            self._sentences(out, _sentence(image.caption), lang, 0)
        _extend_pause(out, self.pauses["paragraph_ms"])

    def _table(self, out: list[Utterance], table: Table, lang: str | None) -> None:
        label = self.words["table"]
        intro = f"{label}: {table.caption}" if table.caption else f"{label}."
        self._sentences(out, _sentence(intro), lang, self.pauses["sentence_ms"])
        if self.settings["tables"] == "skip":
            self._sentences(out, self.words["table_skipped"], lang, self.pauses["paragraph_ms"])
            return
        headers = table.rows[0] if table.header_rows else ()
        for n, row in enumerate(table.rows[table.header_rows :], start=1):
            self._sentences(out, _row_text(self.words["row"], n, headers, row), lang, 0)
            _extend_pause(out, self.pauses["list_item_ms"])
        _extend_pause(out, self.pauses["paragraph_ms"])


def block_lang(block, section_lang: str | None) -> str | None:
    return getattr(block, "lang", None) or section_lang


def _starts_with_heading(section: Section) -> bool:
    for block in section.blocks:
        if not isinstance(block, PageMarker):
            return isinstance(block, Heading)
    return False


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
