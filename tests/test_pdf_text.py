"""Page-text cleanup and paragraph rules, tested on hand-placed lines (no PDF needed)."""

from dataclasses import replace

import pytest
from pdf_lines import BODY, PITCH, body_lines, layout_for, ln

from dogear.extract.pdf_text import (
    Line,
    Page,
    body_size,
    continues,
    join_lines,
    leading_heading_lines,
    measure_layout,
    merge_drop_caps,
    split_paragraphs,
)

SOFT_HYPHEN = chr(0xAD)


@pytest.fixture
def layout(config):
    return layout_for(config)


# Joining lines


def test_hyphenation_rejoined():
    assert join_lines(["the beauti-", "ful garden"]) == "the beautiful garden"


def test_hyphen_kept_before_capital_or_digit():
    assert join_lines(["an Anglo-", "Saxon king"]) == "an Anglo-Saxon king"
    assert join_lines(["the pre-", "1914 world"]) == "the pre-1914 world"


def test_dashes_and_plain_lines():
    assert join_lines(["one word -", "and the next"]) == "one word - and the next"
    assert join_lines(["and then—", "she fell"]) == "and then—she fell"
    assert join_lines(["a mid-line hyphen stays", "as it was"]) == (
        "a mid-line hyphen stays as it was"
    )


def test_soft_hyphens_removed():
    assert join_lines([f"beauti{SOFT_HYPHEN}", "ful"]) == "beautiful"
    assert join_lines([f"an in{SOFT_HYPHEN}visible break"]) == "an invisible break"


def test_whitespace_collapsed():
    assert join_lines(["  spaced   out ", "", "words  "]) == "spaced out words"


# Paragraphs


def texts(page_text):
    return [[line.text for line in group] for group in page_text.paragraphs]


def test_paragraphs_split_by_gap(layout):
    lines = [*body_lines(72, 3, "a"), *body_lines(72 + 3 * PITCH + PITCH, 2, "b")]
    assert [len(group) for group in split_paragraphs(lines, layout).paragraphs] == [3, 2]


def test_paragraphs_split_by_indent(layout):
    lines = [
        ln("first paragraph opens indented", 72, x0=90, x1=540),
        ln("and runs on at the margin", 86, x1=540),
        ln("to a short end.", 100, x1=200),
        ln("second paragraph opens indented", 114, x0=90, x1=540),
        ln("and runs on.", 128, x1=200),
    ]
    result = split_paragraphs(lines, layout)
    assert [len(group) for group in result.paragraphs] == [3, 2]
    assert result.indented_start


def test_one_line_dialogue_paragraphs(layout):
    lines = [
        ln("the end of a paragraph from the last page, which fills the line", 72, x1=540),
        ln("“Yes,” he said.", 86, x0=90, x1=170),
        ln("“No,” she said.", 100, x0=90, x1=165),
        ln("“Why not?” asked Alice.", 114, x0=90, x1=200),
    ]
    assert len(split_paragraphs(lines, layout).paragraphs) == 4


def test_indented_quotation_stays_together(layout):
    lines = [
        ln("He read aloud from the letter:", 72, x1=540),
        ln("a quoted passage set in from the margin", 86, x0=108, x1=504),
        ln("that keeps the same indent on each line", 100, x0=108, x1=504),
        ln("until it ends.", 114, x0=108, x1=300),
    ]
    assert [len(group) for group in split_paragraphs(lines, layout).paragraphs] == [1, 3]


def test_size_change_splits(layout):
    lines = [*body_lines(72, 2), ln("a footnote in small type", 72 + 2 * PITCH, size=8)]
    assert [len(group) for group in split_paragraphs(lines, layout).paragraphs] == [2, 1]


def page_text(layout, *lines):
    return split_paragraphs(list(lines), layout)


def test_continues_without_terminal_punctuation(layout):
    previous = (ln("and then", 700, x1=540),)
    assert continues(previous, page_text(layout, ln("dipped down.", 72, x1=540)), layout)


