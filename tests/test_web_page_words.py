"""The web page's own pronunciation file: checking words and spellings, saving them
whole, reading them back, keeping phoneme entries, and the [web] limits."""

import os
import stat

import pytest

from dogear.config import default_config
from dogear.errors import DogearError, PronunciationError
from dogear.pronunciations import load_dictionary, read_pronunciation_file
from dogear.web import page_words
from dogear.web.page_words import (
    EntryError,
    PageWords,
    clean_spelling,
    clean_word,
    words_option,
)
from dogear.web.settings import WordLimits, web_settings

LIMITS = WordLimits(entries=10, word_chars=20, spelling_chars=30)


@pytest.fixture
def words(tmp_path):
    return PageWords(tmp_path / "web" / "words.toml", LIMITS)


def saved(words: PageWords) -> list[tuple]:
    return [(e.word, e.sounds_like, e.phonemes) for e in read_pronunciation_file(words.path)]


def test_nothing_is_written_until_a_word_is_saved(words):
    assert words.entries() == []
    assert words_option(words.path) == []
    words.save({"Utterson": ""})  # removing a word that isn't there changes nothing
    assert not words.path.exists()
    words.save({"Utterson": "utter son"})
    assert words_option(words.path) == ["--words", str(words.path)]
    assert saved(words) == [("Utterson", "utter son", None)]


def test_quotes_backslashes_and_unicode_are_saved_as_typed(words):
    typed = {
        'The "Doctor"': 'the "doc"',
        "back\\slash": "back \\ slash",
        "Zoë": "zo ee",
        "日本": "nihon",
        "St. John": "sin jun",
    }
    words.save(typed)
    assert sorted(saved(words)) == sorted((w, s, None) for w, s in typed.items())
    # And the reader every `dogear` command uses finds them in text.
    dictionary = load_dictionary([words.path])
    assert dictionary.say_sounds_like('Zoë met The "Doctor".') == 'Zo ee met The "doc".'


def test_saving_changes_and_removes_entries_whatever_their_capitals(words):
    words.save({"Utterson": "utter son", "Poole": "pool"})
    words.save({"UTTERSON": "utter sun", "poole": ""})
    assert saved(words) == [("UTTERSON", "utter sun", None)]


def test_entries_are_listed_in_alphabetical_order(words):
    words.save({"poole": "pool", "Hyde": "hide", "Lanyon": "lan yon"})
    assert [e.word for e in words.entries()] == ["Hyde", "Lanyon", "poole"]


def test_phoneme_entries_written_by_hand_are_kept_unchanged(words):
    words.path.parent.mkdir(parents=True)
    words.path.write_text(
        '[words]\nLanyon = { phonemes = "lˈænjən" }\nHyde = "hide"\n', encoding="utf-8"
    )
    words.save({"Utterson": "utter son", "Hyde": "", "lanyon": ""})
    assert saved(words) == [("Lanyon", None, "lˈænjən"), ("Utterson", "utter son", None)]
    with pytest.raises(EntryError, match="Lanyon has exact phonemes") as error:
        words.save({"LANYON": "lan yon"})
    assert error.value.word == "LANYON"
    assert saved(words) == [("Lanyon", None, "lˈænjən"), ("Utterson", "utter son", None)]


def test_the_file_is_owner_only_and_read_back_before_it_replaces_the_old_one(words, monkeypatch):
    words.save({"Utterson": "utter son"})
    if os.name != "nt":
        assert stat.S_IMODE(words.path.stat().st_mode) == 0o600
    monkeypatch.setattr(
        page_words, "pronunciation_file_text", lambda entries, header: "[words]\nbroken = \n"
    )
    with pytest.raises(DogearError, match="didn't read back") as error:
        words.save({"Poole": "pool"})
    assert error.value.hint == page_words.BUG_HINT
    assert saved(words) == [("Utterson", "utter son", None)]
    assert [p.name for p in words.path.parent.iterdir()] == ["words.toml"]


def test_a_file_made_unreadable_by_hand_is_an_error_not_an_empty_list(words):
    words.path.parent.mkdir(parents=True)
    words.path.write_text("[words]\nUtterson = \n", encoding="utf-8")
    with pytest.raises(PronunciationError, match="not valid TOML"):
        words.entries()
    with pytest.raises(PronunciationError):
        words.save({"Poole": "pool"})


@pytest.mark.parametrize("text", ["Hyde\nJekyll", "Hyde\r", "nul\x00", "bell\x07", "\ud800"])
def test_line_breaks_and_control_characters_are_refused(text):
    with pytest.raises(EntryError, match="line breaks or other control characters"):
        clean_word(text, LIMITS)
    with pytest.raises(EntryError, match="line breaks or other control characters"):
        clean_spelling(text, "Hyde", LIMITS)


def test_words_and_spellings_are_tidied_and_checked():
    assert clean_word("  St.   John\t", LIMITS) == "St. John"
    assert clean_spelling("  utter\tson ", "Utterson", LIMITS) == "utter son"
    assert clean_spelling("   ", "Utterson", LIMITS) == ""
    with pytest.raises(EntryError, match="Type the word"):
        clean_word("  ", LIMITS)
    with pytest.raises(EntryError, match="at least one letter or number"):
        clean_word("--", LIMITS)


def test_the_limits_come_from_the_web_settings(tmp_path):
    config = default_config()
    config["web"]["dir"] = str(tmp_path)
    config["web"].update(max_pronunciations=2, max_word_chars=8, max_spelling_chars=9)
    limits = web_settings(config).word_limits
    assert clean_word("Utterson", limits) == "Utterson"
    with pytest.raises(EntryError, match="at most 8 characters"):
        clean_word("Uttersons", limits)
    assert clean_spelling("utter son", "Utterson", limits) == "utter son"
    with pytest.raises(EntryError, match="How to say Utterson can be at most 9 characters"):
        clean_spelling("utter sonn", "Utterson", limits)

    words = PageWords(tmp_path / "words.toml", limits)
    words.save({"Hyde": "hide", "Poole": "pool"})
    with pytest.raises(EntryError, match="holds at most 2 words") as error:
        words.save({"Lanyon": "lan yon", "Hyde": "hidey"})
    assert error.value.word == "Lanyon"
    assert len(words.entries()) == 2
    words.save({"Lanyon": "lan yon", "Hyde": ""})  # one out, one in: still 2
    assert [e.word for e in words.entries()] == ["Lanyon", "Poole"]


def test_the_limits_must_be_above_zero(tmp_path):
    config = default_config()
    config["web"]["max_word_chars"] = 0
    with pytest.raises(DogearError, match="web.max_word_chars must be more than 0"):
        web_settings(config)


def test_a_full_disk_is_a_plain_error(words, monkeypatch):
    def full(path, data, check=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(page_words, "write_atomically", full)
    with pytest.raises(DogearError, match="No space left on device") as error:
        words.save({"Hyde": "hide"})
    assert "disk" in error.value.hint
