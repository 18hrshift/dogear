"""A talking book's identifier and narrator."""

import re

from dogear.document import Metadata
from dogear.output.book_identity import book_uid, narrator


def test_the_same_book_always_gets_the_same_uid():
    one = book_uid(Metadata("Dr Jekyll", authors=["R. L. Stevenson"], identifier="isbn:1"))
    again = book_uid(Metadata("Dr Jekyll", authors=["R. L. Stevenson"], identifier="isbn:1"))
    assert one == again
    assert re.fullmatch(r"urn:uuid:[0-9a-f-]{36}", one)


def test_different_books_get_different_uids():
    base = Metadata("Dr Jekyll", authors=["R. L. Stevenson"])
    assert book_uid(base) != book_uid(Metadata("Dr Jekyll", authors=["Someone Else"]))
    assert book_uid(base) != book_uid(
        Metadata("Dr Jekyll", authors=["R. L. Stevenson"], identifier="x")
    )


def test_the_narrator_is_the_configured_voice(config):
    config["voice"]["voice"] = "bf_emma"
    assert narrator(config) == "bf_emma, a synthetic Kokoro voice"
