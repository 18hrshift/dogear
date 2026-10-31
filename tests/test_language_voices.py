"""Which voice reads which language: [voice.languages] and [voice] other_languages, with
stand-in engines beside Kokoro."""

import pytest
from engine_fakes import fake_engine, hum_voice

from dogear.config import load_config
from dogear.errors import ConfigError
from dogear.language_match import lookup_keys, most_specific, primary, same_language
from dogear.voice.engines import find_voice
from dogear.voice.language_voices import LanguageVoices, best_voice, voices_for, voices_for_run


def lilt(**attributes):
    """An engine with voices in French (two kinds), German, and British English."""
    voices = [
        hum_voice("fr_one", "fr-FR", description="French"),
        hum_voice("fr_ca", "fr-CA", description="Canadian French"),
        hum_voice("de_one", "de-DE", description="German"),
        hum_voice("en_two", "en-GB", description="British English"),
    ]
    return fake_engine("lilt", "Lilt", voices, sample_rate=22050, **attributes)


@pytest.fixture
def with_lilt(installed_engines):
    installed_engines(lilt())


def settings(tmp_path, text: str):
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def spec(choices: LanguageVoices, lang):
    return choices.voice_for(lang).spec


# Matching tags.


def test_tags_match_most_specific_first():
    assert lookup_keys("pt-BR") == ["pt-br", "pt"]
    table = {"fr": 1, "fr-ca": 2}
    assert most_specific(table, "fr-CA") == 2
    assert most_specific(table, "fr-FR") == 1
    assert most_specific(table, "FR") == 1
    assert most_specific(table, "de") is None
    assert most_specific(table, None) is None
    assert primary("fr-CA") == "fr" and primary(None) == "en"
    assert same_language("EN-gb", "en") and not same_language("fr", "de")


def test_three_letter_codes_and_underscores_match_their_language():
    assert primary("eng") == "en" and primary("fra-CA") == "fr" and primary("en_US") == "en"
    assert lookup_keys("en_US") == ["en-us", "en"]
    assert most_specific({"fr": 1}, "fra") == 1
    assert most_specific({"FR": 1}, "fr-BE") == 1
    assert primary("kab") == "kab"  # no two-letter code: as it is


def test_a_book_marked_eng_is_english(config):
    assert LanguageVoices.from_config(config).speaks("eng")


# Choosing.


def test_by_default_the_main_voice_reads_everything(with_lilt, config):
    choices = LanguageVoices.from_config(config)
    for lang in (None, "en", "en-GB", "fr", "de-AT"):
        assert spec(choices, lang) == "kokoro:af_heart"
    assert choices.speaks("en-GB")
    assert not choices.speaks("fr")
    assert choices.languages() == {"en"}


def test_a_mapped_voice_reads_its_language_most_specific_first(with_lilt, config):
    config["voice"]["languages"] = {"fr": "lilt:fr_one", "fr-CA": "lilt:fr_ca"}
    choices = LanguageVoices.from_config(config)
    assert spec(choices, "fr") == "lilt:fr_one"
    assert spec(choices, "fr-BE") == "lilt:fr_one"
    assert spec(choices, "fr-ca") == "lilt:fr_ca"
    assert spec(choices, "en") == "kokoro:af_heart"
    assert spec(choices, "de") == "kokoro:af_heart"  # not mapped, and other_languages = main
    assert choices.languages() == {"en", "fr"}


def test_a_mapping_beats_the_main_voice_for_a_variety_of_its_language(with_lilt, config):
    config["voice"]["languages"] = {"en-GB": "lilt:en_two"}
    choices = LanguageVoices.from_config(config)
    assert spec(choices, "en-GB") == "lilt:en_two"
    assert spec(choices, "en-US") == "kokoro:af_heart"
    assert spec(choices, None) == "kokoro:af_heart"


def test_best_finds_a_voice_for_any_language_with_none_mapped(with_lilt, config):
    config["voice"]["other_languages"] = "best"
    choices = LanguageVoices.from_config(config)
    assert spec(choices, "de-AT") == "lilt:de_one"
    assert spec(choices, "fr-CA") == "lilt:fr_ca"  # its exact tag first
    assert spec(choices, "fr") == "lilt:fr_one"
    # The main voice speaks English, so it keeps reading every kind of English.
    assert spec(choices, "en-GB") == "kokoro:af_heart"
    assert spec(choices, "ja") == "kokoro:af_heart"
    assert not choices.speaks("ja")
    assert choices.languages() == {"en", "fr", "de"}


