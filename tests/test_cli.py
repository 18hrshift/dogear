from pathlib import Path

import pytest

from dogear import cli
from dogear.document import (
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    Metadata,
    PageMarker,
    Paragraph,
    Section,
)


@pytest.fixture
def book(monkeypatch):
    book = Book(
        metadata=Metadata(title="Test Book", authors=["Ann Author"], language="en"),
        sections=[
            Section("Cover", kind="front", blocks=[Image(alt="A red door.")]),
            Section(
                "Chapter One",
                blocks=[
                    PageMarker("1"),
                    Heading(1, "Chapter One"),
                    Paragraph("Dr. Smith had 42 cats. They were loud.", note_refs=("n1",)),
                    ListBlock(("first", "second")),
                    PageMarker("2"),
                    Footnote("n1", "Some were kittens.", label="1"),
                ],
            ),
        ],
        source_path=Path("test.epub"),
        source_format="epub",
    )
    monkeypatch.setattr(cli, "extract_book", lambda path, config: book)
    return book


def test_outline_reads_as_sentences(book, capsys):
    assert cli.main(["outline", "test.epub"]) == 0
    out = capsys.readouterr().out
    assert "Title: Test Book\nBy: Ann Author\nLanguage: en\n" in out
    assert "EPUB file, 2 sections, 18 words." in out
    assert "1. Cover: front matter, 3 words, 1 image." in out
    assert "2. Chapter One: main text, 15 words, print pages 1 to 2, 1 note." in out


def test_text_shows_display_text(book, capsys):
    assert cli.main(["text", "test.epub", "--section", "2"]) == 0
    out = capsys.readouterr().out
    assert "Section 2: Chapter One" in out
    assert "[Print page 1]" in out
    assert "Dr. Smith had 42 cats. They were loud." in out
    assert "- first" in out
    assert "Note 1: Some were kittens." in out
    assert "Cover" not in out


def test_text_spoken_shows_one_normalized_sentence_per_line(book, capsys):
    assert cli.main(["text", "test.epub", "--spoken"]) == 0
    out = capsys.readouterr().out
    assert "Doctor Smith had forty-two cats.\nThey were loud.\n" in out
    assert "Image: A red door." in out


def test_bad_section_number_explains_the_fix(book, capsys):
    assert cli.main(["text", "test.epub", "--section", "9"]) == 1
    err = capsys.readouterr().err
    assert "Error: There is no section 9; this book has 2." in err
    assert "What to do: Run `dogear outline`" in err


def test_unsupported_file_is_a_friendly_error(tmp_path, capsys):
    notes = tmp_path / "notes.odt"
    notes.write_text("x")
    assert cli.main(["outline", str(notes)]) == 1
    err = capsys.readouterr().err
    assert "Error: Dogear can't read .odt files yet." in err
    assert "What to do: Supported formats:" in err


def test_config_flag_is_read(tmp_path, capsys):
    bad = tmp_path / "dogear.toml"
    bad.write_text("[pdf]\npage_split_size = 'ten'\n")
    assert cli.main(["outline", "x.pdf", "--config", str(bad)]) == 1
    assert "pdf.page_split_size' must be int" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit) as done:
        cli.main(["--version"])
    assert done.value.code == 0
    assert capsys.readouterr().out.startswith("dogear ")


def test_voices_lists_best_rated_first_and_marks_the_default(capsys):
    assert cli.main(["voices"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if ". " in line[:4]]
    assert lines[0] == (
        "1. af_heart: American English, female, grade A. This is the one Dogear uses now."
    )
    assert lines[1].startswith("2. af_bella: American English, female, grade A-.")
    assert lines[-1].endswith("grade F+.")
