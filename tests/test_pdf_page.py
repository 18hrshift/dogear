"""Reading one pdfplumber page into lines."""

from collections import Counter

import pdfplumber
import pytest
from pdf_builder import ALICE, MARGIN, PdfBuilder, novel

from dogear.extract.pdf_page import ReadSettings, read_page

SETTINGS = ReadSettings(column_gap_ratio=0.8)


def read(path, settings=SETTINGS):
    with pdfplumber.open(path) as pdf:
        return [read_page(page, i, str(i + 1), settings) for i, page in enumerate(pdf.pages)]


@pytest.mark.parametrize("style", ["indent", "gap"])
def test_lines_match_pdfplumber_text_lines(tmp_path, style):
    # The reader rebuilds lines from pdfplumber's text map; they must be exactly what
    # `extract_text_lines` gives, so pages without columns read as they always have.
    path = novel(tmp_path / "n.pdf", style=style, front=["A title page."], back=["Notes"])
    with pdfplumber.open(path) as pdf:
        expected = []
        for page in pdf.pages:
            lines = []
            for raw in page.extract_text_lines(strip=True, return_chars=True):
                chars = [c for c in raw["chars"] if not c["text"].isspace()]
                size = Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
                box = (raw["top"], raw["bottom"], raw["x0"], raw["x1"])
                lines.append((" ".join(raw["text"].split()), *box, size, len(chars)))
            expected.append(lines)
    got = [
        [(ln.text, ln.top, ln.bottom, ln.x0, ln.x1, ln.size, ln.chars) for ln in page.lines]
        for page in read(path)
    ]
    assert got == expected


def test_wide_gap_cuts_a_line_into_parts(tmp_path):
    pdf = PdfBuilder(tmp_path / "parts.pdf")
    pdf.line("the left column")
    pdf.space(-14)
    pdf.line("the right column", x=MARGIN + 250)
    pdf.paragraph(ALICE[0])
    [page] = read(pdf.save())
    first = page.lines[0]
    assert first.text == "the left column the right column"
    assert [part.text for part in first.parts] == ["the left column", "the right column"]
    assert first.parts[1].x0 == pytest.approx(MARGIN + 250)
    assert all(not line.parts for line in page.lines[1:])  # ordinary word spaces


def test_column_gap_ratio_sets_where_lines_are_cut(tmp_path):
    pdf = PdfBuilder(tmp_path / "parts.pdf")
    pdf.line("the left column")
    pdf.space(-14)
    pdf.line("the right column", x=MARGIN + 150)  # a gap of about 7 times the type size
    path = pdf.save()
    [page] = read(path)
    assert len(page.lines[0].parts) == 2
    [page] = read(path, ReadSettings(column_gap_ratio=8.0))
    assert page.lines[0].parts == ()
