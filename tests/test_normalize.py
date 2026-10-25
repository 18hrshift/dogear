import copy

import pytest

from dogear.speech.normalize import SpeechRules, normalize_for_speech


@pytest.fixture
def say(config):
    rules = SpeechRules.from_config(config)
    return lambda text, lang="en": normalize_for_speech(text, rules, lang)


# Ported from audiobook-maker's tests.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dr. Smith", "Doctor Smith"),
        ("fruits, vegetables, etc.", "etcetera"),
        ("cats vs. dogs", "versus"),
        ("There were 42 apples.", "forty-two"),
        ("He finished 1st in the race.", "first"),
    ],
)
def test_ported_expansions(say, text, expected):
    assert expected in say(text)


def test_ported_full_pipeline(say):
    result = say("Dr. Johnson published 3 papers in 1999, etc.")
    assert result == "Doctor Johnson published three papers in nineteen ninety-nine, etcetera."


# Bugs in the old preprocessor, fixed here.
def test_no_at_sentence_end_is_not_number(say):
    assert say("He said no.") == "He said no."


def test_no_before_number_is_number(say):
    assert say("See No. 5 on p. 12.") == "See number five on page twelve."


def test_decimal_digits_read_one_by_one(say):
    assert say("Pi is 3.14 and 3.05.") == "Pi is three point one four and three point zero five."


def test_comma_grouped_numbers(say):
    assert say("1,000 people") == "one thousand people"
    assert say("1,500,000") == "one million, five hundred thousand"


def test_title_needs_a_name_after_it(say):
    assert say("Mrs. Jones lives on Elm Dr. now.") == "Missus Jones lives on Elm Dr. now."


def test_longer_abbreviation_wins(say):
    assert say("pp. 3") == "pages three"


# Numbers.
def test_years_spoken_as_years(say):
    assert say("In 1984 and 2023.") == "In nineteen eighty-four and twenty twenty-three."


def test_long_codes_and_leading_zeros_read_digit_by_digit(say):
    assert say("agent 007") == "agent zero zero seven"
    assert say("code 12345678") == "code one two three four five six seven eight"


def test_numbers_inside_words_untouched(say):
    assert say("Version v1.2 of the MP3 file.") == "Version v1.2 of the MP3 file."


def test_number_range_with_en_dash(say):
    assert say("pages 3–4") == "pages three to four"


def test_other_languages_use_their_number_words(say):
    assert say("Il a 42 ans.", lang="fr") == "Il a quarante-deux ans."


def test_unsupported_language_leaves_digits(say, caplog):
    assert say("42", lang="xx") == "42"
    assert "can't be spelled out" in caplog.text


# Punctuation and leftovers.
def test_curly_quotes_dashes_and_ellipsis(say):
    assert say("“Hi,” she said—quietly…") == '"Hi," she said, quietly...'


def test_markup_characters_removed(say):
    assert say("a *bold* _word_") == "a bold word"


def test_abbreviation_period_kept_only_at_sentence_end(say):
    assert say("apples, etc. and pears") == "apples, etcetera and pears"
    assert say("apples, etc.") == "apples, etcetera."


# Config is the source of truth.
def test_config_table_changes_behavior(config):
    custom = copy.deepcopy(config)
    custom["speech"]["abbreviations"]["approx."] = "about"
    rules = SpeechRules.from_config(custom)
    assert normalize_for_speech("approx. ten", rules, "en") == "about ten"
