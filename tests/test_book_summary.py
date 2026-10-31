"""A book's summary, its JSON, and reading that JSON back with every field checked."""

import json
from dataclasses import replace

import pytest

from dogear.book_summary import (
    BookSummary,
    SectionSummary,
    describe_section,
    summary_from_json,
    summary_to_json,
)


def summary() -> BookSummary:
    return BookSummary(
        title="A Book",
        authors=("Ann Author", "Bob Writer"),
        language="en",
        source_format="epub",
        words=2_522,
        sections=(
            SectionSummary(1, "Title Page", "front", 12, None, None, 1, 0, 0),
            SectionSummary(2, "Story of the Door", "body", 2_510, "1", "12", 0, 1, 2),
        ),
    )


def test_json_reads_back_the_same():
    assert summary_from_json(json.loads(json.dumps(summary_to_json(summary())))) == summary()


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("title"),
        lambda d: d.update(words="many"),
        lambda d: d.update(words=-1),
        lambda d: d.update(authors=[1]),
        lambda d: d.update(language=5),
        lambda d: d["sections"][0].update(kind="middle"),
        lambda d: d["sections"][0].update(number=2),
        lambda d: d["sections"][0].update(images=True),
        lambda d: d["sections"][0].pop("last_page"),
        lambda d: d.update(sections="none"),
        lambda d: d.update(sections=["x"]),
    ],
)
def test_json_with_a_wrong_field_is_refused(change):
    data = summary_to_json(summary())
    change(data)
    with pytest.raises(ValueError):
        summary_from_json(data)


def test_a_section_is_described_the_way_outline_prints_it():
    one, two = summary().sections
    assert describe_section(one) == "Title Page: front matter, 12 words, 1 image."
    assert describe_section(two) == (
        "Story of the Door: main text, 2,510 words, print pages 1 to 12, 1 note, 2 tables."
    )
    assert describe_section(replace(two, last_page="1")) == (
        "Story of the Door: main text, 2,510 words, print page 1, 1 note, 2 tables."
    )
