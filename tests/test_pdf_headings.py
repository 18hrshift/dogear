"""Subheadings inside a section, tested on hand-placed lines."""

from dataclasses import replace

import pytest
from pdf_lines import PITCH, body_lines, layout_for, ln

from dogear.extract.pdf_headings import Run, find_subheadings, heading_levels, heading_style


@pytest.fixture
def layout(config):
    return layout_for(config)  # 11 pt body; subheadings from about 12.7 pt


def kinds(runs: list[Run]) -> list[tuple[str, int]]:
    """Each run as ("body" or "head", line count)."""
    return [("body" if run.style is None else "head", len(run.lines)) for run in runs]


def test_heading_styles(layout):
    assert heading_style(ln("The Pool of Tears", 0, size=14), layout) == (14, False)
    assert heading_style(ln("The Pool of Tears", 0, size=22), layout) == (22, False)
    assert heading_style(ln("The Pool of Tears", 0, bold=True), layout) == (11, True)
    assert heading_style(ln("The Pool of Tears", 0), layout) is None
    assert heading_style(ln("a small bold caption", 0, size=8, bold=True), layout) is None
    assert heading_style(ln("slightly larger", 0, size=12), layout) is None


def test_bold_is_not_a_heading_when_body_text_is_bold(layout):
    bold_book = replace(layout, body_bold=True)
    assert heading_style(ln("The Pool of Tears", 0, bold=True), bold_book) is None
    assert heading_style(ln("The Pool of Tears", 0, size=14, bold=True), bold_book) == (14, True)


def test_subheading_between_paragraphs(layout):
    lines = [
        *body_lines(72, 3, "a"),
        ln("The Pool of Tears", 72 + 4 * PITCH, size=14),
        *body_lines(72 + 6 * PITCH, 3, "b"),
    ]
    runs = find_subheadings(lines, layout)
    assert kinds(runs) == [("body", 3), ("head", 1), ("body", 3)]
    assert runs[1].lines[0].text == "The Pool of Tears"


def test_two_line_subheading(layout):
    lines = [
        ln("A Caucus-Race and", 72, size=14),
        ln("a Long Tale", 72 + 18, size=14),
        *body_lines(72 + 3 * PITCH, 2),
    ]
    assert kinds(find_subheadings(lines, layout)) == [("head", 2), ("body", 2)]


def test_long_bold_passage_is_body_text(layout):
    bold = [replace(line, bold=True) for line in body_lines(72 + 3 * PITCH, 4, "bold")]
    lines = [*body_lines(72, 3), *bold, *body_lines(72 + 7 * PITCH, 2)]
    assert kinds(find_subheadings(lines, layout)) == [("body", 9)]


def test_single_large_letter_is_not_a_heading(layout):
    lines = [*body_lines(72, 2), ln("I", 72 + 3 * PITCH, size=30), *body_lines(150, 2)]
    assert kinds(find_subheadings(lines, layout)) == [("body", 5)]


def test_heading_does_not_span_two_columns(layout):
    lines = [
        *body_lines(72, 3),
        ln("End of the left column", 120, size=14),
        replace(ln("Top of the right column", 72, size=14), flow=1),
    ]
    runs = find_subheadings(lines, layout)
    assert kinds(runs) == [("body", 3), ("head", 1), ("head", 1)]


def test_levels_ranked_largest_first_then_bold():
    styles = [(14.0, False), (11.0, True), (18.0, False), (14.0, True), (14.0, False)]
    assert heading_levels(styles) == {
        (18.0, False): 2,
        (14.0, True): 3,
        (14.0, False): 4,
        (11.0, True): 5,
    }


def test_levels_stop_at_six():
    levels = heading_levels((float(size), False) for size in range(12, 20))
    assert max(levels.values()) == 6
    assert levels[(19.0, False)] == 2
