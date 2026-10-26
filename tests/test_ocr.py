import copy

import pdfplumber
import pypdfium2
import pytest
from conftest import require_tool
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from dogear.errors import DogearError, ExtractionError, ToolNotFoundError
from dogear.ocr import default_output_path, ocr_pdf

WORDS = ["ACCESSIBLE BOOKS", "LISTEN CLOSELY"]


def scanned_pdf(path, pages):
    """A PDF whose pages are only images of text, like a scanner makes."""
    text_pdf = path.with_name("source.pdf")
    c = canvas.Canvas(str(text_pdf), pagesize=letter)
    c.setTitle("Scanned Test")
    for words in pages:
        c.setFont("Helvetica-Bold", 36)
        c.drawString(72, 600, words)
        c.showPage()
    c.save()
    images = []
    with pypdfium2.PdfDocument(str(text_pdf)) as doc:
        for page in doc:
            images.append(page.render(scale=200 / 72).to_pil().convert("RGB"))
    images[0].save(path, "PDF", resolution=200, save_all=True, append_images=images[1:])
    return path


def text_of(path):
    with pdfplumber.open(str(path)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def test_ocr_adds_text_layer_and_keeps_pages(tmp_path, config):
    require_tool("tesseract")
    scan = scanned_pdf(tmp_path / "scan.pdf", WORDS)
    assert all(not t.strip() for t in text_of(scan))

    seen = []
    out = tmp_path / "scan_ocr.pdf"
    assert ocr_pdf(scan, out, config, progress=lambda done, total: seen.append((done, total))) == 2

    pages = text_of(out)
    assert len(pages) == 2
    for page_text, words in zip(pages, WORDS, strict=True):
        assert words in page_text.upper()
    assert seen == [(1, 2), (2, 2)]


def test_refuses_to_overwrite_input(tmp_path, config):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4")
    with pytest.raises(DogearError, match="overwrite"):
        ocr_pdf(scan, scan, config)


def test_damaged_pdf_is_an_extraction_error(tmp_path, config):
    require_tool("tesseract")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ExtractionError, match="Couldn't open"):
        ocr_pdf(bad, tmp_path / "out.pdf", config)


def test_missing_tesseract_names_the_fix(tmp_path, config):
    custom = copy.deepcopy(config)
    custom["tools"]["tesseract"] = "no-such-tesseract"
    with pytest.raises(ToolNotFoundError) as err:
        ocr_pdf(tmp_path / "a.pdf", tmp_path / "b.pdf", custom)
    assert "no-such-tesseract" in err.value.message


def test_default_output_path(tmp_path):
    assert default_output_path(tmp_path / "My Book.pdf") == tmp_path / "My Book_ocr.pdf"
