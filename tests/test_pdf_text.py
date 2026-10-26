"""Page-text cleanup and paragraph rules, tested on hand-placed lines (no PDF needed)."""

import pytest

from dogear.extract.pdf_text import (
    Layout,
    Line,
    Page,
    body_size,
    continues,
    is_page_number,
    join_lines,
    leading_heading_lines,
    measure_layout,
    merge_drop_caps,
    running_key,
    split_paragraphs,
    strip_furniture,
)

BODY = 11.0
PITCH = 14.0
SOFT_HYPHEN = chr(0xAD)


def ln(text: str, top: float, *, x0: float = 72.0, size: float = BODY, x1: float = 0) -> Line:
    """A line whose box is as tall as its font size, like pdfplumber reports."""
    return Line(
        text=text,
        top=top,
        bottom=top + size,
        x0=x0,
        x1=x1 or x0 + 5.0 * len(text),
        size=size,
        chars=len(text.replace(" ", "")),
    )


def body_lines(start: float, count: int, prefix: str = "body") -> list[Line]:
    return [ln(f"{prefix} line {i} of the page", start + i * PITCH, x1=540) for i in range(count)]


@pytest.fixture
def layout(config):
    pdf = config["pdf"]
    return Layout(
        body_size=BODY,
        heading_size=BODY * pdf["heading_size_ratio"],
        line_pitch=PITCH,
        gap_ratio=pdf["paragraph_gap_ratio"],
        indent=BODY * pdf["paragraph_indent_ratio"],
    )


def never_label(text: str) -> bool:
    return False


def strip(pages, layout, *, is_label=never_label, min_pages=3, min_share=0.4):
    cleaned = strip_furniture(
        pages, layout, is_label=is_label, min_pages=min_pages, min_share=min_share
    )
    return [[line.text for line in page.lines] for page in cleaned]


# Page numbers and running lines


@pytest.mark.parametrize("text", ["42", "7", "xii", "iv", "- 7 -", "[iv]", "(12)"])
def test_page_numbers(text):
    assert is_page_number(text)


@pytest.mark.parametrize("text", ["1865 was a hard year", "I", "XII", "mild", "Chapter 3", "12345"])
def test_not_page_numbers(text):
    assert not is_page_number(text)


def test_running_key_ignores_digits_case_and_edge_numerals():
    assert running_key("Page 12 of 300") == running_key("PAGE 13 OF 300") == "page # of #"
    assert running_key("xii   Preface") == running_key("xiii Preface") == "# preface"


def page_with_furniture(index: int, header: str | None, footer: str | None) -> Page:
    lines = []
    if header:
        lines.append(ln(header, 40, size=9))
    lines += body_lines(72, 5, prefix=f"page {index}")
    if footer:
        lines.append(ln(footer, 750, size=9))
    return Page(index=index, label=str(index + 1), lines=tuple(lines))


def test_page_numbers_dropped_at_top_and_bottom_only(layout):
    page = Page(0, "1", (ln("7", 40), *body_lines(72, 2), ln("42", 100), ln("xii", 750)))
    [kept] = strip([page], layout)
    assert kept == ["body line 0 of the page", "body line 1 of the page", "42"]


def test_running_headers_and_footers_removed(layout):
    pages = [page_with_furniture(i, "THE BOOK TITLE", f"Page {i + 1} of 6") for i in range(6)]
    for kept in strip(pages, layout):
        assert len(kept) == 5
        assert all(text.startswith("page ") for text in kept)


def test_running_header_needs_min_pages(layout):
    pages = [page_with_furniture(i, "THE BOOK TITLE" if i < 2 else None, None) for i in range(6)]
    assert strip(pages, layout)[0][0] == "THE BOOK TITLE"
    assert strip(pages, layout, min_pages=2)[0][0] != "THE BOOK TITLE"


def test_running_header_needs_min_share(layout):
    # The same ornament opens pages 0, 10 and 20: 3 of 21 pages, so it is not a header.
    pages = [page_with_furniture(i, "* * *" if i % 10 == 0 else None, None) for i in range(21)]
    assert strip(pages, layout)[10][0] == "* * *"
    assert strip(pages, layout, min_share=0.1)[10][0] != "* * *"


def test_alternating_headers_removed(layout):
    pages = [
        page_with_furniture(i, "THE BOOK TITLE" if i % 2 else "A Chapter Title", None)
        for i in range(8)
    ]
    assert all(kept[0].startswith("page ") for kept in strip(pages, layout))


def test_repeated_prose_at_page_foot_is_kept(layout):
    # Same last line on every page, but it sits in the text block, not apart from it.
    pages = [
        Page(i, str(i + 1), (*body_lines(72, 3), ln("and the same last line", 72 + 3 * PITCH)))
        for i in range(5)
    ]
    assert all(kept[-1] == "and the same last line" for kept in strip(pages, layout))


def test_heading_type_never_removed(layout):
    pages = [
        Page(i, str(i + 1), (ln("Chapter Title", 40, size=22), *body_lines(90, 3)))
        for i in range(5)
    ]
    assert all(kept[0] == "Chapter Title" for kept in strip(pages, layout))


def test_label_running_header_keeps_its_first_appearance(layout):
    def is_label(text: str) -> bool:
        return text.startswith("Chapter")

    pages = [page_with_furniture(i, "Chapter 3" if i >= 2 else None, None) for i in range(7)]
    kept = strip(pages, layout, is_label=is_label)
    assert kept[2][0] == "Chapter 3"  # where chapter 3 opens
    assert all(page[0].startswith("page ") for page in kept[3:])


def test_numbered_labels_are_not_one_running_header(layout):
    # "Chapter 1", "Chapter 2", ... on every other page look alike once digits are
    # ignored, but labels are compared exactly, so every chapter keeps its opening.
    def is_label(text: str) -> bool:
        return text.startswith("Chapter")

    pages = [
        page_with_furniture(i, f"Chapter {i // 2 + 1}" if i % 2 == 0 else None, None)
        for i in range(8)
    ]
    kept = strip(pages, layout, is_label=is_label)
    assert [kept[i][0] for i in range(0, 8, 2)] == [f"Chapter {n}" for n in range(1, 5)]


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
    layout = measure_layout(pages, heading_ratio=2.0, gap_ratio=1.5, indent_ratio=1.0)
    assert (layout.heading_size, layout.indent, layout.line_pitch) == (22.0, 11.0, PITCH)
    assert layout.paragraph_gap == PITCH * 1.5
    assert pdf["heading_size_ratio"] != 2.0  # the call above used its own ratios


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
