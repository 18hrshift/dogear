"""The forms that give words their spellings: a book's words page and the Pronunciations
page. Each word on them is two fields, numbered from 1: `word-N`, the word (hidden), and
`say-N`, how to say it ("Say it like"). An empty `say-N` removes the word's entry.

Everything sent is checked here (page_words.py has the rules); the pages show what was
sent back, with an error on each field that can't be saved.
"""

from __future__ import annotations

from dataclasses import dataclass

from dogear.pronunciations import word_key
from dogear.web.page_words import EntryError, clean_spelling, clean_word
from dogear.web.settings import WordLimits

MAX_NUMBER_DIGITS = 5


@dataclass(frozen=True)
class SentWord:
    number: int
    word: str  # as sent
    typed: str  # what was in "Say it like"

    @property
    def field(self) -> str:
        return say_field(self.number)


def say_field(number: int) -> str:
    """The name, and the id, of a word's "Say it like" field."""
    return f"say-{number}"


def sent_words(fields: list[tuple[str, str]], most: int) -> list[SentWord]:
    """The words sent, numbered 1 to `most`, in order. Other fields are ignored."""
    words: dict[int, str] = {}
    typed: dict[int, str] = {}
    for key, value in fields:
        kind, _, number_text = key.partition("-")
        number = _number(number_text)
        if number is None or not 1 <= number <= most:
            continue
        if kind == "word":
            words.setdefault(number, value)
        elif kind == "say":
            typed.setdefault(number, value)
    return [SentWord(n, words[n], typed.get(n, "")) for n in sorted(words)]


def spellings_to_save(
    sent: list[SentWord], limits: WordLimits
) -> tuple[dict[str, str], dict[str, str]]:
    """The spellings to save (word: spelling, "" to remove), and an error for each field
    that can't be saved, keyed by the field's name."""
    spellings: dict[str, str] = {}
    errors: dict[str, str] = {}
    for item in sent:
        try:
            word = clean_word(item.word, limits)
        except EntryError as e:
            if item.typed.strip():
                errors[item.field] = f"{item.word.strip()} can't be saved: {e.message}"
            continue  # a word that can't be saved has no entry to remove
        try:
            spellings[word] = clean_spelling(item.typed, word, limits)
        except EntryError as e:
            errors[item.field] = e.message
    return spellings, errors


def field_for(sent: list[SentWord], word: str) -> str:
    """The "Say it like" field of `word`, or of the first word if it isn't one sent."""
    for item in sent:
        if word_key(" ".join(item.word.split())) == word_key(word):
            return item.field
    return sent[0].field if sent else ""


def _number(text: str) -> int | None:
    if text.isascii() and text.isdecimal() and len(text) <= MAX_NUMBER_DIGITS:
        return int(text)
    return None
