"""The voice catalog and setting up the configured voice, with no real model or download."""

import re
import sys
import zipfile

import pytest
from kokoro_fakes import use_fake_session, write_tokenizer, write_voice

from dogear.errors import ToolNotFoundError, VoiceError
from dogear.voice import _check_engine, find_voice, make_engine, prepare_kokoro
from dogear.voice import downloads as downloads_module
from dogear.voice.catalog import (
    catalog,
    kokoro_file,
    kokoro_voices,
    spacy_model_dir,
    spacy_wheel,
)

SHA256 = re.compile(r"[0-9a-f]{64}")

# misaki 0.9.4 loads its dictionaries with a deprecated importlib call.
pytestmark = pytest.mark.filterwarnings("ignore:open_text is deprecated:DeprecationWarning")


# The catalog.


@pytest.mark.parametrize("voice", kokoro_voices(), ids=lambda v: v.name)
def test_every_voice_is_pinned_and_described(voice):
    entry = catalog()["kokoro"]["voices"][voice.name]
    assert SHA256.fullmatch(entry["sha256"])
    assert voice.accent in ("American", "British")
    assert voice.gender in ("female", "male")
    assert re.fullmatch(r"[A-F][+-]?", voice.grade)
    # The name's first letter is the accent and the second the gender.
    assert voice.name[0] == ("b" if voice.british else "a")
    assert voice.name[1] == voice.gender[0]


def test_every_voice_file_is_different():
    hashes = [v["sha256"] for v in catalog()["kokoro"]["voices"].values()]
    assert len(set(hashes)) == len(hashes)


def test_every_other_download_is_pinned():
    kokoro = catalog()["kokoro"]
    entries = [*kokoro["models"].values(), kokoro["tokenizer"], catalog()["spacy"]]
    for entry in entries:
        assert SHA256.fullmatch(entry["sha256"])
        assert entry["size"] > 0


def test_kokoro_files_come_from_one_pinned_revision():
    base_url = catalog()["kokoro"]["base_url"]
    assert base_url.startswith("https://")
    assert re.search(r"/resolve/[0-9a-f]{40}$", base_url)


def test_default_voice_is_in_the_catalog(config):
    assert find_voice(config["voice"]["voice"]).name == config["voice"]["voice"]


def test_default_model_build_is_in_the_catalog(config):
    assert config["kokoro"]["model"] in catalog()["kokoro"]["models"]


def test_default_engine_is_known(config):
    _check_engine(config)


def test_kokoro_file_locations(tmp_path):
    base_url = catalog()["kokoro"]["base_url"]
    model = kokoro_file("model", "quantized", tmp_path)
    assert model.url == f"{base_url}/onnx/model_quantized.onnx"
    assert model.path == tmp_path / "kokoro" / "onnx" / "model_quantized.onnx"
    assert model.sha256 == catalog()["kokoro"]["models"]["quantized"]["sha256"]
    voice = kokoro_file("voice", "bf_emma", tmp_path)
    assert voice.url == f"{base_url}/voices/bf_emma.bin"
    assert voice.path == tmp_path / "kokoro" / "voices" / "bf_emma.bin"
    assert voice.sha256 == catalog()["kokoro"]["voices"]["bf_emma"]["sha256"]
    tokenizer = kokoro_file("tokenizer", "", tmp_path)
    assert tokenizer.path == tmp_path / "kokoro" / "tokenizer.json"
    with pytest.raises(ValueError, match="unknown Kokoro file kind"):
        kokoro_file("vocoder", "", tmp_path)


def test_spacy_file_locations(tmp_path):
    wheel = spacy_wheel(tmp_path)
    assert wheel.url.endswith(".whl")
    assert wheel.path == tmp_path / "downloads" / "en_core_web_sm-3.8.0-py3-none-any.whl"
    assert spacy_model_dir(tmp_path) == tmp_path / "spacy" / "en_core_web_sm-3.8.0"


# Choosing and preparing the voice.

SYMBOLS = " .,!?;:'\"()abcdefhijklmnopqrstuvwxyzæðŋɑɔəɛɜɡɪɹʃʊʌʒʤʧθᵊˈˌAIOQWYTː"


@pytest.fixture
def models(tmp_path, config):
    """Points models.dir at an empty folder and returns it."""
    folder = tmp_path / "models"
    config["models"]["dir"] = str(folder)
    return folder


def install_voice(models_dir, voice="af_heart", build="full"):
    """Puts stand-ins for every file the voice needs where Dogear looks for them."""
    model = kokoro_file("model", build, models_dir).path
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"not a real model")
    write_tokenizer(kokoro_file("tokenizer", "", models_dir).path, SYMBOLS)
    write_voice(kokoro_file("voice", voice, models_dir).path, rows=510)
    spacy_dir = spacy_model_dir(models_dir)
    spacy_dir.mkdir(parents=True, exist_ok=True)
    (spacy_dir / "config.cfg").write_text("[nlp]", encoding="utf-8")


@pytest.fixture
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("tests must not download anything")

    monkeypatch.setattr(downloads_module.urllib.request, "urlopen", fail)


