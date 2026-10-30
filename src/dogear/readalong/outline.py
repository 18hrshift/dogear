"""Book-wide heading levels and print page kinds, for moving around a talking book.

Players move by heading level ("next level 2 heading"), and DAISY 2.02 forbids skipping
a level. Books use levels loosely: chapters are often level 2 with no level 1 anywhere,
or a section jumps from level 1 to level 3. So the levels a book uses become 1, 2, 3 in
order, and any jump of more than one level deeper is pulled up to one.
"""

from __future__ import annotations

import re

from dogear.readalong.model import PageKind

_ARABIC = re.compile(r"[0-9]+")
# A well-formed roman numeral ("xiv", not "iiii" or "ic"), as DAISY's schema checks them.
_ROMAN = re.compile(r"(?=.)M*(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", re.IGNORECASE)


def heading_levels(levels: list[int]) -> list[int]:
    """Levels from 1 to 6 for headings in reading order, none deeper than the last plus one."""
    ranks = {level: rank for rank, level in enumerate(sorted(set(levels)), start=1)}
    result, previous = [], 0
    for level in levels:
        previous = min(ranks[level], previous + 1)
        result.append(previous)
    return result


def page_kind(label: str) -> PageKind:
    """DAISY's kinds of page number: front (roman numerals), normal (arabic), or special.

    Anything else, including a malformed roman numeral, is special.
    """
    if _ARABIC.fullmatch(label):
        return "normal"
    if _ROMAN.fullmatch(label):
        return "front"
    return "special"
