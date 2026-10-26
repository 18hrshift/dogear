from pathlib import Path

import pytest

from dogear.document import (
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    Metadata,
    PageMarker,
    Paragraph,
    SceneBreak,
    Section,
    Table,
    block_text,
)


@pytest.mark.parametrize(
    "make",
    [
        lambda: Heading(0, "Title"),
        lambda: Heading(7, "Title"),
        lambda: Heading(1, "  "),
        lambda: Paragraph(""),
        lambda: ListBlock(()),
        lambda: ListBlock(("ok", " ")),
        lambda: Table(()),
        lambda: Table((("a",),), header_rows=2),
        lambda: Footnote("", "text"),
        lambda: PageMarker(""),
        lambda: Section(" "),
        lambda: Section("Title", kind="middle"),
    ],
)
def test_invalid_blocks_are_rejected(make):
    with pytest.raises(ValueError):
        make()


def test_block_text_for_every_kind():
    assert block_text(Heading(2, "Part")) == "Part"
    assert block_text(ListBlock(("a", "b"))) == "a\nb"
    assert block_text(Table((("h1", "h2"), ("c1", "c2")), caption="Cap")) == "Cap\nh1 h2\nc1 c2"
    assert block_text(Image(alt=None, caption="A map")) == "A map"
    assert block_text(Footnote("n1", "Note text")) == "Note text"
    assert block_text(PageMarker("xii")) == ""


def test_language_is_keyword_only():
    assert Paragraph("Bonjour", lang="fr").lang == "fr"
    with pytest.raises(TypeError):
        Paragraph("Bonjour", (), "fr")


def test_section_counts_and_pages():
    section = Section(
        "Chapter 1",
        blocks=[PageMarker("1"), Paragraph("One two three."), PageMarker("2"), Image(alt="")],
    )
    assert section.word_count() == 3
    assert section.page_labels() == ["1", "2"]


def test_slug():
    assert Section("Chapter One: The River!").slug(3) == "03_chapter_one_the_river"
    assert Section("***").slug(1) == "01_section"


def test_book_word_count():
    book = Book(
        Metadata(title="T"),
        [Section("A", blocks=[Paragraph("one two")]), Section("B", blocks=[Paragraph("three")])],
        Path("t.epub"),
        "epub",
    )
    assert book.word_count() == 3


def test_scene_break_has_no_words():
    assert block_text(SceneBreak()) == ""
    assert Section("S", blocks=[Paragraph("one"), SceneBreak()]).word_count() == 1
