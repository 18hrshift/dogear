"""Images in PDFs: which count as figures, where they are read, and their captions."""

import logging

import pytest
from pdf_builder import (
    ALICE,
    CHAPTER_TITLES,
    INDENT,
    LEADING,
    MARGIN,
    TEXT_WIDTH,
    PdfBuilder,
    wrap,
)
from pdf_lines import layout_for, ln

from dogear.document import Image, PageMarker, Paragraph
from dogear.extract.pdf import extract
from dogear.extract.pdf_figures import is_caption_start

CAPTION = f"Figure 1. {CHAPTER_TITLES[0]}"


def blocks(path, config):
    [section] = extract(path, config).sections
    return section.blocks


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("Figure 3. The White Rabbit", 11),
        ("Fig. 3: The White Rabbit", 11),
        ("Plate IV — The Pool of Tears", 11),
        ("FIGURE 12a. The Pool of Tears", 11),
        ("Figure 3 The White Rabbit", 9),  # no punctuation, but not body type
        ("Illustration 2", 9),
    ],
)
def test_caption_starts(config, text, size):
    assert is_caption_start(ln(text, 0, size=size), layout_for(config))


@pytest.mark.parametrize(
    "text", ["Figure 3 shows the White Rabbit", "Figures of speech", "A figure. 3", "Plate"]
)
def test_not_caption_starts(config, text):
    assert not is_caption_start(ln(text, 0), layout_for(config))


def test_image_between_paragraphs(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "fig.pdf")
    pdf.paragraph(ALICE[0])
    pdf.figure()
    pdf.paragraph(ALICE[1])
    assert blocks(pdf.save(), config) == [
        PageMarker("1"),
        Paragraph(ALICE[0]),
        Image(alt=None),
        Paragraph(ALICE[1]),
    ]


def test_caption_below_is_attached_and_not_read_twice(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "fig.pdf")
    pdf.paragraph(ALICE[0])
    pdf.figure(caption=CAPTION)
    pdf.paragraph(ALICE[1])
    assert blocks(pdf.save(), config) == [
        PageMarker("1"),
        Paragraph(ALICE[0]),
        Image(alt=None, caption=CAPTION),
        Paragraph(ALICE[1]),
    ]


def test_caption_above_is_attached(tmp_path, config):
    caption = f"Plate I: {CHAPTER_TITLES[1]}"  # body size, so it needs the colon
    pdf = PdfBuilder(tmp_path / "fig.pdf")
    pdf.paragraph(ALICE[0])
    pdf.space(LEADING)  # set apart from the text above, as captions are
    pdf.line(caption, x=MARGIN)
    pdf.figure()
    pdf.paragraph(ALICE[1])
    assert blocks(pdf.save(), config) == [
        PageMarker("1"),
        Paragraph(ALICE[0]),
        Image(alt=None, caption=caption),
        Paragraph(ALICE[1]),
    ]


def test_text_that_isnt_a_caption_stays_a_paragraph(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "fig.pdf")
    pdf.figure()
    pdf.paragraph(ALICE[1])
    assert blocks(pdf.save(), config) == [PageMarker("1"), Image(alt=None), Paragraph(ALICE[1])]


def test_figure_inside_a_paragraph_comes_after_it(tmp_path, config):
    lines = wrap(ALICE[3], [TEXT_WIDTH - INDENT])
    pdf = PdfBuilder(tmp_path / "fig.pdf")
    pdf.line(lines[0], x=MARGIN + INDENT)
    pdf.line(lines[1])
    pdf.figure()
    for line in lines[2:]:
        pdf.line(line)
    pdf.paragraph(ALICE[4])
    assert blocks(pdf.save(), config) == [
        PageMarker("1"),
        Paragraph(ALICE[3]),
        Image(alt=None),
        Paragraph(ALICE[4]),
    ]


def test_small_images_are_decoration(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "ornament.pdf")
    pdf.paragraph(ALICE[0])
    pdf.figure(24, 24)  # an ornament: about a fifth of a percent of the page
    pdf.paragraph(ALICE[1])
    path = pdf.save()
    assert Image(alt=None) not in blocks(path, config)
    config["pdf"]["image_min_page_share"] = 0.001
    assert Image(alt=None) in blocks(path, config)


def test_image_under_text_is_not_a_figure(tmp_path, config):
    # A page background, or a scanned page under its text layer.
    pdf = PdfBuilder(tmp_path / "background.pdf")
    pdf.image()
    for text in ALICE:
        pdf.paragraph(text)
    assert not any(isinstance(b, Image) for b in blocks(pdf.save(), config))


def test_picture_page_before_the_first_chapter_is_kept(tmp_path, config, caplog):
    pdf = PdfBuilder(tmp_path / "frontispiece.pdf")
    pdf.image()
    pdf.new_page()
    for title in CHAPTER_TITLES[:2]:
        pdf.heading(title)
        pdf.paragraph(ALICE[0])
        pdf.new_page()
    with caplog.at_level(logging.WARNING):
        book = extract(pdf.save(), config)
    front = book.sections[0]
    assert (front.title, front.kind) == ("Front matter", "front")
    assert front.blocks == [PageMarker("1"), Image(alt=None)]
