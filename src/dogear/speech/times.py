"""Clock times: "3:30 pm" is "three thirty p.m.", "3:05" is "three oh five", "10:00" is
"ten o'clock". English only; the am and pm table comes from config.
"""

from __future__ import annotations

import re
from functools import cache

from num2words import num2words

from dogear.speech.spoken import ENGLISH, any_of, keep_final_period

# Hours and minutes, not followed by seconds ("12:30:45" stays as it is).
_CLOCK = r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?!:?\d)"
# An hour on its own counts as a time only when a suffix follows: "10 a.m.", "10am".
_HOUR = r"(?P<bare_hour>1[0-2]|0?[1-9])"


@cache
def _pattern(suffixes: tuple[str, ...]) -> re.Pattern[str]:
    # The lookbehind keeps times out of codes and decimals ("v3:30", "1.3:30").
    start = r"(?<![\w.,:])"
    if not any(suffixes):
        return re.compile(rf"{start}{_CLOCK}")
    suffix = rf"(?i:{any_of(suffixes)})(?!\w)"
    return re.compile(rf"{start}(?:{_CLOCK}|{_HOUR}(?=\s?{suffix}))(?:\s?(?P<suffix>{suffix}))?")


def say_times(text: str, suffixes: dict[str, str]) -> str:
    """Spell out clock times, and hours followed by am or pm."""
    spoken = {k.lower(): v for k, v in suffixes.items()}
    return _pattern(tuple(suffixes)).sub(lambda m: _say(m, spoken), text)


def _say(match: re.Match[str], suffixes: dict[str, str]) -> str:
    found = match.groupdict()  # no suffix groups when the suffix table is empty
    suffix = found.get("suffix")
    words = _clock(found["hour"] or found.get("bare_hour"), found["minute"], bool(suffix))
    if suffix:
        words = f"{words} {suffixes[suffix.lower()]}"
    return keep_final_period(match, words)


def _clock(hour: str, minute: str | None, has_suffix: bool) -> str:
    said = num2words(int(hour), lang=ENGLISH)
    if minute is None or (minute == "00" and has_suffix):
        return said  # "10 a.m.", "10:00 a.m."
    if minute == "00":
        # "10:00" is "ten o'clock"; a 24-hour "14:00" is "fourteen hundred".
        return f"{said} o'clock" if 1 <= int(hour) <= 12 else f"{said} hundred"
    if minute.startswith("0"):
        return f"{said} oh {num2words(int(minute), lang=ENGLISH)}"  # "3:05"
    return f"{said} {num2words(int(minute), lang=ENGLISH)}"
