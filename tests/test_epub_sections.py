"""Sections built from the table of contents. Text is from Lewis Carroll's *Alice's
Adventures in Wonderland* (Project Gutenberg #11, public domain in the US)."""

import logging
from pathlib import Path

import pytest
from epub_builder import Doc, Toc, build_epub

from dogear.config import load_config
from dogear.document import Book, Footnote, Heading, Image, PageMarker, Paragraph, block_text
from dogear.errors import ConfigError
from dogear.extract.epub import extract

LOGGER = "dogear.extract.epub_sections"


def read(tmp_path: Path, config, docs: list[Doc], **kwargs) -> Book:
    return extract(build_epub(tmp_path / "book.epub", docs, **kwargs), config)


def outline(book: Book) -> list[tuple[str, str, str]]:
    return [(s.title, s.kind, s.source) for s in book.sections]


def texts(book: Book) -> list[list[str]]:
    return [[block_text(b) for b in s.blocks if block_text(b)] for s in book.sections]


def with_depth(tmp_path: Path, depth: int):
    path = tmp_path / f"depth{depth}.toml"
    path.write_text(f"[epub]\ntoc_depth = {depth}\n")
    return load_config(path)


# A chapter split across files


def test_chapter_split_across_files_is_one_section(tmp_path, config):
    docs = [
        Doc("ch1_split_000.xhtml", "<h2>Down the Rabbit-Hole</h2><p>Alice was beginning</p>"),
        Doc("ch1_split_001.xhtml", "<p>to get very tired</p>"),
        Doc("ch1_split_002.xhtml", "<p>of sitting by her sister.</p>"),
        Doc("ch2.xhtml", "<h2>The Pool of Tears</h2><p>Curiouser and curiouser!</p>"),
    ]
    toc = [Toc("ch1_split_000.xhtml", "I. Down the Rabbit-Hole"), Toc("ch2.xhtml", "II")]
    book = read(tmp_path, config, docs, toc=toc)
    assert outline(book) == [
        (
            "I. Down the Rabbit-Hole",
            "body",
            "OEBPS/ch1_split_000.xhtml to OEBPS/ch1_split_002.xhtml",
        ),
        ("II", "body", "OEBPS/ch2.xhtml"),
    ]
    assert texts(book)[0] == [
        "Down the Rabbit-Hole",
        "Alice was beginning",
        "to get very tired",
        "of sitting by her sister.",
    ]


def test_epub2_ncx_joins_split_files_too(tmp_path, config):
    docs = [
        Doc("a_split_000.xhtml", "<p>Alice was beginning</p>", toc_title="Chapter I"),
        Doc("a_split_001.xhtml", "<p>to get very tired.</p>"),
        Doc("b.xhtml", "<p>Curiouser and curiouser!</p>", toc_title="Chapter II"),
    ]
    book = read(tmp_path, config, docs, nav=False, ncx=True)
    assert [s.title for s in book.sections] == ["Chapter I", "Chapter II"]
    assert texts(book)[0] == ["Alice was beginning", "to get very tired."]


# Several chapters in one file


BOOK_FILE = """
<p>Project front matter.</p>
<section id="c1" epub:type="chapter"><h2>Chapter I</h2><p>Alice was beginning.</p>
  <p>She had a noteref<a epub:type="noteref" href="#n1">1</a> here.</p>
  <span epub:type="pagebreak" title="5"/></section>
<section id="c2" epub:type="chapter"><h2>Chapter II</h2><p>Curiouser and curiouser!
  <a id="c3"/>The White Rabbit returned.</p></section>
<section id="appx" epub:type="appendix"><h2>Notes</h2>
  <aside epub:type="footnote" id="n1"><p>A note.</p></aside></section>
"""


