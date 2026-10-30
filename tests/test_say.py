"""`dogear say`, with a fake voice: what it says, where it saves, and its checks."""

import hashlib

import numpy as np
import pytest

from dogear import cli, say
from dogear.errors import DogearError
from dogear.render.wav import read_wav
from dogear.say import say_text
from dogear.voice.engine import SpeechPlan

RATE = 24000


class ToneEngine:
    """A voice that sounds a tone for a tenth of a second per word; its input is the text
    in capitals, standing in for phonemes."""

    sample_rate = RATE

    def __init__(self) -> None:
        self.rendered: list[str] = []

    def plan(self, text: str) -> SpeechPlan:
        payload = text.upper()
        return SpeechPlan(key=hashlib.sha256(payload.encode()).hexdigest(), payload=payload)

    def render(self, plan: SpeechPlan) -> np.ndarray:
        self.rendered.append(plan.payload)
        samples = int(RATE * 0.1 * len(plan.payload.split()))
        return np.full(samples, 0.3, dtype=np.float32)


@pytest.fixture
def voice(monkeypatch, config, tmp_path):
    """The fake voice in place of the real one; records the config it was made with."""
    config["render"]["cache_dir"] = str(tmp_path / "cache")
    engine = ToneEngine()
    engine.configs = []

    def fake_make_engine(cfg, report):
        engine.configs.append(cfg)
        return engine

    monkeypatch.setattr(say, "make_engine", fake_make_engine)
    return engine


def words_file(tmp_path, text='Utterson = "utter son"\n'):
    path = tmp_path / "words.toml"
    path.write_text("[words]\n" + text, encoding="utf-8")
    return path


def test_says_each_sentence_into_one_wav(voice, config, tmp_path):
    out = tmp_path / "said.wav"
    said = say_text("Dr. Jekyll came home. He had 2 dogs.", out, config, print)
    assert [s.spoken for s in said] == ["Doctor Jekyll came home.", "He had two dogs."]
    assert [s.voice_input for s in said] == ["DOCTOR JEKYLL CAME HOME.", "HE HAD TWO DOGS."]
    samples, rate = read_wav(out)
    assert rate == RATE
    pause = config["narration"]["pauses"]["sentence_ms"] / 1000
    assert len(samples) / RATE == pytest.approx(0.4 + pause + 0.4 + pause, abs=0.01)


def test_pronunciation_files_change_what_is_said(voice, config, tmp_path):
    config["pronunciation"]["files"] = [str(words_file(tmp_path))]
    said = say_text("Utterson met him.", tmp_path / "said.wav", config, print)
    assert [s.spoken for s in said] == ["Utter son met him."]
    assert voice.rendered == ["UTTER SON MET HIM."]


def test_saying_it_again_reuses_the_sentence_cache(voice, config, tmp_path):
    say_text("Hello there. Goodbye.", tmp_path / "one.wav", config, print)
    voice.rendered.clear()
    say_text("Hello there. Goodbye now.", tmp_path / "two.wav", config, print)
    assert voice.rendered == ["GOODBYE NOW."]


def test_makes_the_folder_it_saves_in(voice, config, tmp_path):
    out = tmp_path / "new" / "folder" / "said.wav"
    say_text("Hello.", out, config, print)
    assert out.is_file()


@pytest.mark.parametrize("name", ["said.mp3", "said", "said.wav.txt"])
def test_only_saves_wav_files(voice, config, tmp_path, name):
    with pytest.raises(DogearError, match="doesn't end in .wav") as err:
        say_text("Hello.", tmp_path / name, config, print)
    assert ".wav" in err.value.hint
    assert voice.configs == []  # checked before the voice is loaded


def test_a_folder_is_not_an_output_file(voice, config, tmp_path):
    folder = tmp_path / "out.wav"
    folder.mkdir()
    with pytest.raises(DogearError, match="is a folder"):
        say_text("Hello.", folder, config, print)


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_nothing_to_say_is_explained_before_loading_the_voice(voice, config, tmp_path, text):
    with pytest.raises(DogearError, match="no words to say") as err:
        say_text(text, tmp_path / "said.wav", config, print)
    assert 'dogear say "' in err.value.hint
    assert voice.configs == []


# The command.


def test_cli_say_prints_what_was_said_and_where(voice, capsys, tmp_path):
    out = tmp_path / "said.wav"
    words = words_file(tmp_path)
    assert cli.main(["say", "Utterson met him.", "-o", str(out), "--words", str(words)]) == 0
    assert capsys.readouterr().out == f"Said: Utter son met him.\nSaved: {out}\n"
    assert out.is_file()


def test_cli_say_shows_phonemes_when_asked(voice, capsys, tmp_path):
    out = tmp_path / "said.wav"
    assert cli.main(["say", "Hello. Bye.", "-o", str(out), "--phonemes"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "Said: Hello.",
        "Phonemes: HELLO.",
        "Said: Bye.",
        "Phonemes: BYE.",
        f"Saved: {out}",
    ]


def test_cli_say_uses_the_voice_and_speed_options(voice, tmp_path):
    out = tmp_path / "said.wav"
    assert cli.main(["say", "Hello.", "-o", str(out), "--voice", "bf_emma", "--speed", "1.1"]) == 0
    [config] = voice.configs
    assert (config["voice"]["voice"], config["voice"]["speed"]) == ("bf_emma", 1.1)


def test_cli_say_needs_an_output_file(capsys):
    with pytest.raises(SystemExit):
        cli.main(["say", "Hello."])
    assert "-o/--output" in capsys.readouterr().err


def test_cli_say_takes_text_that_looks_like_an_option_after_two_hyphens(voice, capsys, tmp_path):
    """The web page puts what a person typed after `--`, so it is never an option."""
    out = tmp_path / "said.wav"
    elsewhere = tmp_path / "elsewhere.wav"
    assert cli.main(["say", "-o", str(out), "--", f"-o{elsewhere}"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == f"Saved: {out}"
    assert out.is_file() and not elsewhere.exists()
    assert cli.main(["say", "-o", str(out), "--", "--help"]) == 0
    assert capsys.readouterr().out.startswith("Said: ")
