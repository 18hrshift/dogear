"""Page numbers and running headers and footers, tested on hand-placed lines."""

import pytest
from pdf_lines import PITCH, body_lines, layout_for, ln

from dogear.extract.pdf_furniture import is_page_number, running_key, strip_furniture
from dogear.extract.pdf_text import Page


@pytest.fixture
def layout(config):
    return layout_for(config)


def never_label(text: str) -> bool:
    return False


def strip(pages, layout, *, is_label=never_label, min_pages=3, min_share=0.4, max_lines=2):
    cleaned = strip_furniture(
        pages,
        layout,
        is_label=is_label,
        min_pages=min_pages,
        min_share=min_share,
        max_lines=max_lines,
    )
    return [[line.text for line in page.lines] for page in cleaned]


@pytest.mark.parametrize("text", ["42", "7", "xii", "iv", "- 7 -", "[iv]", "(12)"])
def test_page_numbers(text):
    assert is_page_number(text)


@pytest.mark.parametrize("text", ["1865 was a hard year", "I", "XII", "mild", "Chapter 3", "12345"])
def test_not_page_numbers(text):
    assert not is_page_number(text)


def test_running_key_ignores_digits_case_and_edge_numerals():
    assert running_key("Page 12 of 300") == running_key("PAGE 13 OF 300") == "page # of #"
    assert running_key("xii   Preface") == running_key("xiii Preface") == "# preface"


def page_with_furniture(
    index: int, header: str | tuple[str, ...] | None, footer: str | tuple[str, ...] | None
) -> Page:
    """Five body lines, with header lines above them and footer lines below, 11 pt apart."""
    headers = (header,) if isinstance(header, str) else header or ()
    footers = (footer,) if isinstance(footer, str) else footer or ()
    lines = [ln(text, 30 + i * 11, size=9) for i, text in enumerate(headers)]
    lines += body_lines(72, 5, prefix=f"page {index}")
    lines += [ln(text, 740 + i * 11, size=9) for i, text in enumerate(footers)]
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


# Two-line running headers and footers


def chapter_of(index: int) -> str:
    return ("Down the Rabbit-Hole", "The Pool of Tears")[index // 4]


def test_two_line_header_removed(layout):
    # The book's title over the chapter's title: neither line is apart from the other,
    # but the pair is apart from the text.
    pages = [page_with_furniture(i, ("THE BOOK TITLE", chapter_of(i)), None) for i in range(8)]
    for kept in strip(pages, layout):
        assert all(text.startswith("page ") for text in kept)


def test_two_line_footer_removed(layout):
    pages = [page_with_furniture(i, None, (chapter_of(i), str(i + 1))) for i in range(8)]
    for kept in strip(pages, layout):
        assert all(text.startswith("page ") for text in kept)


def test_running_line_max_lines_is_the_depth(layout):
    pages = [page_with_furniture(i, ("THE BOOK TITLE", chapter_of(i)), None) for i in range(8)]
    for i, kept in enumerate(strip(pages, layout, max_lines=1)):
        assert kept[:2] == ["THE BOOK TITLE", chapter_of(i)]


ONE_LINERS = (
    "Alice was beginning to get very tired.",
    "So she was considering in her own mind.",
    "There was nothing so very remarkable in that.",
    "The rabbit-hole went straight on like a tunnel.",
    "Either the well was very deep, or she fell very slowly.",
    "Oh dear! Oh dear! I shall be late!",
)


def test_second_line_must_repeat_on_its_own(layout):
    # The second line is in the header block, but it changes on every page, so it is
    # kept: being next to a running line is not enough.
    pages = [page_with_furniture(i, ("THE BOOK TITLE", ONE_LINERS[i]), None) for i in range(6)]
    for i, kept in enumerate(strip(pages, layout)):
        assert kept[0] == ONE_LINERS[i]


def test_first_lines_of_text_are_not_eaten(layout):
    # A one-line header, then text that starts close under it. The first two text lines
    # are the same on every page (a refrain), but they are part of the text block.
    def page(i: int) -> Page:
        lines = (
            ln("THE BOOK TITLE", 40, size=9),
            ln("Down, down, down.", 72, x1=540),
            ln("Would the fall never come to an end?", 72 + PITCH, x1=540),
            *body_lines(72 + 2 * PITCH, 3, prefix=f"page {i}"),
        )
        return Page(i, str(i + 1), lines)

    for kept in strip([page(i) for i in range(6)], layout):
        assert kept[:2] == ["Down, down, down.", "Would the fall never come to an end?"]


def test_header_then_one_line_paragraph_keeps_the_paragraph(layout):
    # Gap-style text: a one-line paragraph right under the header is apart from the
    # text below it, so it is a candidate, but it doesn't repeat, so it stays.
    def page(i: int) -> Page:
        lines = (
            ln("THE BOOK TITLE", 40, size=9),
            ln(ONE_LINERS[i], 40 + PITCH),
            *body_lines(40 + 3 * PITCH, 3, prefix=f"page {i}"),
        )
        return Page(i, str(i + 1), lines)

    for i, kept in enumerate(strip([page(i) for i in range(6)], layout)):
        assert kept[0] == ONE_LINERS[i]
