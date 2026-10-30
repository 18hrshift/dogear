"""The forms that save spellings: which fields count, which words a Save asks to change,
and what the page shows again when a word was changed in another window."""

from dogear.web.settings import WordLimits
from dogear.web.spelling_forms import (
    SentWord,
    changed_elsewhere,
    sent_words,
    spellings_to_save,
)

LIMITS = WordLimits(entries=10, word_chars=12, spelling_chars=20)


def test_each_word_is_its_word_was_and_say_fields():
    fields = [
        ("word-2", "Lanyon"),
        ("say-2", "lanny on"),
        ("was-2", "lan yon"),
        ("word-1", "Utterson"),
        ("say-1", ""),
        ("was-x", "ignored"),
        ("other", "ignored"),
    ]
    assert sent_words(fields, 10) == [
        SentWord(1, "Utterson", "", None),  # no was-1: a form from before was-N
        SentWord(2, "Lanyon", "lanny on", "lan yon"),
    ]


def test_only_the_words_changed_on_the_page_are_asked_for():
    sent = [
        SentWord(1, "Utterson", "utter son", "utter son"),  # left as it was
        SentWord(2, "Lanyon", " lan  yon ", "lan yon"),  # only its spacing differs
        SentWord(3, "Poole", "pool", ""),  # given a spelling
        SentWord(4, "Hyde", "", "hide"),  # emptied: removed
        SentWord(5, "Enfield", "en field", None),  # a form that doesn't say: asked, as before
    ]
    changes = spellings_to_save(sent, LIMITS)
    assert changes.spellings == {"Poole": "pool", "Hyde": "", "Enfield": "en field"}
    assert changes.shown == {"Poole": "", "Hyde": "hide"}
    assert changes.errors == {}


def test_the_rules_for_new_words_apply_only_to_words_being_given_a_spelling():
    long = "Dr. Henry Jekyll"  # longer than LIMITS.word_chars
    sent = [
        SentWord(1, long, "doctor jekyll", "doctor jekyll"),  # left alone: no error
        SentWord(2, f" {long} ", "", "doctor jekyll"),  # removed: matched however long
        SentWord(3, "Mr. Edward Hyde", "mister hide", "mister hyde"),  # changed: checked
    ]
    changes = spellings_to_save(sent, LIMITS)
    assert changes.spellings == {long: ""}
    assert changes.errors == {
        "say-3": "Mr. Edward Hyde can't be saved: A word can be at most 12 characters long."
    }


def test_a_word_changed_elsewhere_keeps_what_was_typed_and_shows_its_new_spelling():
    sent = [
        SentWord(1, "Utterson", "otter son", "utter son"),
        SentWord(2, "Lanyon", "lanny on", "lan yon"),
        SentWord(3, "Poole", "pooh", "pool"),
    ]
    again, errors = changed_elsewhere(sent, {"UTTERSON": "utter sun", "Poole": ""})
    assert again == [
        SentWord(1, "Utterson", "otter son", "utter sun"),
        sent[1],
        SentWord(3, "Poole", "pooh", ""),
    ]
    assert errors == {
        "say-1": "Utterson was changed in another window since this page was opened. "
        "It now says: utter sun. Check it and save again.",
        "say-3": "Poole was changed in another window since this page was opened. "
        "It now has no spelling. Check it and save again.",
    }
