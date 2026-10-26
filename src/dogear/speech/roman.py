"""Roman numerals that number something, rewritten as digits for the number pass to say:
"Chapter IV" becomes "Chapter 4", and a heading that is only "IV." becomes "4.".

Everything else stays as written: the pronoun "I", words spelled with numeral letters
("MIX", "DID", "CIVIL"), and regnal names ("World War II", "Henry VIII"). English only;
the keywords come from config.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache

from dogear.speech.spoken import any_of

# A candidate numeral: capitals, or lower case i, v, and x ("Scene ii"). D and M are left
# out: words like "DC", "MD", and "MIX" are far likelier than a chapter past 399. The
# lookahead keeps "I'm" and "Iowa" whole.
_NUMERAL = r"(?P<numeral>[IVXLC]+|[ivx]+)(?![\w'])"
# Well-formed numerals only, so "IIII" and "VX" are not read as numbers.
_UPPER = re.compile(r"C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_LOWER = re.compile(r"x{0,3}(?:ix|iv|v?i{0,3})")
# Letters that count as a numeral on their own. "L" and "C" alone are usually labels
# ("Appendix C").
_SINGLE = frozenset("IVXivx")
_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
# A lone "I" followed by a word is the pronoun: "the Part I played".
_WORD_NEXT = re.compile(r"\s+[A-Za-z]")
# A heading numbered by a leading numeral: "IV", "IV.", or "IV. The Return". A period and
# then another single letter is a name's initials ("I. M. Pei"), not a number.
_HEADING_NUMERAL = re.compile(rf"^{_NUMERAL}(?=[.:]?$|[.:]\s+(?![A-Za-z]\.))")


def roman_value(token: str) -> int | None:
    """The value of a numeral Dogear reads aloud, or None if `token` isn't one."""
    if len(token) == 1 and token not in _SINGLE:
        return None
    if not (_UPPER.fullmatch(token) or _LOWER.fullmatch(token)):
        return None
    values = [_VALUES[c] for c in token.upper()]
    return sum(-v if v < after else v for v, after in zip(values, [*values[1:], 0], strict=True))


def keyword_numerals(text: str, keywords: Sequence[str]) -> str:
    """A numeral right after a keyword becomes digits: "in Chapter IV we saw"."""
    if not any(keywords):
        return text

    def swap(match: re.Match[str]) -> str:
        if match["numeral"] in ("I", "i") and _WORD_NEXT.match(match.string, match.end()):
            return match.group(0)
        return _with_digits(match)

    return _after_keyword(tuple(keywords)).sub(swap, text)


def heading_numerals(text: str, keywords: Sequence[str]) -> str:
    """The numeral that numbers a heading becomes digits: "IV.", "IV. The Return", or
    "CHAPTER I THE BEGINNING". At the start of a heading a lone "I" is always a number.
    """
    text = text.strip()
    match = _after_keyword(tuple(keywords)).match(text) if any(keywords) else None
    if match is None:
        match = _HEADING_NUMERAL.match(text)
    if match is None:
        return text
    return _with_digits(match) + text[match.end() :]


@cache
def _after_keyword(keywords: tuple[str, ...]) -> re.Pattern[str]:
    # Each keyword as written in config and in capitals: "Chapter IV", "CHAPTER IV".
    words = any_of({form for k in keywords for form in (k, k.upper())})
    return re.compile(rf"(?<!\w)(?:{words})\s+{_NUMERAL}")


def _with_digits(match: re.Match[str]) -> str:
    """The matched text with its numeral as digits, or unchanged if it isn't one."""
    value = roman_value(match["numeral"])
    if value is None:
        return match.group(0)
    return match.group(0)[: match.start("numeral") - match.start()] + str(value)
