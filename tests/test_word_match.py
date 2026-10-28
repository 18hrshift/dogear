"""Finding dictionary words in text: whole words, any case, possessives, longest first."""

import pytest

from dogear.speech.word_match import WordMatcher


def found(words: list[str], text: str) -> list[tuple[str, str, str]]:
    """(the word that matched, the text it covered, its possessive) for each match."""
    return [
        (words[m.index], text[m.start : m.end], m.possessive)
        for m in WordMatcher(words).finditer(text)
    ]


@pytest.mark.parametrize(
    "text",
    ["Utterson came.", "UTTERSON came.", "utterson came.", "(Utterson)", "'Utterson,' he said."],
)
def test_whole_words_in_any_case(text):
    assert [w for w, _, _ in found(["Utterson"], text)] == ["Utterson"]


@pytest.mark.parametrize(
    "text",
    [
        "Uttersons came.",  # a plural is another word
        "Lutterson came.",
        "Utterson2 came.",
        "The Uttersons' house.",
        "Mr. O'Utterson came.",  # after a letter and an apostrophe, as in O'Brien
    ],
)
def test_never_inside_another_word(text):
    assert found(["Utterson"], text) == []


@pytest.mark.parametrize("apostrophe", ["'", "’"])
def test_possessives_match_and_are_reported(apostrophe):
    text = f"Utterson{apostrophe}s house"
    assert found(["Utterson"], text) == [("Utterson", f"Utterson{apostrophe}s", f"{apostrophe}s")]


def test_a_word_followed_by_a_closing_quote_is_not_possessive():
    assert found(["Utterson"], "'Utterson' said") == [("Utterson", "Utterson", "")]


def test_either_apostrophe_matches_either():
    assert found(["O'Brien"], "O’Brien came") == [("O'Brien", "O’Brien", "")]
    assert found(["O’Brien"], "O'Brien came") == [("O’Brien", "O'Brien", "")]


def test_hyphenated_compounds_hold_separate_words():
    assert [w for w, _, _ in found(["Jekyll", "Hyde"], "the Jekyll-Hyde affair")] == [
        "Jekyll",
        "Hyde",
    ]


@pytest.mark.parametrize("text", ["St. John left.", "St.  John left.", "St.\nJohn left."])
def test_several_words_match_across_any_spacing(text):
    assert found(["St. John"], text) == [("St. John", text[: text.index("n ") + 1], "")]


def test_the_longest_entry_wins():
    words = ["John", "St. John", "Hyde", "Hyde Park"]
    text = "St. John walked in Hyde Park with John Hyde."
    assert [w for w, _, _ in found(words, text)] == ["St. John", "Hyde Park", "John", "Hyde"]


def test_a_longer_entry_that_doesnt_fit_falls_back_to_a_shorter_one():
    assert [w for w, _, _ in found(["John", "John Smith"], "John Smithers")] == ["John"]


def test_words_with_regex_characters_are_taken_literally():
    assert found(["C++", "a.b"], "I like C++ and a.b, not axb.") == [
        ("C++", "C++", ""),
        ("a.b", "a.b", ""),
    ]


def test_sub_replaces_only_the_matches():
    matcher = WordMatcher(["Utterson", "Poole"])
    text = "Utterson's man Poole met Utterson."
    swapped = matcher.sub(text, lambda m: f"<{m.index}{m.possessive}>")
    assert swapped == "<0's> man <1> met <0>."


def test_no_words_finds_nothing():
    matcher = WordMatcher([])
    assert list(matcher.finditer("Anything at all.")) == []
    assert matcher.sub("Anything at all.", lambda m: "x") == "Anything at all."


def test_many_words():
    words = [f"Name{n}x" for n in range(3000)] + ["Lanyon"]
    assert found(words, "Lanyon met Name2999x.") == [
        ("Lanyon", "Lanyon", ""),
        ("Name2999x", "Name2999x", ""),
    ]
