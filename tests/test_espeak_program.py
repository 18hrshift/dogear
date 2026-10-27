"""The real espeak-ng program, as Dogear calls it for words misaki doesn't know.

Run on every CI platform, so the flags and the stdin handoff are checked on Windows and
macOS too, not just against a stand-in.
"""

from types import SimpleNamespace

from conftest import require_tool

from dogear.voice.g2p import EspeakFallback


def test_espeak_names_become_misaki_phonemes():
    fallback = EspeakFallback(require_tool("espeak-ng"), british=False)
    phonemes, rating = fallback(SimpleNamespace(text="Jekyll"))
    assert rating == 1
    assert phonemes.startswith("ʤ")  # espeak's tied d^ʒ, mapped to misaki's single symbol
    assert "^" not in phonemes


def test_text_that_looks_like_an_option_is_read_as_a_word():
    fallback = EspeakFallback(require_tool("espeak-ng"), british=True)
    phonemes, _ = fallback(SimpleNamespace(text="--version"))
    assert phonemes and "eSpeak" not in phonemes
