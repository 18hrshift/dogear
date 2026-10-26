"""English phonemes: the espeak-ng mapping, the espeak-ng fallback, and misaki with spaCy.

espeak-ng is replaced by a small Python script, and spaCy's model by a blank English
pipeline, so nothing here needs a download. `test_espeak_program.py` runs the real program.
"""

import json
import logging
import sys

import pytest
from misaki.en import MToken

from dogear.errors import ToolFailedError
from dogear.voice import g2p
from dogear.voice.g2p import EnglishG2P, EspeakFallback, to_misaki

# misaki 0.9.4 loads its dictionaries with a deprecated importlib call.
pytestmark = pytest.mark.filterwarnings("ignore:open_text is deprecated:DeprecationWarning")

PROGRAM = "espeak-ng-under-test"

FAKE_ESPEAK = """\
import json
import sys
from pathlib import Path

here = Path(__file__).parent
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
text = sys.stdin.read()
with (here / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"args": sys.argv[1:], "stdin": text}) + "\\n")
answers = json.loads((here / "answers.json").read_text(encoding="utf-8"))
sys.stdout.write(answers.get(text.strip(), ""))
"""


class FakeEspeak:
    def __init__(self, folder):
        self.folder = folder
        self.answers: dict[str, str] = {}
        self.save()

    def answer(self, word: str, ipa: str) -> None:
        self.answers[word] = ipa
        self.save()

    def save(self) -> None:
        path = self.folder / "answers.json"
        path.write_text(json.dumps(self.answers), encoding="utf-8")

    def calls(self) -> list[dict]:
        log = self.folder / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def espeak(tmp_path, monkeypatch):
    """espeak-ng as a Python script, run through the real run_tool with the same arguments."""
    folder = tmp_path / "espeak"
    folder.mkdir()
    script = folder / "fake_espeak.py"
    script.write_text(FAKE_ESPEAK, encoding="utf-8")
    real_run_tool = g2p.run_tool

    def run_tool(cmd, **kwargs):
        assert cmd[0] == PROGRAM
        return real_run_tool([sys.executable, str(script), *cmd[1:]], **kwargs)

    monkeypatch.setattr(g2p, "run_tool", run_tool)
    return FakeEspeak(folder)


def token(text: str) -> MToken:
    return MToken(text=text, tag="NNP", whitespace="")


# espeak-ng IPA to misaki phonemes.


@pytest.mark.parametrize("british", [False, True])
@pytest.mark.parametrize(
    ("ipa", "phonemes"),
    [
        ("d^ʒˈɛkɪl", "ʤˈɛkɪl"),  # Jekyll
        ("hˈa^ɪd", "hˈId"),  # Hyde
        ("nˈa^ʊ", "nˈW"),
        ("dˈe^ɪ", "dˈA"),
        ("bˈɔ^ɪ", "bˈY"),
        ("t^ʃˈɪp", "ʧˈɪp"),
        ("lˈɪtə^l", "lˈɪtᵊl"),
        ("lˈɪtl̩", "lˈɪtᵊl"),  # a syllabic consonant gets a schwa before it
        ("bˈʌʔn̩", "bˈʌtn"),  # Kokoro 1.0 has no glottal stop
        ("wˈɔɾə", "wˈɔTə"),  # or flap
        ("lˈɒx", "lˈɒk"),
        ("rˈʌn", "ɹˈʌn"),
        ("ɡˈo", "ɡˈɔ"),  # espeak-ng before 1.52
        ("bɐnˈænə", "bənˈænə"),
    ],
)
def test_to_misaki_shared_mappings(ipa, phonemes, british):
    assert to_misaki(ipa, british) == phonemes


@pytest.mark.parametrize(
    ("ipa", "phonemes"),
    [
        ("həlˈo^ʊ", "həlˈO"),
        ("bˈɜːd", "bˈɜɹd"),
        ("bˈɜːɹd", "bˈɜɹd"),
        ("nˈɪə", "nˈiə"),
        ("bˈʌtɚ", "bˈʌtəɹ"),
        ("fˈɑːðɚ", "fˈɑðəɹ"),  # no long vowels
    ],
)
def test_to_misaki_american(ipa, phonemes):
    assert to_misaki(ipa, british=False) == phonemes


@pytest.mark.parametrize(
    ("ipa", "phonemes"),
    [
        ("həlˈə^ʊ", "həlˈQ"),
        ("bˈɜːd", "bˈɜːd"),  # long vowels stay
        ("nˈiə", "nˈɪə"),
        ("fˈɑːðə", "fˈɑːðə"),
    ],
)
def test_to_misaki_british(ipa, phonemes):
    assert to_misaki(ipa, british=True) == phonemes


def test_to_misaki_leaves_no_ties():
    assert "^" not in to_misaki("k^w ɐ^ɪ d^ʒ", british=False)


# The espeak-ng fallback.