def test_does_not_continue_after_a_full_stop(layout):
    previous = (ln("she fell.", 700, x1=540),)
    assert not continues(previous, page_text(layout, ln("Down she went.", 72, x1=540)), layout)


def test_lowercase_start_continues_after_an_abbreviation(layout):
    previous = (ln("said Mrs.", 700, x1=540),)
    assert continues(previous, page_text(layout, ln("smith quietly.", 72, x1=540)), layout)


def test_indented_page_start_does_not_continue(layout):
    previous = (ln("and then", 700, x1=540),)
    nxt = page_text(layout, ln("A new one.", 72, x0=90, x1=540), ln("more", 86, x1=540))
    assert not continues(previous, nxt, layout)


def test_size_change_does_not_continue(layout):
    previous = (ln("and then", 700, x1=540),)
    assert not continues(previous, page_text(layout, ln("small", 72, size=8)), layout)


# Measuring and headings


def test_body_size_weighted_by_characters():
    page = Page(
        0,
        "1",
        (
            ln("A Big Title", 40, size=22),
            ln("Sub", 70, size=16),
            ln("x" * 200, 100),
        ),
    )
    assert body_size([page]) == BODY


def test_measure_layout_uses_config_ratios(config):
    pages = [Page(0, "1", tuple(body_lines(72, 5)))]
    pdf = config["pdf"]
    layout = measure_layout(
        pages, heading_ratio=2.0, subheading_ratio=1.5, gap_ratio=1.5, indent_ratio=1.0
    )
    assert (layout.heading_size, layout.indent, layout.line_pitch) == (22.0, 11.0, PITCH)
    assert layout.subheading_size == 16.5
    assert layout.paragraph_gap == PITCH * 1.5
    assert not layout.body_bold
    assert pdf["heading_size_ratio"] != 2.0  # the call above used its own ratios


def test_body_bold_measured():
    pages = [Page(0, "1", tuple(replace(line, bold=True) for line in body_lines(72, 5)))]
    layout = measure_layout(
        pages, heading_ratio=2.0, subheading_ratio=1.5, gap_ratio=1.5, indent_ratio=1.0
    )
    assert layout.body_bold


def test_leading_heading_lines(layout):
    two_line = [
        ln("A Very Long", 40, size=22),
        ln("Chapter Title", 70, size=22),
        *body_lines(110, 2),
    ]
    assert leading_heading_lines(two_line, layout) == 2
    assert leading_heading_lines(body_lines(72, 2), layout) == 0
    # A single large letter is a drop cap or an ornament, not a heading.
    assert leading_heading_lines([ln("A", 40, size=40), *body_lines(72, 2)], layout) == 0


def test_drop_cap_joins_its_word():
    # Positions as pdfplumber reports a 40 pt "A" beside the first three 11 pt lines.
    lines = [
        Line("Down the Rabbit-Hole", 104.7, 126.7, 72.0, 272.4, 22.0, 18),
        Line("lice was beginning to get very tired", 155.3, 166.3, 104.0, 331.9, 11.0, 30),
        Line("A", 160.6, 200.6, 72.0, 100.9, 40.0, 1),
        Line("sister on the bank, and of having", 169.3, 180.3, 104.0, 335.3, 11.0, 27),
        Line("or twice she had peeped into the", 183.3, 194.3, 104.0, 333.1, 11.0, 26),
        Line("reading, but it had no pictures", 197.3, 208.3, 72.0, 387.9, 11.0, 26),
    ]
    merged = merge_drop_caps(lines)
    assert [line.text for line in merged] == [
        "Down the Rabbit-Hole",
        "Alice was beginning to get very tired",
        "sister on the bank, and of having",
        "or twice she had peeped into the",
        "reading, but it had no pictures",
    ]
    assert {line.x0 for line in merged} == {72.0}


def test_large_numeral_heading_is_not_a_drop_cap():
    lines = [ln("I", 40, size=30), *body_lines(90, 3)]
    assert merge_drop_caps(lines) == tuple(lines)
