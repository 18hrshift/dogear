import copy

import pytest

from dogear.speech.sentences import SentenceRules, split_sentences


@pytest.fixture
def split(config):
    rules = SentenceRules.from_config(config)
    return lambda text: split_sentences(text, rules)


def test_basic_split(split):
    assert split("First one. Second one! Third one?") == ["First one.", "Second one!", "Third one?"]


def test_titles_and_initials_do_not_end_sentences(split):
    text = "Dr. Smith met J. R. R. Tolkien. They talked."
    assert split(text) == ["Dr. Smith met J. R. R. Tolkien.", "They talked."]


def test_no_before_number_does_not_end_sentence(split):
    assert split("See No. 5 today. Then go.") == ["See No. 5 today.", "Then go."]


def test_no_at_end_still_ends_sentence(split):
    assert split("He said no. Then he left.") == ["He said no.", "Then he left."]


def test_closing_quotes_stay_with_their_sentence(split):
    assert split('"Stop!" She ran. "Why?" he asked.') == ['"Stop!"', "She ran.", '"Why?" he asked.']


def test_lowercase_after_punctuation_is_not_a_boundary(split):
    assert split('"Stop!" she cried.') == ['"Stop!" she cried.']


def test_never_returns_empty_pieces(split):
    assert split("   ") == []
    assert split("Hello world.") == ["Hello world."]


def test_long_sentence_split_at_clauses(config):
    rules = SentenceRules.from_config(config)
    rules = SentenceRules(rules.no_break_after, rules.no_break_before_number, max_chars=30)
    parts = split_sentences("One two three four, five six seven eight; nine ten eleven.", rules)
    assert parts == ["One two three four,", "five six seven eight;", "nine ten eleven."]


def test_long_clause_split_at_spaces_never_mid_word(config):
    rules = SentenceRules.from_config(config)
    rules = SentenceRules(rules.no_break_after, rules.no_break_before_number, max_chars=20)
    parts = split_sentences("word " * 20, rules)
    assert all(len(p) <= 20 for p in parts)
    assert " ".join(parts).split() == ["word"] * 20


def test_config_max_chars_changes_behavior(config):
    custom = copy.deepcopy(config)
    custom["speech"]["max_sentence_chars"] = 10
    long = "alpha beta gamma delta."
    assert len(split_sentences(long, SentenceRules.from_config(config))) == 1
    assert len(split_sentences(long, SentenceRules.from_config(custom))) > 1