def test_several_chapters_in_one_file_are_cut_at_their_anchors(tmp_path, config, caplog):
    toc = [
        Toc("book.xhtml#c1", "Chapter I"),
        Toc("book.xhtml#c2", "Chapter II"),
        Toc("book.xhtml#c3", "Chapter III"),
        Toc("book.xhtml#appx", "Notes"),
    ]
    with caplog.at_level(logging.WARNING):
        book = read(tmp_path, config, [Doc("book.xhtml", BOOK_FILE)], toc=toc)
    assert outline(book) == [
        ("Section 1", "front", "OEBPS/book.xhtml"),  # before the first entry
        ("Chapter I", "body", "OEBPS/book.xhtml#c1"),
        ("Chapter II", "body", "OEBPS/book.xhtml#c2"),
        ("Chapter III", "body", "OEBPS/book.xhtml#c3"),  # starts mid-paragraph
        ("Notes", "back", "OEBPS/book.xhtml#appx"),  # each part classified on its own
    ]
    first, ch1, ch2, ch3, notes = book.sections
    assert first.blocks == [Paragraph("Project front matter.")]
    assert ch2.blocks == [
        PageMarker("5"),  # the page begins with Chapter II, not at the end of Chapter I
        Heading(2, "Chapter II"),
        Paragraph("Curiouser and curiouser!"),
    ]
    assert ch3.blocks == [Paragraph("The White Rabbit returned.")]
    # Notes are still linked across the cut.
    assert ch1.blocks[-1] == Paragraph(
        "She had a noteref here.", note_refs=("OEBPS/book.xhtml#n1",)
    )
    assert notes.blocks[-1] == Footnote("OEBPS/book.xhtml#n1", "A note.", label="1")
    assert not caplog.records


def test_anchor_inside_a_heading(tmp_path, config):
    body = '<h2><a id="c1"/>Chapter I</h2><p>One.</p><h2><a id="c2"/>Chapter II</h2><p>Two.</p>'
    toc = [Toc("book.xhtml#c1", "I"), Toc("book.xhtml#c2", "II")]
    book = read(tmp_path, config, [Doc("book.xhtml", body)], toc=toc)
    assert texts(book) == [["Chapter I", "One."], ["Chapter II", "Two."]]


def test_missing_anchor_starts_at_the_top_of_its_file(tmp_path, config, caplog):
    docs = [Doc("ch1.xhtml", "<p>One.</p>"), Doc("ch2.xhtml", "<p>Two.</p>")]
    toc = [Toc("ch1.xhtml", "I"), Toc("ch2.xhtml#gone", "II")]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, docs, toc=toc)
    assert outline(book) == [("I", "body", "OEBPS/ch1.xhtml"), ("II", "body", "OEBPS/ch2.xhtml")]
    assert any("#gone" in r.message for r in caplog.records)


# Nested tables of contents


NESTED_DOCS = [
    Doc("part1.xhtml", "<h1>Part One</h1><p>Who in the world am I?</p>"),
    Doc("ch1.xhtml", "<h2>Chapter 1</h2><p>Alice was beginning.</p>"),
    Doc("ch2.xhtml", "<h2>Chapter 2</h2><p>Curiouser and curiouser!</p>"),
    Doc(
        "part2.xhtml",
        '<section id="p2"><h1>Part Two</h1></section>'
        '<section id="c3"><h2>Chapter 3</h2><p>A Caucus-Race.</p></section>',
    ),
]
NESTED_TOC = [
    Toc("part1.xhtml", "Part One", [Toc("ch1.xhtml", "Chapter 1"), Toc("ch2.xhtml", "Chapter 2")]),
    Toc("part2.xhtml#p2", "Part Two", [Toc("part2.xhtml#c3", "Chapter 3")]),
]


@pytest.mark.parametrize("epub2", [False, True])
def test_nested_toc_gives_chapter_tracks_and_short_part_tracks(tmp_path, config, epub2):
    book = read(tmp_path, config, NESTED_DOCS, toc=NESTED_TOC, nav=not epub2, ncx=epub2)
    assert [s.title for s in book.sections] == [
        "Part One",
        "Chapter 1",
        "Chapter 2",
        "Part Two",
        "Chapter 3",
    ]
    assert texts(book)[0] == ["Part One", "Who in the world am I?"]  # the Part's own page
    assert texts(book)[3] == ["Part Two"]


