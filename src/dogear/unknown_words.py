"""`dogear words`: the words in a book the voice doesn't know, most frequent first.

These are the words misaki's dictionaries don't have, which the voice hands to the
espeak-ng program to guess. Names and made-up words are the usual ones: worth a listen
with `dogear say`, and an entry in a pronunciation file if they come out wrong. Words
the user's files already cover aren't listed. This needs spaCy's English model (about
13 MB) but not the Kokoro voice.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.extract import extract_book
from dogear.make import _chosen, check_language
from dogear.narration import narrate_book
from dogear.pronunciations import dictionary_from_config
from dogear.render.progress import Report
from dogear.voice import find_voice, prepare_spacy

_EDGES = re.compile(r"^\W+|\W+$")  # quotes, brackets, and punctuation around a word
_POSSESSIVE = re.compile(r"(?<=\w)['’]s$", re.IGNORECASE)


@dataclass(frozen=True)
class WordsRequest:
    book: Path
    sections: set[int] | None = None  # numbers from `dogear outline`; None means all
    language: str | None = None  # overrides the language the book declares


@dataclass(frozen=True)
class UnknownWord:
    word: str  # the spelling the book uses most
    count: int


def find_unknown_words(request: WordsRequest, config: Config, report: Report) -> list[UnknownWord]:
    """The book's unknown words, most frequent first, as the configured voice would meet them."""
    book = extract_book(request.book, config)
    if request.language:
        book.metadata.language = request.language
    check_language(book)
    narrations = _chosen(narrate_book(book, config), request.sections, len(book.sections))
    british = find_voice(config["voice"]["voice"]).british
    dictionary = dictionary_from_config(config)
    spacy_model = prepare_spacy(config, report)

    from dogear.voice.g2p import count_unknown_words  # loads misaki and spaCy: slow

    spoken = [u.spoken for n in narrations for u in n.utterances if u.spoken]
    return rank_words(count_unknown_words(spoken, spacy_model, british, dictionary))


def rank_words(counts: Counter[str]) -> list[UnknownWord]:
    """One entry per word, as a pronunciation file would list it: whatever its capitals,
    without punctuation around it, and with "Utterson's" counted as "Utterson". Most
    frequent first; ties in alphabetical order. Lone punctuation isn't a word to list."""
    totals: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    for word, count in counts.items():
        base = _POSSESSIVE.sub("", _EDGES.sub("", word))
        if not base:
            continue
        key = base.casefold()
        totals[key] += count
        spellings.setdefault(key, Counter())[base] += count
    ranked = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
    return [UnknownWord(spellings[key].most_common(1)[0][0], count) for key, count in ranked]