def test_fallback_sends_the_word_on_stdin(espeak):
    espeak.answer("Jekyll", "d^ʒˈɛkɪl")
    assert EspeakFallback(PROGRAM, british=False)(token("Jekyll")) == ("ʤˈɛkɪl", 1)
    [call] = espeak.calls()
    assert call == {"args": ["-q", "--ipa", "--tie=^", "-v", "en-us"], "stdin": "Jekyll\n"}


@pytest.mark.parametrize("word", ["--help", "-v", "--version", "-w", "/tmp/out.wav"])
def test_words_that_look_like_options_stay_words(espeak, word):
    espeak.answer(word, "hˈɛlp")
    phonemes, rating = EspeakFallback(PROGRAM, british=False)(token(word))
    assert (phonemes, rating) == ("hˈɛlp", 1)
    [call] = espeak.calls()
    assert call == {"args": ["-q", "--ipa", "--tie=^", "-v", "en-us"], "stdin": word + "\n"}


def test_british_voices_use_british_espeak(espeak):
    espeak.answer("Hyde", "hˈa^ɪd")
    EspeakFallback(PROGRAM, british=True)(token("Hyde"))
    assert espeak.calls()[0]["args"][-2:] == ["-v", "en-gb"]


def test_fallback_asks_once_per_word(espeak):
    espeak.answer("Utterson", "ˈʌɾɚsən")
    fallback = EspeakFallback(PROGRAM, british=False)
    first = fallback(token("Utterson"))
    assert fallback(token("Utterson")) == first == ("ˈʌTəɹsən", 1)
    fallback(token("Poole"))
    fallback(token("Poole"))  # an unknown word is remembered as unknown, too
    assert [c["stdin"] for c in espeak.calls()] == ["Utterson\n", "Poole\n"]


@pytest.mark.parametrize("output", ["", "\n", "  \n \n"])
def test_empty_output_means_no_pronunciation(espeak, output):
    espeak.answer("Zzxq", output)
    assert EspeakFallback(PROGRAM, british=False)(token("Zzxq")) == (None, None)


def test_multiline_output_is_joined(espeak):
    espeak.answer("Lanyon", " lˈanjən\n ")
    assert EspeakFallback(PROGRAM, british=True)(token("Lanyon")) == ("lˈanjən", 1)


def test_espeak_failure_is_loud(monkeypatch):
    fallback = EspeakFallback(sys.executable, british=False)
    real_run_tool = g2p.run_tool

    def run_failing(cmd, **kwargs):
        return real_run_tool([cmd[0], "-c", "import sys; sys.exit(2)"], **kwargs)

    monkeypatch.setattr(g2p, "run_tool", run_failing)
    with pytest.raises(ToolFailedError, match="exit code 2"):
        fallback(token("Carew"))


# misaki with a spaCy pipeline.


@pytest.fixture
def blank_spacy(monkeypatch):
    """spaCy's blank English pipeline in place of the downloaded model; records loads."""
    import spacy

    loads = []

    def load(path, enable):
        loads.append((path, enable))
        return spacy.blank("en")

    monkeypatch.setattr(spacy, "load", load)
    return loads


def test_english_g2p_loads_the_model_folder(blank_spacy, tmp_path):
    EnglishG2P(tmp_path / "en_core_web_sm-3.8.0", british=False, espeak=None)
    assert blank_spacy == [(tmp_path / "en_core_web_sm-3.8.0", ["tok2vec", "tagger"])]


def test_english_g2p_known_words(blank_spacy, tmp_path):
    american = EnglishG2P(tmp_path, british=False, espeak=None)
    british = EnglishG2P(tmp_path, british=True, espeak=None)
    assert american("Hello") == "həlˈO"
    assert british("Hello") == "həlˈQ"


def test_unknown_words_are_skipped_with_one_warning(blank_spacy, tmp_path, caplog):
    g = EnglishG2P(tmp_path, british=False, espeak=None)
    with caplog.at_level(logging.WARNING, logger="dogear.voice.g2p"):
        first = g("Hello Zorblax")
        second = g("Zorblax hello")
    assert first == second == "həlˈO"
    warnings = [r.getMessage() for r in caplog.records]
    assert warnings == ["No pronunciation found for 'Zorblax', so it will be skipped."]


def test_unknown_words_go_to_espeak(blank_spacy, tmp_path, espeak):
    espeak.answer("Zorblax", "zˈɔːblæks")
    g = EnglishG2P(tmp_path, british=True, espeak=PROGRAM)
    assert g("Hello Zorblax") == "həlˈQ zˈɔːblæks"
    assert [(c["args"][-1], c["stdin"]) for c in espeak.calls()] == [("en-gb", "Zorblax\n")]


def test_output_has_no_edge_whitespace(blank_spacy, tmp_path):
    g = EnglishG2P(tmp_path, british=False, espeak=None)
    phonemes = g("  Hello  ")
    assert phonemes == phonemes.strip()
