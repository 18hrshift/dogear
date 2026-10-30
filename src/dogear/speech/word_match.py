"""Finding a list of words in text: whole words, in any case, the longest first.

Used for the user's pronunciation dictionary. "Utterson" matches "Utterson", "UTTERSON",
and the possessives "Utterson's" and "Utterson’s", but not "Uttersons" or "Lutterson";
"Brien" doesn't match inside "O'Brien". A word written with spaces ("St. John") matches
across any run of spaces or a line break. Where words overlap, the longest wins:
"St. John" before "John". Straight and curly apostrophes count as the same character.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

_APOSTROPHES = "'’"
_POSSESSIVE = re.compile(r"['’]s(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class WordMatch:
    index: int  # which word matched, as its position in the matcher's list
    start: int
    end: int  # after the possessive, when there is one
    possessive: str  # "'s" or "’s" as the text has it, or ""


class WordMatcher:
    def __init__(self, words: Sequence[str]) -> None:
        longest_first = sorted(range(len(words)), key=lambda i: len(words[i]), reverse=True)
        alternatives = "|".join(f"(?P<w{i}>{_pattern(words[i])})" for i in longest_first)
        # Not right after a letter or digit, or after one and an apostrophe ("O'Brien"),
        # and not right before one.
        self._regex = (
            re.compile(rf"(?<!\w)(?<!\w['’])(?:{alternatives})(?!\w)", re.IGNORECASE)
            if words
            else None
        )

    def finditer(self, text: str) -> Iterator[WordMatch]:
        if self._regex is None:
            return
        for match in self._regex.finditer(text):
            possessive = _POSSESSIVE.match(text, match.end())
            yield WordMatch(
                index=int(match.lastgroup[1:]),
                start=match.start(),
                end=possessive.end() if possessive else match.end(),
                possessive=possessive.group(0) if possessive else "",
            )

    def sub(self, text: str, replace: Callable[[WordMatch], str]) -> str:
        """`text` with each match swapped for what `replace` returns for it."""
        pieces, last = [], 0
        for match in self.finditer(text):
            pieces += [text[last : match.start], replace(match)]
            last = match.end
        return "".join(pieces) + text[last:]


def _pattern(word: str) -> str:
    """The word as a regular expression: any whitespace between its parts, either apostrophe."""
    parts = word.split()
    return r"\s+".join(
        "".join(f"[{_APOSTROPHES}]" if c in _APOSTROPHES else re.escape(c) for c in part)
        for part in parts
    )
