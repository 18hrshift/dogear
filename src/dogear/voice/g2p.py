"""English pronunciation for Kokoro: text in, phonemes out.

misaki (Apache-2.0) is the phonemizer Kokoro was trained with. It looks words up in its
dictionaries and uses spaCy part-of-speech tags to choose between heteronyms such as
"read" (present) and "read" (past). Words it doesn't know, mostly names, go to the
espeak-ng program, as in Kokoro's own setup.

misaki's packaged English setup loads espeak-ng as a library through `phonemizer`, both
GPL. Dogear runs the espeak-ng program instead, the same way it runs ffmpeg, so no GPL
code is part of Dogear. misaki is pinned to 0.9.4 because `_MisakiG2P` relies on how
its G2P class sets itself up and builds its tokens.

Phoneme entries in the user's pronunciation files are pinned here: those words get
exactly the phonemes the file gives, and never reach misaki's dictionaries or espeak-ng.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from misaki import en

from dogear.pronunciations import PronunciationDictionary
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
    if british:
        # Before the table, whose "e" -> "A" would otherwise turn "e^ə" into "Aə". misaki
        # 0.9.4 has that order, so its rule never matched; its British lexicon says "ɛː".
        ipa = ipa.replace("e^ə", "ɛː")
    for old, new in _ESPEAK_TO_MISAKI:
        ipa = ipa.replace(old, new)
    ipa = _SYLLABIC.sub(r"ᵊ\1", ipa).replace("̩", "")
    if british:
        ipa = ipa.replace("iə", "ɪə").replace("ə^ʊ", "Q")
    else:
        ipa = ipa.replace("o^ʊ", "O").replace("ɜːɹ", "ɜɹ").replace("ɜː", "ɜɹ")
        ipa = ipa.replace("ɪə", "iə").replace("ː", "")
    ipa = ipa.replace("o", "ɔ")  # espeak-ng before 1.52 writes o for ɔ
    ipa = ipa.replace("ɾ", "T").replace("ʔ", "t")  # Kokoro 1.0's flap and glottal stop
    return ipa.replace("^", "")


_PINNED_RATING = 5  # misaki's rating for phonemes its own markup pins; its dictionaries give 4


class _MisakiG2P(en.G2P):
    """misaki's English G2P with a spaCy model loaded from a folder, and pinned phonemes.

    misaki's own constructor installs the spaCy model with pip when it's missing, which
    doesn't work in an installed app. This sets the same attributes without that step.

    Pinning happens where misaki builds its tokens from spaCy's, which is where misaki
    applies its own `[word](/phonemes/)` markup: the first token of the word gets the
    phonemes and misaki's top rating, and the rest join it with none of their own. The
    other ways in were worse. misaki's dictionary lookup only ever sees one token, or a
    run of tokens with no spaces between, so "Hyde Park" couldn't be an entry, and it
    adds its own stress and capital-letter rules to what it finds. Writing that markup
    into the text would work for several words, but misaki maps markup to spaCy tokens
    by counting, and the count slips when a word ends inside a spaCy token (in
    "lanyon@example.com", say), pinning later words to the wrong tokens. Here each word
    is placed by its character offsets instead, and a word that ends inside a spaCy
    token is left to misaki: spaCy reads it as part of something longer.

    Callers pass `preprocess=False`, so misaki's markup parser never runs and markup-like
    text in a book is read as text.
    """

    def __init__(
        self, nlp, british: bool, fallback, pinned: PronunciationDictionary | None = None
    ) -> None:
        self.version = None
        self.british = british
        self.nlp = nlp
        self.lexicon = en.Lexicon(british)
        self.fallback = fallback
        self.unk = ""
        self.pinned = (pinned or PronunciationDictionary()).with_phonemes()

    def tokenize(self, text: str, tokens, features) -> list[en.MToken]:
        mtokens = super().tokenize(text, tokens, features)
        if self.pinned.entries:
            self._pin(text, mtokens)
        return mtokens

    def _pin(self, text: str, tokens: list[en.MToken]) -> None:
        starts, ends, offset = {}, {}, 0
        for i, token in enumerate(tokens):
            starts[offset] = i
            offset += len(token.text)
            ends[offset] = i
            offset += len(token.whitespace)
        for match, entry in self.pinned.find(text):
            if match.start not in starts or match.end not in ends:
                continue
            first, last = starts[match.start], ends[match.end]
            phonemes = entry.phonemes
            if match.possessive:
                phonemes = self.lexicon._s(phonemes)  # misaki's own -s: z, s, or ᵻz by the sound
            for i in range(first, last + 1):
                tokens[i].phonemes = phonemes if i == first else ""
                tokens[i]._.is_head = i == first
                tokens[i]._.rating = _PINNED_RATING


def _load_spacy(model: Path):
    import spacy  # slow to import, so only when a voice is actually needed

    return spacy.load(model, enable=["tok2vec", "tagger"])


class EnglishG2P:
    def __init__(
        self,
        spacy_model: Path,
        british: bool,
        espeak: str | None,
        dictionary: PronunciationDictionary | None = None,
    ) -> None:
        fallback = EspeakFallback(espeak, british) if espeak else None
        self._g2p = _MisakiG2P(_load_spacy(spacy_model), british, fallback, dictionary)
        self._unknown: set[str] = set()

    def __call__(self, text: str) -> str:
        phonemes, tokens = self._g2p(text.strip(), preprocess=False)
        for token in tokens:
            if token.phonemes is None and token.text not in self._unknown:
                self._unknown.add(token.text)
                log.warning("No pronunciation found for %r, so it will be skipped.", token.text)
        return phonemes.strip()


class _CountUnknown:
    """Takes the espeak-ng fallback's place, counting each word misaki hands it."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def __call__(self, token: en.MToken) -> tuple[None, None]:
        self.counts[token.text] += 1
        return None, None


def count_unknown_words(
    texts: Iterable[str], spacy_model: Path, british: bool, dictionary: PronunciationDictionary
) -> Counter[str]:
    """How often each word misaki doesn't know appears in `texts`: the words the voice
    would send to the espeak-ng program. Words with phoneme entries count as known.
    Needs spaCy's model, but not the voice model or espeak-ng.
    """
    unknown = _CountUnknown()
    g2p = _MisakiG2P(_load_spacy(spacy_model), british, unknown, dictionary)
    for text in texts:
        g2p(text.strip(), preprocess=False)
    return unknown.counts
