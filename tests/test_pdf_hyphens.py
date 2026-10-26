"""Line-end hyphens decided by how the book spells words elsewhere."""

import pytest

from dogear.extract.pdf_hyphens import HyphenEvidence
from dogear.extract.pdf_text import join_lines

BOOK = [
    "whether the pleasure of making a daisy-chain would be worth the trouble",
    "The rabbit-hole went straight on like a tunnel for some way, and then",
    "so many out-of-the-way things had happened lately",
    "the Rabbit-Hole",  # case is ignored
    "and the trouble of exam-",  # a fragment, not evidence for either spelling
    "ple",
]


def evidence(*, min_count=1, keep_by_default=False, texts=BOOK):
    return HyphenEvidence.from_texts(texts, min_count=min_count, keep_by_default=keep_by_default)


def test_hyphenated_spelling_elsewhere_keeps_the_hyphen():
    assert evidence().keep("daisy", "chain")
    assert evidence().keep("out-of-the", "way")


def test_joined_spelling_elsewhere_drops_the_hyphen():
    assert not evidence(keep_by_default=True).keep("tun", "nel")


def test_more_frequent_spelling_wins():
    texts = ["a rabbit-hole", "a rabbithole", "a rabbithole"]
    assert not evidence(texts=texts).keep("rabbit", "hole")
    assert evidence(texts=[*texts, "rabbit-hole", "rabbit-hole"]).keep("rabbit", "hole")


@pytest.mark.parametrize("keep_by_default", [False, True])
def test_no_evidence_uses_the_default(keep_by_default):
    assert evidence(keep_by_default=keep_by_default).keep("remark", "able") is keep_by_default
    # The broken word itself is two fragments, so it is no evidence either.
    assert evidence(keep_by_default=keep_by_default).keep("exam", "ple") is keep_by_default


def test_a_tie_uses_the_default():
    texts = ["a rabbit-hole", "a rabbithole"]
    assert evidence(texts=texts, keep_by_default=True).keep("rabbit", "hole")
    assert not evidence(texts=texts, keep_by_default=False).keep("rabbit", "hole")


def test_min_count():
    assert evidence(min_count=1).keep("daisy", "chain")
    assert not evidence(min_count=2).keep("daisy", "chain")  # seen once: no evidence
    assert evidence(min_count=2).keep("rabbit", "hole")  # seen twice


def test_join_lines_asks_about_lowercase_continuations_only():
    asked = []

    def keep(left: str, right: str) -> bool:
        asked.append((left, right))
        return left in ("well", "out-of-the")

    assert join_lines(["a well-", "known tale"], keep) == "a well-known tale"
    assert join_lines(["an exam-", "ple of it"], keep) == "an example of it"
    assert join_lines(["many out-of-the-", "way things"], keep) == "many out-of-the-way things"
    assert join_lines(["an Anglo-", "Saxon king"], keep) == "an Anglo-Saxon king"
    assert asked == [("well", "known"), ("exam", "ple"), ("out-of-the", "way")]


def test_join_lines_without_a_rule_joins():
    assert join_lines(["a well-", "known tale"]) == "a wellknown tale"
