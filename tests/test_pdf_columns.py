"""Pages set in columns: hand-placed rows for the rules, then PDFs end to end."""

from dataclasses import replace

import pytest
from pdf_builder import ALICE, INDENT, PdfBuilder, alice, wrap
from pdf_lines import PITCH, ln

from dogear.document import Paragraph
from dogear.extract.pdf import extract
from dogear.extract.pdf_columns import ColumnRules, order_columns
from dogear.extract.pdf_text import Line, Page, merge_lines

LEFT, RIGHT = 72.0, 318.0  # where two columns start
WIDTH = 222.0  # their width


@pytest.fixture
def rules(config):
    pdf = config["pdf"]
    return ColumnRules(
        pdf["column_gap_ratio"], pdf["column_min_lines"], pdf["column_min_width_ratio"]
    )


def row(top: float, *pieces: tuple[str, float, float]) -> Line:
    """A row as read: (text, x0, x1) pieces, cut into parts if there is more than one."""
    parts = tuple(ln(text, top, x0=x0, x1=x1) for text, x0, x1 in pieces)
    return parts[0] if len(parts) == 1 else replace(merge_lines(parts), parts=parts)


def texts(page: Page) -> list[str]:
    return [line.text for line in page.lines]


def flows(page: Page) -> list[int]:
    return [line.flow for line in page.lines]


def two_columns(start: float, count: int) -> list[Line]:
    """Rows holding a line of each column, as pdfplumber reads aligned columns."""
    return [
        row(start + i * PITCH, (f"left {i}", LEFT, LEFT + WIDTH), (f"right {i}", RIGHT, 540))
        for i in range(count)
    ]


def test_aligned_columns_read_left_then_right(rules):
    page = Page(0, "1", tuple(two_columns(72, 4)))
    ordered = order_columns(page, rules)
    assert texts(ordered) == [f"left {i}" for i in range(4)] + [f"right {i}" for i in range(4)]
    assert flows(ordered) == [0] * 4 + [1] * 4
    assert [line.seq for line in ordered.lines] == list(range(8))


def test_columns_that_dont_line_up(rules):
    # Each column's lines sit between the other's, so every row holds one column's line.
    lines = []
    for i in range(4):
        lines.append(row(72 + i * PITCH, (f"left {i}", LEFT, LEFT + WIDTH)))
        lines.append(row(79 + i * PITCH, (f"right {i}", RIGHT, 540)))
    ordered = order_columns(Page(0, "1", tuple(lines)), rules)
    assert texts(ordered) == [f"left {i}" for i in range(4)] + [f"right {i}" for i in range(4)]


def test_full_width_lines_stay_where_they_are(rules):
    title = ln("A title across both columns", 40, x0=200, x1=420)
    note = ln("a full-width line below the columns, read last", 200, x1=540)
    page = Page(0, "1", (title, *two_columns(72, 4), note))
    ordered = order_columns(page, rules)
    assert texts(ordered) == [
        title.text,
        *[f"left {i}" for i in range(4)],
        *[f"right {i}" for i in range(4)],
        note.text,
    ]
    assert flows(ordered) == [0, 1, 1, 1, 1, 2, 2, 2, 2, 3]


def test_short_last_line_of_full_width_text_joins_the_left_column(rules):
    # It doesn't cross the gutter, so it is read as the left column's first line, which
    # is still the right order.
    lines = (
        ln("a full-width paragraph that runs across the page", 40, x1=540),
        ln("and ends here.", 54, x1=150),
        *two_columns(72, 4),
    )
    ordered = order_columns(Page(0, "1", lines), rules)
    assert texts(ordered)[:3] == [lines[0].text, "and ends here.", "left 0"]


def test_three_columns(rules):
    starts = {"one": 72.0, "two": 226.0, "three": 380.0}
    lines = [
        row(72 + i * PITCH, *((f"{name} {i}", x0, x0 + 130) for name, x0 in starts.items()))
        for i in range(4)
    ]
    ordered = order_columns(Page(0, "1", tuple(lines)), rules)
    assert texts(ordered) == [f"{name} {i}" for name in ("one", "two", "three") for i in range(4)]
    assert flows(ordered) == [0] * 4 + [1] * 4 + [2] * 4


def test_single_column_page_is_unchanged(rules):
    lines = tuple(ln(f"line {i} of the page", 72 + i * PITCH, x1=540) for i in range(10))
    ordered = order_columns(Page(0, "1", lines), rules)
    assert texts(ordered) == [line.text for line in lines]
    assert flows(ordered) == [0] * 10


