"""`dogear ocr`, and what it shares with reading a scanned PDF by itself: reading one page
with Tesseract, the checks before it, and the progress sentences."""

import copy
import logging

import pdfplumber
import pytest
from conftest import require_tool
from pdf_builder import scanned_words
from PIL import Image
from test_ocr_cache import TESSERACT

from dogear import cli
from dogear.errors import (
    ConfigError,
    DogearError,
    ExtractionError,
    OcrLanguageError,
    ToolNotFoundError,
)
from dogear.ocr import default_output_path, ocr_pdf, page
from dogear.ocr.page import open_pdf, page_dpi
from dogear.ocr.progress import OcrProgress
from dogear.ocr.settings import OcrSettings
from dogear.ocr.tesseract import find_tesseract

WORDS = ["ACCESSIBLE BOOKS", "LISTEN CLOSELY"]


def text_of(path):
    with pdfplumber.open(str(path)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def images_of(path):
    with pdfplumber.open(str(path)) as pdf:
        return [len(page.images) for page in pdf.pages]


def test_ocr_adds_a_text_layer_over_each_page(tmp_path, config):
    require_tool("tesseract")
    scan = scanned_words(tmp_path / "scan.pdf", WORDS)
    assert all(not t.strip() for t in text_of(scan))

    lines = []
    out = tmp_path / "scan_ocr.pdf"
    assert ocr_pdf(scan, out, config, lines.append) == 2

    pages = text_of(out)
    assert len(pages) == 2
    for page_text, words in zip(pages, WORDS, strict=True):
        assert words in page_text.upper()
    assert images_of(out) == [1, 1]  # the pictures of the pages stay, under the text
    assert lines[0] == (
        "Reading the 2 pages of scan.pdf with OCR, which takes a while: often a few seconds a page."
    )
    assert lines[1].startswith("Read 1 of 2 pages with OCR.")
    assert lines[2] == "Finished reading 2 pages with OCR."


def test_the_ocr_command_saves_next_to_the_scan(tmp_path, capsys):
    require_tool("tesseract")
    scan = scanned_words(tmp_path / "scan.pdf", WORDS[:1])
    assert cli.main(["ocr", str(scan), "--dpi", "100"]) == 0
    out = tmp_path / "scan_ocr.pdf"
    assert WORDS[0] in text_of(out)[0].upper()
    assert f"Saved 1 page with a text layer to {out}" in capsys.readouterr().out


def test_refuses_to_overwrite_input(tmp_path, config):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4")
    with pytest.raises(DogearError, match="overwrite"):
        ocr_pdf(scan, scan, config, print)


def test_damaged_pdf_is_an_extraction_error(tmp_path, config):
    require_tool("tesseract")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ExtractionError, match="Couldn't open"):
        ocr_pdf(bad, tmp_path / "out.pdf", config, print)


def test_missing_tesseract_names_the_fix(tmp_path, config):
    custom = copy.deepcopy(config)
    custom["tools"]["tesseract"] = "no-such-tesseract"
    with pytest.raises(ToolNotFoundError) as err:
        ocr_pdf(tmp_path / "a.pdf", tmp_path / "b.pdf", custom, print)
    assert "no-such-tesseract" in err.value.message


def test_a_missing_language_pack_is_named_with_how_to_install_it(config):
    require_tool("tesseract")
    config["ocr"]["language"] = "eng+qqq"
    with pytest.raises(OcrLanguageError) as err:
        find_tesseract(config, OcrSettings.from_config(config))
    assert "language pack for 'qqq'" in err.value.message
    assert "sudo apt install tesseract-ocr-qqq" in err.value.hint
    assert "ocr.language" in err.value.hint


def test_the_installed_languages_pass(config):
    require_tool("tesseract")
    tesseract = find_tesseract(config, OcrSettings.from_config(config))
    assert tesseract.version.startswith("tesseract")


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("language", "eng; rm -rf", "Tesseract language codes"),
        ("language", "", "Tesseract language codes"),
        ("dpi", 50, "at least 70"),
        ("max_page_megapixels", 0, "more than 0"),
    ],
)
def test_ocr_settings_are_checked(config, key, value, message):
    config["ocr"][key] = value
    with pytest.raises(ConfigError, match=message):
        OcrSettings.from_config(config)


def test_a_huge_page_is_drawn_at_a_lower_resolution(config):
    settings = OcrSettings.from_config(config)
    letter = (612, 792)
    assert page_dpi(*letter, settings) == 300
    poster = (72 * 100, 72 * 100)  # 100 inches square
    assert page_dpi(*poster, settings) == 100  # 10,000 by 10,000 pixels
    config["ocr"]["max_page_megapixels"] = 2
    smaller = OcrSettings.from_config(config)
    assert smaller.max_page_pixels == 2_000_000
    assert page_dpi(*letter, smaller) == 146  # 1,241 by 1,606 pixels


def test_a_page_over_the_size_limit_is_read_at_the_lower_resolution(
    tmp_path, config, monkeypatch, caplog
):
    """ocr.max_page_megapixels decides how big a picture a page makes, and Tesseract is
    told the resolution it was drawn at, so the text lands where it is printed."""
    scan = scanned_words(tmp_path / "scan.pdf", ["ONE"], dpi=20)
    seen = []

    def read_image(tesseract, image, out_base, *, dpi, settings, text_only):
        with Image.open(image) as picture:
            seen.append((dpi, picture.size, picture.mode))
        made = out_base.with_suffix(".pdf")
        made.write_bytes(b"%PDF-1.4 stand-in")
        return made

    monkeypatch.setattr(page, "read_image", read_image)
    document = open_pdf(scan)
    try:
        for megapixels in (100, 2):
            config["ocr"]["max_page_megapixels"] = megapixels
            settings = OcrSettings.from_config(config)
            with caplog.at_level(logging.WARNING, logger="dogear.ocr.page"):
                page.ocr_page(
                    document, 0, tmp_path / "page.pdf", TESSERACT, settings, text_only=True
                )
    finally:
        document.close()
    assert seen == [(300, (2550, 3301), "L"), (146, (1241, 1606), "L")]
    assert caplog.messages == [
        "Page 1 is 8.5 by 11 inches, too big to read at 300 dpi, so it is read at 146 dpi."
    ]
    assert (tmp_path / "page.pdf").read_bytes() == b"%PDF-1.4 stand-in"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith("work-")] == []


def test_progress_comes_after_the_first_page_every_ten_and_at_the_end():
    lines = []
    now = [0.0]
    progress = OcrProgress(25, 0, lines.append, clock=lambda: now[0])
    for _ in range(25):
        now[0] += 6
        progress.page_done()
    assert lines == [
        "Read 1 of 25 pages with OCR. About 2 minutes left.",
        "Read 10 of 25 pages with OCR. About 2 minutes left.",
        "Read 20 of 25 pages with OCR. Less than a minute left.",
        "Finished reading 25 pages with OCR.",
    ]


def test_progress_counts_pages_read_before():
    lines = []
    now = [0.0]
    progress = OcrProgress(300, 120, lines.append, clock=lambda: now[0])
    now[0] += 4
    progress.page_done()
    assert lines == ["Read 121 of 300 pages with OCR. About 12 minutes left."]


def test_default_output_path(tmp_path):
    assert default_output_path(tmp_path / "My Book.pdf") == tmp_path / "My Book_ocr.pdf"