@pytest.fixture
def fake_downloads(monkeypatch):
    """Replaces ensure_files: records what was asked for and writes stand-in files."""
    requested = []

    def fake_ensure_files(files, config, report):
        requested.append([f.path.name for f in files])
        for remote in files:
            remote.path.parent.mkdir(parents=True, exist_ok=True)
            if remote.path.suffix == ".whl":
                model_dir = catalog()["spacy"]["model_dir"]
                with zipfile.ZipFile(remote.path, "w") as wheel:
                    wheel.writestr(f"{model_dir}/config.cfg", "[nlp]")
            else:
                remote.path.write_bytes(b"stand-in")

    monkeypatch.setattr("dogear.voice.ensure_files", fake_ensure_files)
    return requested


def test_find_voice():
    voice = find_voice("bf_emma")
    assert (voice.name, voice.accent, voice.british) == ("bf_emma", "British", True)
    assert not find_voice("af_heart").british


def test_unknown_voice_has_a_hint():
    with pytest.raises(VoiceError, match="no voice called 'af_nobody'") as err:
        find_voice("af_nobody")
    assert "dogear voices" in err.value.hint


@pytest.mark.parametrize(
    ("section", "key", "value", "message", "hint"),
    [
        ("voice", "engine", "piper", "voice.engine is 'piper'", "kokoro"),
        ("voice", "voice", "af_nobody", "no voice called 'af_nobody'", "dogear voices"),
        ("kokoro", "model", "q8f16", "kokoro.model is 'q8f16'", "full, quantized"),
    ],
)
def test_bad_voice_settings_fail_before_any_download(
    config, models, fake_downloads, section, key, value, message, hint
):
    config[section][key] = value
    with pytest.raises(VoiceError, match=message) as err:
        prepare_kokoro(config, print)
    assert hint in err.value.hint
    assert fake_downloads == []


def test_first_run_downloads_every_file_and_unpacks_spacy(config, models, fake_downloads):
    setup = prepare_kokoro(config, print)
    assert fake_downloads == [
        ["model.onnx", "tokenizer.json", "af_heart.bin", "en_core_web_sm-3.8.0-py3-none-any.whl"]
    ]
    assert setup.voice.name == "af_heart"
    assert setup.model.path == models / "kokoro" / "onnx" / "model.onnx"
    assert setup.tokenizer.path == models / "kokoro" / "tokenizer.json"
    assert setup.voice_file.path == models / "kokoro" / "voices" / "af_heart.bin"
    assert (spacy_model_dir(models) / "config.cfg").is_file()
    assert not spacy_wheel(models).path.exists()


def test_unpacked_spacy_model_is_not_downloaded_again(config, models, fake_downloads):
    prepare_kokoro(config, print)
    prepare_kokoro(config, print)
    assert fake_downloads[1] == ["model.onnx", "tokenizer.json", "af_heart.bin"]


def test_nothing_is_downloaded_when_every_file_is_there(config, models, no_network):
    install_voice(models)
    lines = []
    prepare_kokoro(config, lines.append)
    assert lines == []


def test_voice_and_model_settings_choose_the_files(config, models, fake_downloads):
    config["voice"]["voice"] = "bm_george"
    config["kokoro"]["model"] = "quantized"
    setup = prepare_kokoro(config, print)
    assert setup.voice.british
    assert setup.model.path.name == "model_quantized.onnx"
    assert setup.voice_file.path.name == "bm_george.bin"
    assert fake_downloads[0][:3] == ["model_quantized.onnx", "tokenizer.json", "bm_george.bin"]


def test_missing_espeak_is_reported_before_any_download(config, models, fake_downloads, tmp_path):
    config["tools"]["espeak_ng"] = str(tmp_path / "no-such-espeak-ng")
    with pytest.raises(ToolNotFoundError, match="espeak_ng") as err:
        make_engine(config, print)
    assert "eSpeak NG" in err.value.hint
    assert fake_downloads == []


@pytest.fixture
def ready_engine(config, models, monkeypatch, no_network):
    """Everything make_engine needs, faked: model files, spaCy, onnxruntime, espeak-ng."""
    import spacy

    install_voice(models)
    install_voice(models, voice="bf_emma")
    monkeypatch.setattr(spacy, "load", lambda path, enable: spacy.blank("en"))
    config["tools"]["espeak_ng"] = sys.executable  # found, but never run in these tests
    return use_fake_session(monkeypatch)


def test_make_engine_uses_the_configured_settings(config, models, ready_engine):
    config["voice"]["speed"] = 1.25
    config["kokoro"]["threads"] = 3
    engine = make_engine(config, print)
    assert engine.sample_rate == catalog()["kokoro"]["sample_rate"]
    [session] = ready_engine.instances
    assert session.model == str(models / "kokoro" / "onnx" / "model.onnx")
    assert session.options.intra_op_num_threads == 3
    assert session.providers == ["CPUExecutionProvider"]
    audio = engine.render(engine.plan("Hello there."))
    assert len(audio) > 0
    assert session.feeds[0]["speed"].tolist() == [1.25]


def test_make_engine_pronounces_by_the_voices_accent(config, ready_engine):
    american = make_engine(config, print).plan("Hello.").payload
    config["voice"]["voice"] = "bf_emma"
    british = make_engine(config, print).plan("Hello.").payload
    assert "O" in american  # misaki's American "oh" in "hello"
    assert "Q" in british  # and its British one
    assert american != british


def test_make_engine_keys_differ_by_voice(config, ready_engine):
    heart = make_engine(config, print).plan("Good morning.")
    config["voice"]["voice"] = "bf_emma"
    emma = make_engine(config, print).plan("Good morning.")
    assert heart.key != emma.key