def test_best_prefers_the_main_voices_engine(installed_engines, config):
    other = fake_engine("alto", "Alto", [hum_voice("alto_fr", "fr-FR", description="French")])
    installed_engines(lilt(), other)
    config["voice"]["other_languages"] = "best"
    main = find_voice("lilt:en_two")
    assert LanguageVoices.from_config(config, main).voice_for("fr").spec == "lilt:fr_one"
    # Otherwise the engines go in the order `dogear voices` lists them.
    assert best_voice("fr").spec == "alto:alto_fr"
    assert [c.spec for c in voices_for("fr")] == ["alto:alto_fr", "lilt:fr_one", "lilt:fr_ca"]


def test_the_other_languages_setting_changes_who_reads(with_lilt, config):
    assert spec(LanguageVoices.from_config(config), "de") == "kokoro:af_heart"
    config["voice"]["other_languages"] = "best"
    assert spec(LanguageVoices.from_config(config), "de") == "lilt:de_one"


def test_voices_for_run_lists_every_voice_the_settings_may_use(with_lilt, config):
    assert [c.spec for c in voices_for_run(config)] == ["kokoro:af_heart"]
    config["voice"]["languages"] = {"fr": "lilt:fr_one"}
    assert [c.spec for c in voices_for_run(config)] == ["kokoro:af_heart", "lilt:fr_one"]
    config["voice"]["other_languages"] = "best"
    # The mapping covers every French, fr-CA too; "best" adds German.
    specs = ["kokoro:af_heart", "lilt:fr_one", "lilt:de_one"]
    assert [c.spec for c in voices_for_run(config)] == specs
    config["voice"]["languages"] = {}
    specs = ["kokoro:af_heart", "lilt:de_one", "lilt:fr_one", "lilt:fr_ca"]
    assert [c.spec for c in voices_for_run(config)] == specs
    main = find_voice("lilt:en_two")
    assert voices_for_run(config, main)[0].spec == "lilt:en_two"


# Checking the settings as they load.


def test_mapped_voices_load_from_a_settings_file(with_lilt, tmp_path):
    config = settings(tmp_path, '[voice.languages]\nfr = "lilt:fr_one"\nde = "de_one"\n')
    choices = LanguageVoices.from_config(config)
    assert spec(choices, "fr") == "lilt:fr_one"
    assert spec(choices, "de") == "lilt:de_one"  # a name only one engine has


@pytest.mark.parametrize(
    ("text", "message", "hint"),
    [
        (
            '[voice.languages]\nfr = "piper:fr_FR-mls-medium"\n',
            "no voice engine called 'piper' is installed",
            "Installed engines: kokoro, lilt.",
        ),
        (
            '[voice.languages]\nfr = "lilt:fr_two"\n',
            "The Lilt voice engine has no voice called 'fr_two'.",
            "dogear voices",
        ),
        (
            '[voice.languages]\nfr = "lilt:de_one"\n',
            "voice.languages.fr is lilt:de_one, which speaks de-DE (German), not fr.",
            "Voices for fr: lilt:fr_one, lilt:fr_ca.",
        ),
        (
            '[voice.languages]\nit = "lilt:de_one"\n',
            "not it.",
            "No installed voice speaks it.",
        ),
        (
            '[voice.languages]\nFrench = "lilt:fr_one"\n',
            "isn't a BCP 47 tag",
            "Name each entry after the language",
        ),
        (
            '[voice.languages]\nfr = "lilt:fr_one"\nFR = "lilt:fr_ca"\n',
            "lists the language FR twice",
            "Keep one",
        ),
        (
            '[voice]\nother_languages = "any"\n',
            "voice.other_languages is 'any'",
            '"best"',
        ),
        (
            "[voice.languages]\nfr = 3\n",
            "'voice.languages.fr' must be text",
            "",
        ),
    ],
)
def test_mistakes_are_found_as_the_settings_load(with_lilt, tmp_path, text, message, hint):
    with pytest.raises(ConfigError) as err:
        settings(tmp_path, text)
    assert message in err.value.message
    assert hint in err.value.hint
