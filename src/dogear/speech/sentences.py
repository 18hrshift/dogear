"""Split display text into sentences: the unit Dogear renders, caches, and times.

Splitting happens on display text, before any speech normalization, so each sentence
can be highlighted as-is in read-along output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dogear.config import Config

# Sentence-ending punctuation, optional closing quotes or brackets, whitespace, then
# something that can start a sentence.
_BOUNDARY = re.compile(r"""[.!?]["'”’)\]]*\s+(?=["'“‘(\[]?[A-Z0-9])""")
_INITIAL = re.compile(r"(?:^|\s)[A-Z]\.$")
_CLAUSE = re.compile(r"(?<=[,;:])\s+")


@dataclass(frozen=True)
class SentenceRules:
    no_break_after: frozenset[str]  # a period after these never ends a sentence
    no_break_before_number: frozenset[str]  # ...unless a number follows: "No. 5"
    max_chars: int

    @classmethod
    def from_config(cls, config: Config) -> SentenceRules:
        speech = config["speech"]
        return cls(
            no_break_after=frozenset(speech["no_sentence_break_after"])
            | frozenset(speech["abbreviations_before_name"]),
            no_break_before_number=frozenset(speech["abbreviations_before_number"]),
            max_chars=speech["max_sentence_chars"],
        )


def split_sentences(text: str, rules: SentenceRules) -> list[str]:
    """Sentences in reading order, none longer than `rules.max_chars`."""
    sentences = []
    for sentence in _split_at_boundaries(text.strip(), rules):
        sentences.extend(_limit_length(sentence, rules.max_chars))
    return sentences


def _split_at_boundaries(text: str, rules: SentenceRules) -> list[str]:
    pieces, start = [], 0
    for match in _BOUNDARY.finditer(text):
        before = text[start : match.start() + 1]
        if _is_false_boundary(before, text[match.end() :], rules):
            continue
        cut = match.end()
        pieces.append(text[start:cut].strip())
        start = cut
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


def _is_false_boundary(before: str, after: str, rules: SentenceRules) -> bool:
    if not before.endswith("."):
        return False
    words = before.split()
    last_word = words[-1].lstrip("\"'“‘([") if words else ""
    if last_word in rules.no_break_after or _INITIAL.search(before):
        return True
    return last_word in rules.no_break_before_number and after[:1].isdigit()


def _limit_length(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts = []
    for clause in _pack(_CLAUSE.split(sentence), max_chars):
        parts.extend(_split_at_spaces(clause, max_chars))
    return parts


def _pack(pieces: list[str], max_chars: int) -> list[str]:
    """Greedily join pieces with spaces while they fit in `max_chars`."""
    packed: list[str] = []
    for piece in pieces:
        if packed and len(packed[-1]) + 1 + len(piece) <= max_chars:
            packed[-1] = f"{packed[-1]} {piece}"
        else:
            packed.append(piece)
    return packed


def _split_at_spaces(text: str, max_chars: int) -> list[str]:
    """Last resort: break at word boundaries. A single overlong word stays whole."""
    if len(text) <= max_chars:
        return [text]
    return _pack(text.split(), max_chars)
