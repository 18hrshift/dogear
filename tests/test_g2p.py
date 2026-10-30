"""English phonemes: the espeak-ng mapping, the espeak-ng fallback, and misaki with spaCy.

espeak-ng is replaced by a small Python script, and spaCy's model by a blank English
pipeline, so nothing here needs a download. `test_espeak_program.py` runs the real program.
"""

import json
import logging
import sys
from pathlib import Path

import pytest
from misaki.en import MToken

from dogear.errors import ToolFailedError
from dogear.pronunciations import load_dictionary
from dogear.voice import g2p
from dogear.voice.g2p import EnglishG2P, EspeakFallback, count_unknown_words, to_misaki

# misaki 0.9.4 loads its dictionaries with a deprecated importlib call.
pytestmark = pytest.mark.filterwarnings("ignore:open_text is deprecated:DeprecationWarning")

PROGRAM = "espeak-ng-under-test"

FAKE_ESPEAK = """\
import json
import os
import sys
from pathlib import Path

here = Path(__file__).parent
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
text = sys.stdin.read()
with (here / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"args": sys.argv[1:], "stdin": text, "cwd": os.getcwd()}) + "\\n")
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
        ("skwˈe^ə", "skwˈɛː"),  # square, as misaki's British dictionary has it
        ("blˈe^ə", "blˈɛː"),  # Blair
        ("ˈe^əɹən", "ˈɛːɹən"),  # Aaron
        ("ɹˈed", "ɹˈAd"),  # a lone e is still A
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
    assert call["args"] == ["-q", "--ipa", "--tie=^", "-v", "en-us"]
    assert call["stdin"] == "Jekyll\n"


@pytest.mark.parametrize("word", ["--help", "-v", "--version", "-w", "/tmp/out.wav"])
def test_words_that_look_like_options_stay_words(espeak, word):
    espeak.answer(word, "hˈɛlp")
    phonemes, rating = EspeakFallback(PROGRAM, british=False)(token(word))
    assert (phonemes, rating) == ("hˈɛlp", 1)
    [call] = espeak.calls()
    assert call["args"] == ["-q", "--ipa", "--tie=^", "-v", "en-us"]
    assert call["stdin"] == word + "\n"


def test_british_voices_use_british_espeak(espeak):
    espeak.answer("Hyde", "hˈa^ɪd")
    EspeakFallback(PROGRAM, british=True)(token("Hyde"))
    assert espeak.calls()[0]["args"][-2:] == ["-v", "en-gb"]


def test_a_data_folder_is_where_espeak_runs(espeak, tmp_path):
    # A standalone build's espeak-ng runs beside its data and is told it's there; the
    # folder's name never goes on its command line. Other copies find their own.
    espeak.answer("Jekyll", "d^ʒˈɛkɪl")
    data = tmp_path / "tools"
    data.mkdir()
    EspeakFallback(PROGRAM, british=False, data=data)(token("Jekyll"))
    [call] = espeak.calls()
    assert call["args"] == ["--path=.", "-q", "--ipa", "--tie=^", "-v", "en-us"]
    assert Path(call["cwd"]).resolve() == data.resolve()


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


def test_espeak_data_folder_reaches_the_fallback(blank_spacy, tmp_path, espeak):
    espeak.answer("Zorblax", "zˈɔːblæks")
    data = tmp_path / "tools"
    data.mkdir()
    EnglishG2P(tmp_path, british=False, espeak=PROGRAM, espeak_data=data)("Hello Zorblax")
    [call] = espeak.calls()
    assert call["args"][0] == "--path=."
    assert Path(call["cwd"]).resolve() == data.resolve()


def test_output_has_no_edge_whitespace(blank_spacy, tmp_path):
    g = EnglishG2P(tmp_path, british=False, espeak=None)
    phonemes = g("  Hello  ")
    assert phonemes == phonemes.strip()


# Phoneme entries from the user's pronunciation files.

WORDS = """\
[words]
Lanyon = { phonemes = "lˈænjən" }
Watt = { phonemes = "wˈɑt" }
Ross = { phonemes = "ɹˈɔs" }
"Hyde Park" = { phonemes = "ʤˈʌmbO pˈɑɹk" }
Poole = { phonemes = "pˈOlA" }
Utterson = "utter son"
"""


@pytest.fixture
def words(tmp_path):
    path = tmp_path / "words.toml"
    path.write_text(WORDS, encoding="utf-8")
    return load_dictionary([path])


@pytest.mark.parametrize(
    ("text", "phonemes"),
    [
        ("Hello Lanyon", "həlˈO lˈænjən"),
        ("Hello LANYON", "həlˈO lˈænjən"),
        ("Hello Hyde Park", "həlˈO ʤˈʌmbO pˈɑɹk"),  # several words, pinned as one
        ("Hello Hyde  Park", "həlˈO ʤˈʌmbO pˈɑɹk"),
        # A possessive gets misaki's own ending for the sound before it.
        ("Hello Lanyon's", "həlˈO lˈænjənz"),
        ("Hello Lanyon’s", "həlˈO lˈænjənz"),
        ("Hello Watt's", "həlˈO wˈɑts"),
        ("Hello Ross's", "həlˈO ɹˈɔsᵻz"),
    ],
)
def test_phoneme_entries_are_pinned_exactly(blank_spacy, tmp_path, words, text, phonemes):
    assert EnglishG2P(tmp_path, british=False, espeak=None, dictionary=words)(text) == phonemes


def test_pinned_possessives_follow_the_accent(blank_spacy, tmp_path, words):
    british = EnglishG2P(tmp_path, british=True, espeak=None, dictionary=words)
    assert british("Hello Ross's") == "həlˈQ ɹˈɔsɪz"


def test_pinned_words_never_reach_espeak(blank_spacy, tmp_path, espeak, words, caplog):
    espeak.answer("Lanyon", "lˈanjən")
    g = EnglishG2P(tmp_path, british=False, espeak=PROGRAM, dictionary=words)
    with caplog.at_level(logging.WARNING, logger="dogear.voice.g2p"):
        assert g("Hello Lanyon") == "həlˈO lˈænjən"
    assert espeak.calls() == []
    assert caplog.records == []


def test_sounds_like_entries_are_not_pinned(blank_spacy, tmp_path, espeak, words):
    # Sounds-like entries are applied to the text before the voice sees it.
    espeak.answer("Utterson", "ˈʌɾɚsən")
    g = EnglishG2P(tmp_path, british=False, espeak=PROGRAM, dictionary=words)
    assert g("Hello Utterson") == "həlˈO ˈʌTəɹsən"


def test_a_word_inside_a_longer_token_is_not_pinned_and_later_ones_still_are(
    blank_spacy, tmp_path, words
):
    # spaCy keeps "lanyon@example.com" as one token. misaki's own markup slips here and
    # pins Poole's phonemes to the word after it.
    g = EnglishG2P(tmp_path, british=False, espeak=None, dictionary=words)
    phonemes = g("Hello lanyon@example.com and Poole")
    assert "lˈænjən" not in phonemes
    assert phonemes.endswith("ænd pˈOlA")


def test_book_text_is_never_read_as_misaki_markup(blank_spacy, tmp_path):
    # Through misaki's markup parser, this would be just the phonemes "x".
    phonemes = EnglishG2P(tmp_path, british=False, espeak=None)("[Hello](/x/)")
    assert "həlˈO" in phonemes


def test_without_a_dictionary_nothing_is_pinned(blank_spacy, tmp_path, espeak):
    espeak.answer("Lanyon", "lˈanjən")
    assert EnglishG2P(tmp_path, british=False, espeak=PROGRAM)("Hello Lanyon") == "həlˈO lˈanjən"


# Counting unknown words, for `dogear words`.


def test_count_unknown_words_counts_what_would_go_to_espeak(blank_spacy, tmp_path, words):
    texts = ["Hello Zorblax", "Zorblax's hello, Lanyon and Utterson", "Hello Zorblax"]
    counts = count_unknown_words(texts, tmp_path / "model", british=False, dictionary=words)
    # Lanyon has a phoneme entry, so it's known; the rest go to espeak-ng as written.
    assert counts == {"Zorblax": 2, "Zorblax's": 1, "Utterson": 1}
    assert blank_spacy == [(tmp_path / "model", ["tok2vec", "tagger"])]


def test_count_unknown_words_never_runs_espeak(blank_spacy, tmp_path, monkeypatch):
    def no_programs(*args, **kwargs):
        raise AssertionError("counting must not run espeak-ng")

    monkeypatch.setattr(g2p, "run_tool", no_programs)
    empty = load_dictionary([])
    assert count_unknown_words(["Hello Zorblax"], tmp_path, False, empty) == {"Zorblax": 1}
