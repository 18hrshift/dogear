"""Decide whether a hyphen at the end of a PDF line belongs to the word.

A typesetter breaks a long word across lines with a hyphen ("exam-" + "ple"), and a
compound that is always hyphenated can break at its own hyphen ("well-" + "known"). At a
line end the two look the same. The book itself is the best evidence: a book that prints
"well-known" in the middle of a line elsewhere keeps the hyphen, and one that prints
"example" drops it.

With no evidence either way, the default is to join ("hyphen_without_evidence" in the
[pdf] config table). Most line-end hyphens are the typesetter's, and for speech a wrongly
joined compound ("wellknown") still sounds close, while a wrongly kept break
("exam-ple") is read as two words.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

# A word, with any hyphens inside it: "rabbit-hole", "out-of-the-way".
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")


@dataclass(frozen=True)
class HyphenEvidence:
    """How often each word and hyphenated compound appears in a book, ignoring case."""

    counts: Counter[str]
    min_count: int  # how often a spelling must appear to count as evidence
    keep_by_default: bool  # what to do without evidence

    @classmethod
    def from_texts(
        cls, texts: Iterable[str], *, min_count: int, keep_by_default: bool
    ) -> HyphenEvidence:
        """Count the words in `texts`, such as every line of a book.

        A word broken at a line end is counted as two fragments ("exam", "ple"), never as
        either spelling, so the break being decided is not evidence for itself.
        """
        counts = Counter(word.casefold() for text in texts for word in _WORD.findall(text))
        return cls(counts, min_count, keep_by_default)

    def keep(self, left: str, right: str) -> bool:
        """Whether "left-" at a line end and "right" at the next line's start make
        "left-right" (True) or "leftright" (False)."""
        hyphenated = self.counts[f"{left}-{right}".casefold()]
        joined = self.counts[f"{left}{right}".casefold()]
        if hyphenated == joined or max(hyphenated, joined) < self.min_count:
            return self.keep_by_default
        return hyphenated > joined