def test_contents_page_numbers_stay_beside_their_titles(rules):
    # Page numbers down the right make a column too narrow to be one.
    titles = ["Down the Rabbit-Hole", "The Pool of Tears", "A Caucus-Race and a Long Tale"]
    lines = tuple(
        row(72 + i * PITCH, (title, LEFT, 200), (str(1 + 8 * i), 530, 540))
        for i, title in enumerate(titles)
    )
    ordered = order_columns(Page(0, "1", lines), rules)
    assert texts(ordered) == [line.text for line in lines]


def test_column_min_lines(rules):
    page = Page(0, "1", tuple(two_columns(72, 3)))
    assert texts(order_columns(page, rules))[1] == "left 1"
    more = ColumnRules(rules.gap_ratio, 4, rules.min_width_ratio)
    assert texts(order_columns(page, more))[1] == "left 1 right 1"  # rows as read


def test_column_min_width_ratio(rules):
    page = Page(0, "1", tuple(two_columns(72, 4)))
    wider = ColumnRules(rules.gap_ratio, rules.min_lines, WIDTH / 11 + 1)
    assert texts(order_columns(page, wider))[1] == "left 1 right 1"


def test_column_gap_ratio(rules):
    page = Page(0, "1", tuple(two_columns(72, 4)))  # a 24 pt gutter
    wider = ColumnRules(30 / 11, rules.min_lines, rules.min_width_ratio)
    assert texts(order_columns(page, wider))[1] == "left 1 right 1"


# End to end


def page_with_columns(path, **options):
    """A full-width paragraph, two columns of two paragraphs each, and another full-width
    paragraph."""
    pdf = PdfBuilder(path)
    pdf.paragraph(ALICE[0])
    pdf.columns([ALICE[1:3], ALICE[3:5]], **options)
    pdf.paragraph(ALICE[2])
    return pdf.save()


def all_paragraphs(book) -> list[str]:
    return [b.text for s in book.sections for b in s.blocks if isinstance(b, Paragraph)]


@pytest.mark.parametrize("drop", [0, 7])
def test_two_columns_between_full_width_text(tmp_path, config, drop):
    book = extract(page_with_columns(tmp_path / "c.pdf", drop=drop), config)
    assert all_paragraphs(book) == [ALICE[0], *ALICE[1:5], ALICE[2]]


def test_paragraph_carried_from_one_column_to_the_next(tmp_path, config):
    lines = wrap(ALICE[3], [PdfBuilder.column_width(2) - INDENT], PdfBuilder.column_width(2))
    assert not lines[2].endswith(".")
    head, tail = " ".join(lines[:3]), " ".join(lines[3:])
    pdf = PdfBuilder(tmp_path / "carried.pdf")
    pdf.columns([[ALICE[1], head], [tail, ALICE[4]]], carried=True)
    assert all_paragraphs(extract(pdf.save(), config)) == [ALICE[1], ALICE[3], ALICE[4]]


def test_three_columns_end_to_end(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "three.pdf")
    pdf.columns([alice(2), alice(2, start=2), alice(1, start=4)], gutter=18)
    assert all_paragraphs(extract(pdf.save(), config)) == alice(5)


def test_contents_page_read_row_by_row(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "contents.pdf")
    entries = [
        ("Down the Rabbit-Hole", "1"),
        ("The Pool of Tears", "9"),
        ("A Caucus-Race and a Long Tale", "17"),
        ("The Rabbit Sends in a Little Bill", "25"),
    ]
    for title, number in entries:
        pdf.line(title)
        pdf.space(-14)  # back up: the number goes on the same line, at the right margin
        pdf.line(number, x=530)
    [found] = all_paragraphs(extract(pdf.save(), config))
    assert found == " ".join(f"{title} {number}" for title, number in entries)


@pytest.mark.parametrize(
    ("key", "value"),
    [("column_gap_ratio", 3.0), ("column_min_lines", 20), ("column_min_width_ratio", 25.0)],
)
def test_column_settings_come_from_config(tmp_path, config, key, value):
    path = page_with_columns(tmp_path / "c.pdf")
    config["pdf"][key] = value  # the 24 pt gutter, 5 to 9 lines, 222 pt columns fall short
    assert all_paragraphs(extract(path, config)) != [ALICE[0], *ALICE[1:5], ALICE[2]]