def test_toc_depth_setting_changes_the_sections(tmp_path):
    def titles(depth: int) -> list[str]:
        book = read(tmp_path, with_depth(tmp_path, depth), NESTED_DOCS, toc=NESTED_TOC)
        return [s.title for s in book.sections]

    assert titles(1) == ["Part One", "Part Two"]  # chapters stay inside their Part
    assert titles(2) == ["Part One", "Chapter 1", "Chapter 2", "Part Two", "Chapter 3"]
    assert titles(0) == ["Part One", "Chapter 1", "Chapter 2", "Part Two"]  # one per file
    one_level = read(tmp_path, with_depth(tmp_path, 1), NESTED_DOCS, toc=NESTED_TOC)
    assert texts(one_level)[0][-1] == "Curiouser and curiouser!"


def test_toc_depth_must_not_be_negative(tmp_path):
    path = build_epub(tmp_path / "book.epub", [Doc("ch1.xhtml", "<p>T.</p>")])
    with pytest.raises(ConfigError, match="toc_depth"):
        extract(path, with_depth(tmp_path, -1))


def test_unlinked_toc_heading_does_not_add_a_level(tmp_path, config):
    nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="intro.xhtml">Introduction</a></li>
  <li><span>Part One</span><ol>
  <li><a href="ch1.xhtml">Chapter 1</a><ol><li><a href="ch1.xhtml#s">Section</a></li></ol></li>
  <li><a href="ch2.xhtml">Chapter 2</a></li></ol></li></ol></nav></body></html>"""
    docs = [
        Doc("intro.xhtml", "<p>Intro.</p>"),
        Doc("ch1.xhtml", '<p>One.</p><p id="s">Section.</p>'),
        Doc("ch2.xhtml", "<p>Two.</p>"),
    ]
    book = extract(
        build_epub(tmp_path / "book.epub", docs, files={"OEBPS/nav.xhtml": nav}),
        with_depth(tmp_path, 1),
    )
    assert [s.title for s in book.sections] == ["Introduction", "Chapter 1", "Chapter 2"]
    assert texts(book)[1] == ["One.", "Section."]


def test_part_and_chapter_at_the_same_place_take_the_chapter_title(tmp_path, config):
    docs = [Doc("ch1.xhtml", "<h1>Part One</h1><h2>Chapter 1</h2><p>Alice.</p>")]
    toc = [Toc("ch1.xhtml", "Part One", [Toc("ch1.xhtml", "Chapter 1")])]
    book = read(tmp_path, config, docs, toc=toc)
    assert [s.title for s in book.sections] == ["Chapter 1"]
    assert texts(book) == [["Part One", "Chapter 1", "Alice."]]


# Content the table of contents doesn't cover


def test_uncovered_content_is_kept_and_attached(tmp_path, config):
    docs = [
        Doc("cover.xhtml", '<img src="cover.jpg" alt="Cover"/>'),
        Doc("title.xhtml", "<h1>Alice in Wonderland</h1>"),
        Doc("ch1.xhtml", "<p>Alice was beginning.</p>", toc_title="Chapter I"),
        Doc("ch1b.xhtml", "<p>So she was considering.</p>"),
        Doc("ch2.xhtml", "<p>Curiouser and curiouser!</p>", toc_title="Chapter II"),
        Doc("colophon.xhtml", "<p>Set in Caslon.</p>", body_attrs='epub:type="backmatter"'),
        Doc("license.xhtml", "<p>Public domain.</p>"),
        Doc("popup.xhtml", "<p>A map.</p>", linear=False),
    ]
    book = read(tmp_path, config, docs)
    assert outline(book) == [
        ("Section 1", "front", "OEBPS/cover.xhtml"),  # before the first entry: front matter
        ("Alice in Wonderland", "front", "OEBPS/title.xhtml"),
        ("Chapter I", "body", "OEBPS/ch1.xhtml to OEBPS/ch1b.xhtml"),  # continues the chapter
        ("Chapter II", "body", "OEBPS/ch2.xhtml"),
        ("Section 5", "back", "OEBPS/colophon.xhtml to OEBPS/license.xhtml"),  # other matter
        ("Section 6", "back", "OEBPS/popup.xhtml"),  # non-linear, after the main text
    ]
    assert book.sections[0].blocks == [Image(alt="Cover")]
    assert texts(book)[2] == ["Alice was beginning.", "So she was considering."]
    assert texts(book)[4] == ["Set in Caslon.", "Public domain."]


def test_unlisted_file_opening_with_a_chapter_heading_starts_a_section(tmp_path, config):
    docs = [
        Doc("ch1.xhtml", "<h2>Chapter I</h2><p>Alice was beginning.</p>", toc_title="I"),
        Doc("ch1b.xhtml", "<h3>The Bottle</h3><p>Drink me.</p>"),  # a split at a subheading
        Doc("ch2.xhtml", "<h2>Chapter II</h2><p>Curiouser!</p>"),  # missing from the contents
        Doc("ch3.xhtml", "<h2>Chapter III</h2><p>A Caucus-Race.</p>", toc_title="III"),
    ]
    book = read(tmp_path, config, docs)
    assert outline(book) == [
        ("I", "body", "OEBPS/ch1.xhtml to OEBPS/ch1b.xhtml"),
        ("Chapter II", "body", "OEBPS/ch2.xhtml"),
        ("III", "body", "OEBPS/ch3.xhtml"),
    ]


def test_a_lone_start_entry_does_not_swallow_the_book(tmp_path, config):
    docs = [
        Doc("ch1.xhtml", "<h2>Chapter I</h2><p>Alice was beginning.</p>", toc_title="Start"),
        Doc("ch2.xhtml", "<h2>Chapter II</h2><p>Curiouser!</p>"),
        Doc("ch3.xhtml", "<h2>Chapter III</h2><p>A Caucus-Race.</p>"),
    ]
    book = read(tmp_path, config, docs)
    assert [s.title for s in book.sections] == ["Start", "Chapter II", "Chapter III"]


def test_continuing_file_in_another_language_keeps_its_language(tmp_path, config):
    docs = [
        Doc("ch1.xhtml", "<p>Alice was beginning.</p>", toc_title="Chapter I"),
        Doc(
            "ch1b.xhtml",
            '<p>Où est ma chatte?</p><p xml:lang="en">said Alice.</p>',
            html_attrs='xml:lang="fr"',
        ),
    ]
    [section] = read(tmp_path, config, docs, language="en").sections
    assert section.lang == "en"
    assert section.blocks == [
        Paragraph("Alice was beginning."),
        Paragraph("Où est ma chatte?", lang="fr"),
        Paragraph("said Alice."),
    ]


# Falling back to one section per file


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"nav": False}, "no table of contents"),
        ({}, "no table of contents entries"),  # an empty toc nav
        ({"toc": [Toc("elsewhere.xhtml", "Elsewhere")]}, "doesn't point into its reading order"),
    ],
)
def test_no_usable_toc_falls_back_to_one_section_per_file(
    tmp_path, config, caplog, kwargs, message
):
    docs = [Doc("a.xhtml", "<p>A.</p>"), Doc("b.xhtml", "<p>B.</p>")]
    with caplog.at_level(logging.INFO, logger="dogear.extract"):
        book = read(tmp_path, config, docs, **kwargs)
    assert [s.source for s in book.sections] == ["OEBPS/a.xhtml", "OEBPS/b.xhtml"]
    assert any(message in r.message and r.levelno == logging.INFO for r in caplog.records), [
        r.message for r in caplog.records
    ]
