"""Rewrite one sentence of display text into what a voice engine should say.

Engines differ in how they read "Dr.", "3.14", or "1984", so Dogear spells these out
itself and every engine gets the same words. Abbreviation tables come from config and
are English for now; numbers use num2words in the book's language when it supports it.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from num2words import num2words

from dogear.config import Config

log = logging.getLogger(__name__)

_PUNCTUATION = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
}
_EN_DASH_RANGE = re.compile(r"(?<=\d)\s*–\s*(?=\d)")  # 1990–1995 -> 1990 to 1995
_DASHES = re.compile(r"\s*[–—]\s*")
_MARKUP = re.compile(r"[#*_`~]")
_SPACES = re.compile(r"[ \t]{2,}")

# One pass over every number, most specific form first. The lookbehind keeps numbers
# inside words or version strings ("v1.2", "MP3") as they are.
_NUMBER = re.compile(
    r"""(?<![\w.,])(?:
        (?P<grouped>\d{1,3}(?:,\d{3})+)(?![\d])
      | (?P<decimal>\d+\.\d+)(?![\d])
      | (?P<ordinal>\d+)(?P<suffix>(?i:st|nd|rd|th))\b
      | (?P<int>\d+)(?![\d])
    )""",
    re.VERBOSE,
)
_YEAR_RANGE = range(1100, 2100)  # four-digit numbers read the way people say years
_LONGEST_CARDINAL = 999_999  # longer ungrouped numbers are usually codes: read digit by digit

_warned_languages: set[str] = set()


@dataclass(frozen=True)
class SpeechRules:
    abbreviations: dict[str, str]
    before_name: dict[str, str]
    before_number: dict[str, str]

    @classmethod
    def from_config(cls, config: Config) -> SpeechRules:
        speech = config["speech"]
        return cls(
            abbreviations=dict(speech["abbreviations"]),
            before_name=dict(speech["abbreviations_before_name"]),
            before_number=dict(speech["abbreviations_before_number"]),
        )

    def patterns(self) -> list[tuple[re.Pattern[str], str]]:
        def build(table: dict[str, str], context: str) -> list[tuple[re.Pattern[str], str]]:
            # Longest first, so "pp." wins over "p.". The lookbehind stops "p." matching
            # inside "pp." or a longer word.
            keys = sorted(table, key=len, reverse=True)
            return [(re.compile(rf"(?<![\w.]){re.escape(k)}{context}"), table[k]) for k in keys]

        return (
            build(self.before_name, r"(?=\s+[A-Z])")
            + build(self.before_number, r"(?=\s*\d)")
            + build(self.abbreviations, "")
        )


def normalize_for_speech(text: str, rules: SpeechRules, lang: str | None) -> str:
    text = _normalize_punctuation(text)
    for pattern, expansion in rules.patterns():
        text = pattern.sub(lambda m, e=expansion: _expand(m, e), text)
    text = _NUMBER.sub(lambda m: _speak_number(m, _num2words_lang(lang)), text)
    text = _MARKUP.sub("", text)
    return _SPACES.sub(" ", text).strip()


def _expand(match: re.Match[str], expansion: str) -> str:
    # "fruits, etc." ends the sentence: keep its period so the voice still stops.
    rest = match.string[match.end() :].strip("\"') ]")
    return f"{expansion}." if match.group(0).endswith(".") and not rest else expansion


def _normalize_punctuation(text: str) -> str:
    # Invisible formatting characters (word joiners, zero-width spaces, soft hyphens) help
    # page layout but can trip a voice engine.
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    for char, replacement in _PUNCTUATION.items():
        text = text.replace(char, replacement)
    text = _EN_DASH_RANGE.sub(" to ", text)
    return _DASHES.sub(", ", text)  # a dash is a pause; a comma is the safest pause cue


def _num2words_lang(lang: str | None) -> str:
    return (lang or "en").split("-")[0].lower()


def _speak_number(match: re.Match[str], lang: str) -> str:
    original = match.group(0)
    try:
        if grouped := match.group("grouped"):
            return num2words(int(grouped.replace(",", "")), lang=lang)
        if decimal := match.group("decimal"):
            whole, fraction = decimal.split(".")
            digits = " ".join(num2words(int(d), lang=lang) for d in fraction)
            return f"{num2words(int(whole), lang=lang)} point {digits}"
        if ordinal := match.group("ordinal"):
            return num2words(int(ordinal), lang=lang, to="ordinal")
        return _speak_integer(match.group("int"), lang)
    except NotImplementedError:
        if lang not in _warned_languages:
            _warned_languages.add(lang)
            log.warning("Numbers can't be spelled out in language '%s'; leaving digits.", lang)
        return original


def _speak_integer(digits: str, lang: str) -> str:
    value = int(digits)
    if (digits.startswith("0") and len(digits) > 1) or value > _LONGEST_CARDINAL:
        return " ".join(num2words(int(d), lang=lang) for d in digits)
    if len(digits) == 4 and value in _YEAR_RANGE:
        try:
            return num2words(value, lang=lang, to="year")
        except NotImplementedError:
            pass
    return num2words(value, lang=lang)
