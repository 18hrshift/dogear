"""Units after a number: "5 km" is "five kilometers", "1 km" is "one kilometer", "50%" is
"fifty percent". English only; the unit table comes from config.
"""

from __future__ import annotations

import re
from functools import cache

from dogear.speech.spoken import (
    AMOUNT,
    ENGLISH,
    Pair,
    any_of,
    keep_final_period,
    say_amount,
    unit_word,
)


@cache
def _pattern(units: tuple[str, ...]) -> re.Pattern[str]:
    # An amount, at most one space, then a unit that doesn't run on into a word ("5 gals"
    # stays). Like the number pass, the lookbehind keeps "v1.5" and other codes as they are.
    return re.compile(rf"(?<![\w.,])(?P<amount>{AMOUNT})\s?(?P<unit>{any_of(units)})(?!\w)")


def say_units(text: str, units: dict[str, Pair]) -> str:
    """Spell out a number and the unit written after it."""
    if not any(units):
        return text
    return _pattern(tuple(units)).sub(lambda m: _say(m, units), text)


def _say(match: re.Match[str], units: dict[str, Pair]) -> str:
    amount = match["amount"]
    words = f"{say_amount(amount, ENGLISH)} {unit_word(units[match['unit']], amount)}"
    # "He weighed 200 lbs." keeps the period that ends the sentence.
    return keep_final_period(match, words)
