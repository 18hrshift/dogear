"""Pieces the speech normalization passes share: amounts read aloud, singular or plural
unit words, word-table regexes, and keeping a sentence's final period.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from num2words import num2words

Pair = tuple[str, str]  # (singular, plural), such as ("mile", "miles")

ENGLISH = "en"  # the language of the currency, time, unit, and roman numeral rules

# An amount as written in a book: "5", "1.5", "1,000", or "1,000.25".
AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

_CLOSERS = "\"') ]"  # may follow a sentence's last word


def any_of(keys: Iterable[str]) -> str:
    """A regex alternation of `keys`, longest first so "km/h" wins over "km".

    Empty keys are dropped: they would match everywhere.
    """
    return "|".join(re.escape(k) for k in sorted(filter(None, keys), key=len, reverse=True))


def say_amount(amount: str, lang: str) -> str:
    """Read an amount as a quantity: "1,000" is "one thousand", "1.5" is "one point five".

    Always a cardinal, never a year or a code, and digits after the point one by one.
    """
    whole, _, fraction = amount.partition(".")
    words = num2words(int(whole.replace(",", "")), lang=lang)
    if fraction:
        words += " point " + " ".join(num2words(int(d), lang=lang) for d in fraction)
    return words


def unit_word(pair: Pair, amount: str) -> str:
    """Singular only for exactly one: "1 km", but "1.5 km" and "0 km" are plural."""
    return pair[0] if amount.lstrip("0") == "1" else pair[1]


def keep_final_period(match: re.Match[str], words: str) -> str:
    """`words` to put in place of `match`, with one period where the sentence ends.

    "fruits, etc." ends its sentence, so "etcetera" keeps the period. "3 pm." must not
    become "three p.m.." when the spoken suffix brings its own period.
    """
    after = match.string[match.end() :]
    if words.endswith(".") and after.startswith("."):
        return words[:-1]
    ends_sentence = not after.strip(_CLOSERS)
    if match.group(0).endswith(".") and ends_sentence and not words.endswith("."):
        return f"{words}."
    return words
