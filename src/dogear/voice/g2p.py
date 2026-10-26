"""English pronunciation for Kokoro: text in, phonemes out.

misaki (Apache-2.0) is the phonemizer Kokoro was trained with. It looks words up in its
dictionaries and uses spaCy part-of-speech tags to choose between heteronyms such as
"read" (present) and "read" (past). Words it doesn't know, mostly names, go to the
espeak-ng program, as in Kokoro's own setup.

misaki's packaged English setup loads espeak-ng as a library through `phonemizer`, both
GPL. Dogear runs the espeak-ng program instead, the same way it runs ffmpeg, so no GPL
code is part of Dogear. misaki is pinned to 0.9.4 because `_MisakiG2P` relies on how
its G2P class sets itself up.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from misaki import en

from dogear.tools import run_tool

log = logging.getLogger(__name__)

# espeak-ng IPA to misaki's phoneme set, longest first. From misaki 0.9.4 espeak.py
# (Apache-2.0), which is what Kokoro's own fallback uses.
_ESPEAK_TO_MISAKI = sorted(
    {
        "ʔˌn̩": "ʔn",
        "ʔn̩": "ʔn",
        "a^ɪ": "I",
        "a^ʊ": "W",
        "d^ʒ": "ʤ",
        "e^ɪ": "A",
        "e": "A",
        "t^ʃ": "ʧ",
        "ɔ^ɪ": "Y",
        "ə^l": "ᵊl",
        "ʲo": "jo",
        "ʲə": "jə",
        "ʲ": "",
        "ɚ": "əɹ",
        "r": "ɹ",
        "x": "k",
        "ç": "k",
        "ɐ": "ə",
        "ɬ": "l",
        "̃": "",
    }.items(),
    key=lambda pair: -len(pair[0]),
)
_SYLLABIC = re.compile(r"(\S)̩")
_ESPEAK_TIMEOUT = 30  # seconds for one word; espeak-ng normally answers in milliseconds


class EspeakFallback:
    """Phonemes for words misaki doesn't know, from the espeak-ng program."""

    def __init__(self, program: str, british: bool) -> None:
        self.program = program
        self.british = british
        self._known: dict[str, str | None] = {}

    def __call__(self, token: en.MToken) -> tuple[str | None, int | None]:
        word = token.text
        if word not in self._known:
            self._known[word] = self._lookup(word)
        phonemes = self._known[word]
        return (phonemes, 1) if phonemes else (None, None)

    def _lookup(self, word: str) -> str | None:
        voice = "en-gb" if self.british else "en-us"
        result = run_tool(
            [self.program, "-q", "--ipa", "--tie=^", "-v", voice],
            input=word + "\n",
            timeout=_ESPEAK_TIMEOUT,
        )
        ipa = " ".join(result.stdout.split())
        return to_misaki(ipa, self.british) if ipa else None


def to_misaki(ipa: str, british: bool) -> str:
    """Rewrite espeak-ng IPA (with ^ ties) into misaki's phoneme set."""
    for old, new in _ESPEAK_TO_MISAKI:
        ipa = ipa.replace(old, new)
    ipa = _SYLLABIC.sub(r"ᵊ\1", ipa).replace("̩", "")
    if british:
        ipa = ipa.replace("e^ə", "ɛː").replace("iə", "ɪə").replace("ə^ʊ", "Q")
    else:
        ipa = ipa.replace("o^ʊ", "O").replace("ɜːɹ", "ɜɹ").replace("ɜː", "ɜɹ")
        ipa = ipa.replace("ɪə", "iə").replace("ː", "")
    ipa = ipa.replace("o", "ɔ")  # espeak-ng before 1.52 writes o for ɔ
    ipa = ipa.replace("ɾ", "T").replace("ʔ", "t")  # Kokoro 1.0's flap and glottal stop
    return ipa.replace("^", "")


class _MisakiG2P(en.G2P):
    """misaki's English G2P with a spaCy model loaded from a folder.

    misaki's own constructor installs the spaCy model with pip when it's missing, which
    doesn't work in an installed app. This sets the same attributes without that step.
    """

    def __init__(self, nlp, british: bool, fallback: EspeakFallback | None) -> None:
        self.version = None
        self.british = british
        self.nlp = nlp
        self.lexicon = en.Lexicon(british)
        self.fallback = fallback
        self.unk = ""


class EnglishG2P:
    def __init__(self, spacy_model: Path, british: bool, espeak: str | None) -> None:
        import spacy  # slow to import, so only when a voice is actually needed

        nlp = spacy.load(spacy_model, enable=["tok2vec", "tagger"])
        fallback = EspeakFallback(espeak, british) if espeak else None
        self._g2p = _MisakiG2P(nlp, british, fallback)
        self._unknown: set[str] = set()

    def __call__(self, text: str) -> str:
        phonemes, tokens = self._g2p(text)
        for token in tokens:
            if token.phonemes is None and token.text not in self._unknown:
                self._unknown.add(token.text)
                log.warning("No pronunciation found for %r, so it will be skipped.", token.text)
        return phonemes.strip()
