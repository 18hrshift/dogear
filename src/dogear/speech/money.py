"""Money: "$5.99" is "five dollars and ninety-nine cents", "$1.5 million" is "one point
five million dollars". English only; the word tables come from config.
"""

from __future__ import annotations

import re
from functools import cache

from dogear.speech.spoken import ENGLISH, Pair, any_of, say_amount, unit_word

# The whole part of an amount: "5" or "1,000".
_WHOLE = r"\d{1,3}(?:,\d{3})+|\d+"


@cache
def _pattern(symbols: tuple[str, ...], scales: tuple[str, ...]) -> re.Pattern[str]:
    # A symbol, then an amount, then an optional scale word in any case ("$1.5 million",
    # "£5m"). The lookbehind leaves "US$5" alone unless "US$" is in the table itself.
    scale = rf"(?:\s?(?P<scale>(?i:{any_of(scales)}))(?!\w))?" if any(scales) else ""
    return re.compile(
        rf"(?<!\w)(?P<symbol>{any_of(symbols)})"
        rf"(?P<whole>{_WHOLE})(?:\.(?P<fraction>\d+))?(?!\d){scale}"
    )


def say_money(
    text: str, names: dict[str, Pair], cents: dict[str, Pair], scales: dict[str, str]
) -> str:
    """Spell out amounts written with a currency symbol in front."""
    if not any(names):
        return text
    lowered = {k.lower(): v for k, v in scales.items()}
    pattern = _pattern(tuple(names), tuple(scales))
    return pattern.sub(lambda m: _say(m, names, cents, lowered), text)


def _say(
    match: re.Match[str], names: dict[str, Pair], cents: dict[str, Pair], scales: dict[str, str]
) -> str:
    symbol, whole, fraction = match["symbol"], match["whole"], match["fraction"]
    amount = f"{whole}.{fraction}" if fraction else whole
    if written := match.groupdict().get("scale"):  # no scale group without a scale table
        scale = scales[written.lower()]
        return f"{say_amount(amount, ENGLISH)} {scale} {names[symbol][1]}"
    if fraction and len(fraction) == 2 and symbol in cents:
        return _with_cents(whole.replace(",", ""), fraction, names[symbol], cents[symbol])
    # No hundredths to name ("$5.5", or a currency without cents): read it as a decimal.
    return f"{say_amount(amount, ENGLISH)} {unit_word(names[symbol], amount)}"


def _with_cents(whole: str, fraction: str, name: Pair, cent: Pair) -> str:
    """ "5", "99" is "five dollars and ninety-nine cents"; "0", "50" is "fifty cents"."""
    parts = []
    if int(whole) or not int(fraction):
        parts.append(f"{say_amount(whole, ENGLISH)} {unit_word(name, whole)}")
    if int(fraction):
        parts.append(f"{say_amount(fraction, ENGLISH)} {unit_word(cent, fraction)}")
    return " and ".join(parts)
