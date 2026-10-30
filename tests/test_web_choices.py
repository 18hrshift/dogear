"""The choose form: what starts out chosen comes from the config, and what comes back is
checked."""

from dataclasses import replace

from web_samples import CHOSEN, sample_summary

from dogear.make import FORMATS
from dogear.web import choices


def fields(**values):
    sent = {"format": ["m4b"], "voice": ["af_heart"], "speed": ["0.9"], "section": ["1", "2"]}
    sent.update(values)
    return [(name, value) for name, many in sent.items() for value in many]


def test_every_format_dogear_makes_is_offered():
    assert tuple(f.name for f in choices.format_options()) == FORMATS


def test_defaults_come_from_the_config(config):
    config["output"]["formats"] = ["mp3", "daisy"]
    config["voice"]["voice"] = "bf_emma"
    config["voice"]["speed"] = 1.1
    picked = choices.defaults(sample_summary(), config, None)
    assert picked.formats == {"mp3", "daisy"}
    assert picked.voice == "bf_emma"
    assert picked.speed == "1.1"
    assert picked.sections == {1, 2, 3, 4}


def test_a_book_made_before_keeps_its_choices(config):
    picked = choices.defaults(sample_summary(), config, CHOSEN)
    assert picked.formats == {"m4b", "mp3"}
    assert picked.sections == set(CHOSEN.sections)


def test_speeds_are_words_and_mark_the_usual_one(config):
    labels = [option.label for option in choices.speed_options(config)]
    assert labels == [
        "Slower (0.8)",
        "A little slower (0.9), the usual",
        "Natural (1.0)",
        "Faster (1.1)",
    ]
    config["voice"]["speed"] = 1.25
    options = choices.speed_options(config)
    assert [o.value for o in options] == ["0.8", "0.9", "1.0", "1.1", "1.25"]
    assert options[-1].label == "Your usual speed (1.25), the usual"


def test_voices_are_best_rated_first():
    voices = choices.voice_options()
    assert voices[0].label == "af_heart: American English, female, grade A"
    assert voices[-1].label.endswith("grade F+")


def test_good_choices_are_kept_in_format_order(config):
    picked, chosen, errors = choices.check(
        fields(format=["daisy", "m4b"], section=["4", "2"]), sample_summary(), config
    )
    assert errors == {}
    assert chosen.formats == ("m4b", "daisy")
    assert chosen.sections == (2, 4)
    assert chosen.speed == 0.9


def test_each_problem_is_named_by_its_field(config):
    sent = fields(format=["wav"], voice=["nobody"], speed=["3"], section=["9", "x"])
    picked, chosen, errors = choices.check(sent, sample_summary(), config)
    assert chosen is None
    assert set(errors) == {"format", "voice", "speed", "section"}
    assert picked.voice == "nobody"  # shown again as sent, though not in the list


def test_a_book_in_another_language_must_be_read_as_english(config):
    french = replace(sample_summary(), language="fr-FR")
    assert choices.asks_about_language(french)
    assert not choices.asks_about_language(sample_summary())
    assert not choices.asks_about_language(replace(sample_summary(), language=None))
    _, chosen, errors = choices.check(fields(), french, config)
    assert chosen is None
    assert errors["english"].startswith("Dogear's voice speaks only English.")
    _, chosen, errors = choices.check(fields(english=["yes"]), french, config)
    assert errors == {}
    assert chosen.as_english


def test_read_as_english_is_only_kept_when_asked(config):
    _, chosen, _ = choices.check(fields(english=["yes"]), sample_summary(), config)
    assert not chosen.as_english
