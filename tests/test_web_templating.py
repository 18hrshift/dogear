"""Values printed in a page lose the characters HTML doesn't allow, and nothing else."""

from markupsafe import Markup

from dogear.web.templating import REPLACEMENT, fit_for_html


def test_control_characters_become_the_replacement_character():
    assert fit_for_html("pool\x00 side\x1b\x7f\x85") == f"pool{REPLACEMENT} side{REPLACEMENT * 3}"


def test_whitespace_html_allows_is_kept():
    assert fit_for_html("a\tb\nc\x0cd\re") == "a\tb\nc\x0cd\re"


def test_surrogates_and_noncharacters_are_replaced():
    text = "x\ud800y﷐z￾\U0001ffff\U0010ffff"
    assert fit_for_html(text) == "x" + REPLACEMENT + "y" + REPLACEMENT + "z" + REPLACEMENT * 3


def test_other_text_is_unchanged():
    text = "Utterson, Ⅳ, 東京, émigré, \U0001f4d6, �"
    assert fit_for_html(text) == text


def test_markup_stays_markup_so_it_isnt_escaped_again():
    made = fit_for_html(Markup("<b>Bold\x00</b>"))
    assert isinstance(made, Markup)
    assert str(made) == f"<b>Bold{REPLACEMENT}</b>"


def test_values_that_arent_text_pass_through():
    assert fit_for_html(42) == 42
    assert fit_for_html(None) is None
