import pytest

from dogear.output.languages import iso639_2


@pytest.mark.parametrize(
    ("tag", "code"),
    [
        ("en", "eng"),
        ("EN-gb", "eng"),
        ("fr_CA", "fra"),
        ("de", "deu"),  # the terminology code, not the bibliographic "ger"
        ("zh-Hant-TW", "zho"),
        ("deu", "deu"),
        ("haw", "haw"),  # no two-letter code; three letters pass through
    ],
)
def test_known_languages(tag, code):
    assert iso639_2(tag) == code


@pytest.mark.parametrize("tag", [None, "", "und", "mul", "x-pirate", "qq", "e1g", "english"])
def test_missing_or_unusable_tags_give_none(tag):
    assert iso639_2(tag) is None
