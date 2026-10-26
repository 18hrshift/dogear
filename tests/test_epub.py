import logging
import time
import zipfile
from pathlib import Path

import pytest
from epub_builder import Doc, build_epub, container_xml, encryption_xml, xhtml

from dogear.config import load_config
from dogear.document import (
    Block,
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    PageMarker,
    Paragraph,
    SceneBreak,
    Table,
    block_text,
)
from dogear.errors import ConfigError, ExtractionError
from dogear.extract import extract_book
from dogear.extract.epub import extract
from dogear.extract.safe_xml import html_entities_to_numeric, parse_xml
from dogear.extract.xhtml import resolve_href

FIXTURES = Path(__file__).parent / "fixtures"
JEKYLL = FIXTURES / "robert-louis-stevenson_the-strange-case-of-dr-jekyll-and-mr-hyde.epub"


def read(tmp_path: Path, config, docs: list[Doc], **kwargs) -> Book:
    return extract(build_epub(tmp_path / "book.epub", docs, **kwargs), config)


def blocks(tmp_path: Path, config, body: str, **doc_kwargs) -> list[Block]:
    book = read(tmp_path, config, [Doc("ch1.xhtml", body, **doc_kwargs)])
    assert len(book.sections) == 1
    return book.sections[0].blocks


def all_text(book: Book) -> str:
    parts = [book.metadata.title, *book.metadata.authors]
    for section in book.sections:
        parts.append(section.title)
        parts += [block_text(b) for b in section.blocks]
    return "\n".join(parts)


# Metadata


def test_metadata(tmp_path, config):
    book = read(
        tmp_path,
        config,
        [Doc("ch1.xhtml", "<p>Text.</p>")],
        title="A Tale",
        creators=["Ada Writer", "Bo Coauthor"],
        language="en-GB",
        identifiers=[("isbn", "978-0-00-000000-0"), ("bookid", "urn:uuid:1234")],
        unique_identifier="bookid",
        publisher="Small Press",
    )
    meta = book.metadata
    assert meta.title == "A Tale"
    assert meta.authors == ["Ada Writer", "Bo Coauthor"]
    assert meta.language == "en-GB"
    assert meta.identifier == "urn:uuid:1234"  # the one unique-identifier names, not the first
    assert meta.publisher == "Small Press"
    assert book.source_format == "epub"
    assert book.sections[0].source == "OEBPS/ch1.xhtml"


def test_title_falls_back_to_file_stem(tmp_path, config):
    path = build_epub(tmp_path / "my-book.epub", [Doc("ch1.xhtml", "<p>Text.</p>")], title=None)
    assert extract(path, config).metadata.title == "my-book"


def test_extract_book_dispatches_epub(tmp_path, config):
    path = build_epub(tmp_path / "book.EPUB", [Doc("ch1.xhtml", "<p>Text.</p>")])
    book = extract_book(path, config)
    assert book.source_path == path
    assert book.sections[0].blocks == [Paragraph("Text.")]


# Reading order


def test_spine_order_with_non_linear_documents_last(tmp_path, config, caplog):
    docs = [
        Doc("a.xhtml", "<h1>A</h1>"),
        Doc("b.xhtml", "<h1>B</h1>"),
        Doc("popup.xhtml", "<h1>Popup</h1>", linear=False),
        Doc("map.xhtml", "<h1>Map</h1>", linear=False, body_attrs='epub:type="frontmatter"'),
    ]
    with caplog.at_level(logging.INFO, logger="dogear.extract.epub"):
        book = read(tmp_path, config, docs, spine=["doc3", "doc2", "doc4", "doc1"])
    assert [(s.title, s.kind) for s in book.sections] == [
        ("B", "body"),
        ("A", "body"),
        ("Popup", "back"),  # non-linear documents default to back matter...
        ("Map", "front"),  # ...unless the usual rules say otherwise
    ]
    added = [r.message for r in caplog.records if "after the main text" in r.message]
    assert len(added) == 2 and "popup.xhtml" in added[0]
    assert all(r.levelno == logging.INFO for r in caplog.records if "popup" in r.message)


def test_nav_document_is_skipped_as_content(tmp_path, config, caplog):
    with caplog.at_level(logging.INFO, logger="dogear.extract.epub"):
        book = read(tmp_path, config, [Doc("ch1.xhtml", "<p>Text.</p>")], nav_in_spine=True)
    assert [s.source for s in book.sections] == ["OEBPS/ch1.xhtml"]
    assert any("navigation document" in r.message for r in caplog.records)


def test_non_xhtml_spine_item_is_skipped_with_warning(tmp_path, config, caplog):
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><title>Cover</title></svg>'
    docs = [Doc("cover.svg", media_type="image/svg+xml", raw=svg), Doc("ch1.xhtml", "<p>T.</p>")]
    with caplog.at_level(logging.WARNING):
        book = read(tmp_path, config, docs)
    assert len(book.sections) == 1
    assert any("cover.svg" in r.message for r in caplog.records)


def test_url_encoded_hrefs(tmp_path, config):
    docs = [Doc("text/chapter one.xhtml", "<p>Text.</p>", toc_title="Chapter One")]
    book = read(tmp_path, config, docs)
    assert book.sections[0].source == "OEBPS/text/chapter one.xhtml"
    assert book.sections[0].title == "Chapter One"


def test_missing_spine_file_is_an_error(tmp_path, config):
    docs = [Doc("ch1.xhtml", "<p>T.</p>"), Doc("ch2.xhtml", missing=True)]
    with pytest.raises(ExtractionError, match="ch2.xhtml") as e:
        read(tmp_path, config, docs)
    assert e.value.hint


def test_href_escaping_the_archive_counts_as_missing(tmp_path, config):
    docs = [Doc("ch1.xhtml", "<p>T.</p>"), Doc("../../outside.xhtml", missing=True)]
    with pytest.raises(ExtractionError, match="missing"):
        read(tmp_path, config, docs)


def test_unknown_spine_idref_is_an_error(tmp_path, config):
    with pytest.raises(ExtractionError, match="ghost"):
        read(tmp_path, config, [Doc("ch1.xhtml", "<p>T.</p>")], spine=["doc1", "ghost"])


def test_empty_sections_are_skipped_and_image_only_cover_is_kept(tmp_path, config):
    docs = [
        Doc("cover.xhtml", '<img src="cover.jpg" alt="Cover"/>', body_attrs='epub:type="cover"'),
        Doc("blank.xhtml", "<div> </div><p>&nbsp;</p>"),
        Doc("ch1.xhtml", "<p>Text.</p>"),
    ]
    book = read(tmp_path, config, docs)
    assert [s.source for s in book.sections] == ["OEBPS/cover.xhtml", "OEBPS/ch1.xhtml"]
    cover = book.sections[0]
    assert cover.kind == "front"
    assert cover.blocks == [Image(alt="Cover")]
    assert cover.title == "Section 1"


def test_book_with_no_text_is_an_error(tmp_path, config):
    with pytest.raises(ExtractionError, match="no readable text"):
        read(tmp_path, config, [Doc("a.xhtml", "<div></div>"), Doc("b.xhtml", "  ")])


# Titles


def test_title_from_toc_then_first_heading_then_number(tmp_path, config):
    docs = [
        Doc("a.xhtml", "<h1>Heading A</h1><p>A.</p>", toc_title="Contents Title"),
        Doc("b.xhtml", "<p>B.</p><h2>Chapter II<br/>The Road</h2>"),
        Doc("c.xhtml", "<p>C.</p>"),
    ]
    book = read(tmp_path, config, docs)
    assert [s.title for s in book.sections] == [
        "Contents Title",
        "Chapter II The Road",
        "Section 3",
    ]
    assert book.sections[1].blocks[1] == Heading(2, "Chapter II\nThe Road")


def test_epub2_ncx_titles_and_page_list(tmp_path, config):
    docs = [
        Doc("text/ch1.xhtml", '<p>One <span id="pg3"/>two.</p>', toc_title="First"),
        Doc("text/ch2.xhtml", "<p>Two.</p>", toc_title="Second"),
    ]
    book = read(
        tmp_path, config, docs, nav=False, ncx=True, page_list=[("text/ch1.xhtml", "pg3", "3")]
    )
    assert [s.title for s in book.sections] == ["First", "Second"]
    assert book.sections[0].blocks == [PageMarker("3"), Paragraph("One two.")]


def test_unreadable_toc_falls_back_to_headings_with_warning(tmp_path, config, caplog):
    path = build_epub(
        tmp_path / "book.epub",
        [Doc("ch1.xhtml", "<h1>Heading</h1>", toc_title="Toc Title")],
        files={"OEBPS/nav.xhtml": "<html><body><nav>broken"},
    )
    with caplog.at_level(logging.WARNING):
        book = extract(path, config)
    assert book.sections[0].title == "Heading"
    assert any("nav.xhtml" in r.message for r in caplog.records)


# Section kinds


@pytest.mark.parametrize(
    ("body_attrs", "body", "landmark", "kind"),
    [
        ("", "<p>T.</p>", None, "body"),
        ('epub:type="frontmatter"', "<p>T.</p>", None, "front"),
        ('epub:type="backmatter"', "<p>T.</p>", None, "back"),
        ("", '<section epub:type="frontmatter preface"><p>T.</p></section>', None, "front"),
        ("", "<p>T.</p>", "backmatter", "back"),
        ("", "<p>T.</p>", "toc", "front"),
        ('epub:type="dedication"', "<p>T.</p>", None, "front"),
        ("", '<section epub:type="appendix"><p>T.</p></section>', None, "back"),
        ('role="doc-colophon"', "<p>T.</p>", None, "back"),
        # Standard Ebooks' uncopyright page: an explicit matter token beats everything.
        (
            'epub:type="backmatter"',
            '<section epub:type="copyright-page"><p>T.</p></section>',
            "frontmatter",
            "back",
        ),
        # A landmark beats a specific token on the document.
        ('epub:type="preface"', "<p>T.</p>", "bodymatter", "body"),
    ],
)
def test_section_kind(tmp_path, config, body_attrs, body, landmark, kind):
    doc = Doc("ch1.xhtml", body, body_attrs=body_attrs, landmark=landmark)
    assert read(tmp_path, config, [doc]).sections[0].kind == kind


# Blocks


def test_headings(tmp_path, config):
    body = """<h1>One</h1><h3>Three</h3><h6>Six</h6>
    <p role="heading" aria-level="4">Aria four</p><div role="heading">Aria default</div>"""
    assert blocks(tmp_path, config, body) == [
        Heading(1, "One"),
        Heading(3, "Three"),
        Heading(6, "Six"),
        Heading(4, "Aria four"),
        Heading(2, "Aria default"),
    ]


def test_paragraph_whitespace_and_line_breaks(tmp_path, config):
    body = """<p>  Two   words
      here <em>and</em>there </p>
    <p>Line one<br/>
       Line two<br/><br/>Line three</p>"""
    assert blocks(tmp_path, config, body) == [
        Paragraph("Two words here andthere"),
        Paragraph("Line one\nLine two\nLine three"),
    ]


def test_loose_text_in_containers_becomes_paragraphs(tmp_path, config):
    body = """<div>Loose <em>text</em><p>Inner</p> tail text</div>
    <blockquote>Quoted</blockquote><section><div>Deep</div></section>Body text"""
    assert blocks(tmp_path, config, body) == [
        Paragraph("Loose text"),
        Paragraph("Inner"),
        Paragraph("tail text"),
        Paragraph("Quoted"),
        Paragraph("Deep"),
        Paragraph("Body text"),
    ]


def test_preformatted_text_keeps_its_lines(tmp_path, config):
    assert blocks(tmp_path, config, "<pre>line one\n   line two</pre>") == [
        Paragraph("line one\nline two")
    ]


def test_lists_flatten_nested_lists(tmp_path, config):
    body = """<ul><li>One</li><li>Two<ul><li>Two A</li><li><p>Two B</p></li></ul></li>
    <li>Three</li></ul><ol><li>First</li></ol>"""
    assert blocks(tmp_path, config, body) == [
        ListBlock(("One", "Two", "Two A", "Two B", "Three")),
        ListBlock(("First",), ordered=True),
    ]


def test_table_with_thead_and_caption(tmp_path, config):
    body = """<table><caption>Prices</caption>
    <thead><tr><th>Item</th><th>Cost</th></tr></thead>
    <tbody><tr><td>Tea</td><td>2&nbsp;d</td></tr><tr><td>Bread</td><td></td></tr></tbody>
    </table>"""
    assert blocks(tmp_path, config, body) == [
        Table(
            (("Item", "Cost"), ("Tea", "2 d"), ("Bread", "")),
            header_rows=1,
            caption="Prices",
        )
    ]


def test_table_header_rows_from_all_th_rows(tmp_path, config):
    body = """<table><tr><th>Year</th><th>Event</th></tr>
    <tr><th>1886</th><td>Published</td></tr></table>"""
    assert blocks(tmp_path, config, body) == [
        Table((("Year", "Event"), ("1886", "Published")), header_rows=1)
    ]


def test_image_alt_missing_empty_and_present(tmp_path, config):
    body = """<p><img src="a.png"/></p><p><img src="b.png" alt=""/></p>
    <div><img src="c.png" alt="A  red barn"/></div>"""
    assert blocks(tmp_path, config, body) == [
        Image(alt=None),
        Image(alt=""),
        Image(alt="A red barn"),
    ]


def test_image_inside_a_paragraph_follows_it(tmp_path, config):
    body = '<p>Before <img src="i.png" alt="icon"/> after.</p>'
    assert blocks(tmp_path, config, body) == [Paragraph("Before after."), Image(alt="icon")]


def test_figure_caption(tmp_path, config):
    body = """<figure><img src="map.png" alt="Map"/><figcaption>The <em>island</em></figcaption>
    </figure><figure><blockquote>Words</blockquote><figcaption>Someone</figcaption></figure>"""
    assert blocks(tmp_path, config, body) == [
        Image(alt="Map", caption="The island"),
        Paragraph("Words"),
        Paragraph("Someone"),
    ]


def test_inline_svg_is_an_image(tmp_path, config):
    body = '<svg xmlns="http://www.w3.org/2000/svg"><title>Cover art</title><text>x</text></svg>'
    assert blocks(tmp_path, config, body) == [Image(alt="Cover art")]


def test_page_markers(tmp_path, config, caplog):
    body = """<p>One.</p><span epub:type="pagebreak" id="p1" title="1"/>
    <p>Text <span role="doc-pagebreak" aria-label="2"/>continues.</p>
    <div epub:type="pagebreak">iii</div>
    <span epub:type="pagebreak" id="p9"/><p>End.</p>"""
    with caplog.at_level(logging.DEBUG, logger="dogear.extract.xhtml_blocks"):
        result = blocks(tmp_path, config, body)
    assert result == [
        Paragraph("One."),
        PageMarker("1"),
        PageMarker("2"),  # a page that starts mid-paragraph is marked before it
        Paragraph("Text continues."),
        PageMarker("iii"),
        Paragraph("End."),
    ]
    assert any("no label" in r.message for r in caplog.records)


def test_page_list_labels_plain_anchors_and_unlabeled_breaks(tmp_path, config):
    body = """<p id="pg7">Seven.</p><p>Text <span id="pg8"/>more.</p>
    <span epub:type="pagebreak" id="pg9"/><ul><li id="pg10">Item</li></ul>"""
    pages = [
        ("ch1.xhtml", "pg7", "7"),
        ("ch1.xhtml", "pg8", "8"),
        ("ch1.xhtml", "pg9", "9"),
        ("ch1.xhtml", "pg10", "10"),
    ]
    book = read(tmp_path, config, [Doc("ch1.xhtml", body)], page_list=pages)
    assert book.sections[0].blocks == [
        PageMarker("7"),
        Paragraph("Seven."),
        PageMarker("8"),
        Paragraph("Text more."),
        PageMarker("9"),
        PageMarker("10"),
        ListBlock(("Item",)),
    ]
    assert book.sections[0].page_labels() == ["7", "8", "9", "10"]


def test_footnotes_and_note_refs(tmp_path, config):
    body = """<p id="r1">Claim<a epub:type="noteref" href="#fn1">1</a> and more<sup><a
      role="doc-noteref" href="#fn2">*</a></sup>.</p>
    <aside epub:type="footnote" id="fn1"><p>First note.
      <a role="doc-backlink" href="#r1">Back</a></p></aside>
    <aside role="doc-footnote" id="fn2"><p>Second</p><p>note.</p></aside>"""
    assert blocks(tmp_path, config, body) == [
        Paragraph("Claim and more.", note_refs=("OEBPS/ch1.xhtml#fn1", "OEBPS/ch1.xhtml#fn2")),
        Footnote("OEBPS/ch1.xhtml#fn1", "First note.", label="1"),
        Footnote("OEBPS/ch1.xhtml#fn2", "Second\nnote.", label="*"),
    ]


def test_endnotes_list_in_another_file(tmp_path, config):
    notes = """<section epub:type="endnotes" role="doc-endnotes"><h2>Notes</h2><ol>
      <li id="n1"><p>Endnote one. <a epub:type="backlink" href="ch1.xhtml#r1">&#8617;</a></p></li>
      <li id="n2"><p>Never referenced.</p></li></ol></section>"""
    docs = [
        Doc("ch1.xhtml", '<p>Text<a id="r1" epub:type="noteref" href="notes.xhtml#n1">i</a>.</p>'),
        Doc("notes.xhtml", notes, body_attrs='epub:type="backmatter"'),
    ]
    book = read(tmp_path, config, docs)
    assert book.sections[0].blocks == [Paragraph("Text.", note_refs=("OEBPS/notes.xhtml#n1",))]
    assert book.sections[1].kind == "back"
    assert book.sections[1].blocks == [
        Heading(2, "Notes"),
        # The label is the marker printed at the reference, else the note's list number.
        Footnote("OEBPS/notes.xhtml#n1", "Endnote one.", label="i"),
        Footnote("OEBPS/notes.xhtml#n2", "Never referenced.", label="2"),
    ]


def test_same_note_id_in_two_files_does_not_collide(tmp_path, config, caplog):
    def chapter(text: str, note: str) -> str:
        return f"""<p>{text}<a epub:type="noteref" href="#fn1">1</a>.</p>
        <aside epub:type="footnote" id="fn1"><p>{note}</p></aside>"""

    docs = [
        Doc("text/ch1.xhtml", chapter("One", "Note in one.")),
        Doc("text/ch2.xhtml", chapter("Two", "Note in two.")),
    ]
    with caplog.at_level(logging.WARNING):
        book = read(tmp_path, config, docs)
    assert [s.blocks for s in book.sections] == [
        [
            Paragraph("One.", note_refs=("OEBPS/text/ch1.xhtml#fn1",)),
            Footnote("OEBPS/text/ch1.xhtml#fn1", "Note in one.", label="1"),
        ],
        [
            Paragraph("Two.", note_refs=("OEBPS/text/ch2.xhtml#fn1",)),
            Footnote("OEBPS/text/ch2.xhtml#fn1", "Note in two.", label="1"),
        ],
    ]
    assert not caplog.records


def test_notes_in_a_non_linear_file_are_read(tmp_path, config, caplog):
    docs = [
        Doc(
            "notes.xhtml",
            '<aside epub:type="endnote" id="n1"><p>Popup note.</p></aside>',
            linear=False,
        ),
        Doc("ch1.xhtml", '<p>Text<a epub:type="noteref" href="notes.xhtml#n1">1</a>.</p>'),
    ]
    with caplog.at_level(logging.WARNING):
        book = read(tmp_path, config, docs)
    assert [s.source for s in book.sections] == ["OEBPS/ch1.xhtml", "OEBPS/notes.xhtml"]
    assert book.sections[1].kind == "back"
    assert book.sections[1].blocks == [Footnote("OEBPS/notes.xhtml#n1", "Popup note.", label="1")]
    assert not caplog.records


def test_note_refs_to_missing_notes_warn(tmp_path, config, caplog):
    body = '<p>Text<a epub:type="noteref" href="#gone">1</a>.</p>'
    with caplog.at_level(logging.WARNING):
        result = blocks(tmp_path, config, body)
    assert result == [Paragraph("Text.", note_refs=("OEBPS/ch1.xhtml#gone",))]
    assert any("won't be read" in r.message for r in caplog.records)


def test_note_without_id_is_read_as_text(tmp_path, config, caplog):
    with caplog.at_level(logging.WARNING):
        result = blocks(tmp_path, config, '<aside epub:type="footnote"><p>Orphan.</p></aside>')
    assert result == [Paragraph("Orphan.")]
    assert any("no id" in r.message for r in caplog.records)


def test_script_style_and_nav_are_skipped(tmp_path, config):
    body = """<script>alert("x")</script><style>p { color: red }</style>
    <nav><ol><li>Contents</li></ol></nav><p>Kept<script>no()</script>.</p>"""
    assert blocks(tmp_path, config, body) == [Paragraph("Kept.")]


def test_scene_breaks(tmp_path, config):
    body = """<p>One.</p><hr/><p>Two.</p>
    <div role="separator" class="stars">* * *</div><p>Three.</p>
    <div role="separator" tabindex="0">Resize handle</div>"""
    assert blocks(tmp_path, config, body) == [
        Paragraph("One."),
        SceneBreak(),
        Paragraph("Two."),
        SceneBreak(),
        Paragraph("Three."),
        Paragraph("Resize handle"),  # a focusable separator is a widget, not a break
    ]


def test_scene_breaks_never_lead_trail_or_repeat(tmp_path, config):
    body = """<hr/><span epub:type="pagebreak" title="1"/><p>One.</p>
    <hr/><span epub:type="pagebreak" title="2"/><hr/><section><hr/></section><p>Two.</p>
    <hr/><span epub:type="pagebreak" title="3"/><hr/>"""
    assert blocks(tmp_path, config, body) == [
        PageMarker("1"),
        Paragraph("One."),
        SceneBreak(),  # kept where the first of the run was
        PageMarker("2"),
        Paragraph("Two."),
        PageMarker("3"),
    ]


def test_scene_break_alone_is_an_empty_section(tmp_path, config):
    docs = [Doc("rule.xhtml", "<hr/>"), Doc("ch1.xhtml", "<p>Text.</p>")]
    assert [s.source for s in read(tmp_path, config, docs).sections] == ["OEBPS/ch1.xhtml"]


# Language


def test_language_inheritance_and_overrides(tmp_path, config):
    body = """<p>Plain</p><p xml:lang="de">Hallo</p><p lang="EN">Same, other case</p>
    <div xml:lang="la"><p>Lorem</p><img src="x.png" alt="Imago"/></div>"""
    docs = [Doc("en.xhtml", body), Doc("fr.xhtml", "<p>Bonjour</p>", html_attrs='xml:lang="fr"')]
    book = read(tmp_path, config, docs, language="en")
    english, french = book.sections
    assert english.lang == "en"
    assert english.blocks == [
        Paragraph("Plain"),
        Paragraph("Hallo", lang="de"),
        Paragraph("Same, other case"),
        Paragraph("Lorem", lang="la"),
        Image(alt="Imago", lang="la"),
    ]
    assert french.lang == "fr"
    assert french.blocks == [Paragraph("Bonjour")]


def test_body_lang_beats_html_lang(tmp_path, config):
    doc = Doc("ch1.xhtml", "<p>Hola</p>", html_attrs='lang="fr"', body_attrs='xml:lang="es"')
    assert read(tmp_path, config, [doc]).sections[0].lang == "es"


# Entities and encodings


def test_html_entities_in_content_and_metadata(tmp_path, config):
    body = """<p>10&nbsp;km &mdash; &ldquo;quoted&rdquo; &amp; &lt;tag&gt; &#169; &hellip;</p>
    <img src="c.png" alt="Caf&eacute;"/>"""
    book = read(tmp_path, config, [Doc("ch1.xhtml", body)], title="Caf&eacute; Stories")
    assert book.metadata.title == "Café Stories"
    assert book.sections[0].blocks == [
        Paragraph("10 km — “quoted” & <tag> © …"),
        Image(alt="Café"),
    ]


def test_xhtml_1_1_doctype_is_not_fetched(tmp_path, config):
    raw = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head>
<body><p>Old&nbsp;style &copy; 1900</p></body></html>"""
    book = read(tmp_path, config, [Doc("ch1.xhtml", raw=raw)])
    assert book.sections[0].blocks == [Paragraph("Old style © 1900")]


def test_internal_entities_are_expanded(tmp_path, config):
    raw = """<?xml version="1.0"?><!DOCTYPE html [<!ENTITY author "Jane Doe">]>
<html xmlns="http://www.w3.org/1999/xhtml"><body><p>By &author;.</p></body></html>"""
    assert read(tmp_path, config, [Doc("ch1.xhtml", raw=raw)]).sections[0].blocks == [
        Paragraph("By Jane Doe.")
    ]


def test_utf16_document(tmp_path, config):
    raw = xhtml("<p>Na&iuml;ve café</p>").replace("utf-8", "utf-16").encode("utf-16")
    assert read(tmp_path, config, [Doc("ch1.xhtml", raw=raw)]).sections[0].blocks == [
        Paragraph("Naïve café")
    ]


def test_html_entities_to_numeric():
    data = b"&nbsp;&amp;&lt;&unknown;&#160;&NotEqualTilde;"
    assert html_entities_to_numeric(data) == b"&#xA0;&amp;&lt;&unknown;&#160;&#x2242;&#x338;"


# Untrusted input


@pytest.fixture
def secret(tmp_path) -> Path:
    path = tmp_path / "secret.txt"
    path.write_text("TOP-SECRET-7731")
    return path


def test_external_entity_in_content_does_not_leak(tmp_path, config, secret):
    raw = f"""<?xml version="1.0"?><!DOCTYPE html [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>
<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Leak: &xxe;</p></body></html>"""
    with pytest.raises(ExtractionError) as e:
        read(tmp_path, config, [Doc("ch1.xhtml", raw=raw)])
    assert "TOP-SECRET" not in f"{e.value.message} {e.value.hint}"


def test_external_entity_in_nav_does_not_leak(tmp_path, config, secret):
    nav = f"""<?xml version="1.0"?><!DOCTYPE html [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
<nav epub:type="toc"><ol><li><a href="ch1.xhtml">&xxe;</a></li></ol></nav></body></html>"""
    path = build_epub(
        tmp_path / "book.epub",
        [Doc("ch1.xhtml", "<p>Text.</p>")],
        files={"OEBPS/nav.xhtml": nav},
    )
    assert "TOP-SECRET" not in all_text(extract(path, config))


@pytest.mark.parametrize(
    "document",
    [
        # A general entity whose replacement text is the secret file.
        '<!DOCTYPE p [<!ENTITY xxe SYSTEM "{secret}">]><p>&xxe;</p>',
        # A parameter entity that pulls in a DTD declaring &leak; as the secret.
        '<!DOCTYPE p [<!ENTITY % ext SYSTEM "{dtd}"> %ext;]><p>&leak;</p>',
        # The same DTD as the document's external subset.
        '<!DOCTYPE p SYSTEM "{dtd}"><p>&leak;</p>',
    ],
)
def test_parse_xml_never_reads_external_files(tmp_path, secret, document):
    dtd = tmp_path / "evil.dtd"
    dtd.write_text('<!ENTITY leak "TOP-SECRET-7731">')
    data = document.format(secret=secret.as_uri(), dtd=dtd.as_uri())
    try:
        root = parse_xml(data.encode(), "test.opf", "hint")
    except ExtractionError as e:
        assert "TOP-SECRET" not in f"{e.message} {e.hint}"
    else:
        assert "TOP-SECRET" not in "".join(root.itertext())


def test_parse_xml_rejects_entity_bombs():
    lol = "".join(f'<!ENTITY l{i} "{f"&l{i - 1};" * 10}">' for i in range(1, 10))
    data = f'<!DOCTYPE x [<!ENTITY l0 "lol">{lol}]><x>&l9;</x>'.encode()
    started = time.monotonic()
    with pytest.raises(ExtractionError):
        parse_xml(data, "bomb.xhtml", "hint")
    assert time.monotonic() - started < 5


def test_oversized_member_is_refused(tmp_path):
    config = load_config(_write(tmp_path / "dogear.toml", "[epub]\nmax_member_mb = 1\n"))
    big = "<p>" + "word " * 250_000 + "</p>"  # about 1.25 MB, compresses to almost nothing
    path = build_epub(tmp_path / "book.epub", [Doc("ch1.xhtml", big)])
    with pytest.raises(ExtractionError, match="more than 1 MB") as e:
        extract(path, config)
    assert "max_member_mb" in e.value.hint
    raised = load_config(_write(tmp_path / "big.toml", "[epub]\nmax_member_mb = 2\n"))
    assert extract(path, raised).word_count() == 250_000


def test_member_limit_must_be_positive(tmp_path):
    config = load_config(_write(tmp_path / "dogear.toml", "[epub]\nmax_member_mb = 0\n"))
    path = build_epub(tmp_path / "book.epub", [Doc("ch1.xhtml", "<p>T.</p>")])
    with pytest.raises(ConfigError, match="max_member_mb"):
        extract(path, config)


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    ("base", "href", "expected"),
    [
        ("OEBPS/content.opf", "text/ch%201.xhtml", ("OEBPS/text/ch 1.xhtml", "")),
        ("OEBPS/text/ch1.xhtml", "../notes.xhtml#n%2D1", ("OEBPS/notes.xhtml", "n-1")),
        ("OEBPS/text/ch1.xhtml", "#fn1", ("OEBPS/text/ch1.xhtml", "fn1")),
        ("OEBPS/text/ch1.xhtml", "./a/../b.xhtml", ("OEBPS/text/b.xhtml", "")),
        ("OEBPS/content.opf", "../../etc/passwd", None),
        ("content.opf", "../x.xhtml", None),
        ("OEBPS/content.opf", "/etc/passwd", None),
        ("OEBPS/content.opf", "https://example.com/ch1.xhtml", None),
        ("OEBPS/content.opf", "file:///etc/passwd", None),
    ],
)
def test_resolve_href(base, href, expected):
    assert resolve_href(base, href) == expected


# Damaged and protected books


def test_drm_protected_content_is_refused(tmp_path, config):
    enc = encryption_xml(["OEBPS/ch1.xhtml"], "http://www.w3.org/2001/04/xmlenc#aes256-cbc")
    path = build_epub(
        tmp_path / "book.epub",
        [Doc("ch1.xhtml", "<p>T.</p>")],
        files={"META-INF/encryption.xml": enc},
    )
    with pytest.raises(ExtractionError, match="DRM") as e:
        extract(path, config)
    assert "DRM-free" in e.value.hint


def test_font_obfuscation_alone_is_fine(tmp_path, config):
    enc = encryption_xml(["OEBPS/fonts/Body Font.otf"], "http://www.idpf.org/2008/embedding")
    path = build_epub(
        tmp_path / "book.epub",
        [Doc("ch1.xhtml", "<p>Text.</p>")],
        files={"META-INF/encryption.xml": enc, "OEBPS/fonts/Body Font.otf": b"\x00garbled"},
    )
    assert extract(path, config).sections[0].blocks == [Paragraph("Text.")]


def test_not_a_zip(tmp_path, config):
    path = tmp_path / "book.epub"
    path.write_bytes(b"This is not a ZIP archive.")
    with pytest.raises(ExtractionError, match="isn't a ZIP") as e:
        extract(path, config)
    assert "damaged" in e.value.hint


def test_missing_container(tmp_path, config):
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    with pytest.raises(ExtractionError, match="container.xml") as e:
        extract(path, config)
    assert "damaged" in e.value.hint


def test_missing_package_file(tmp_path, config):
    path = build_epub(
        tmp_path / "book.epub",
        [Doc("ch1.xhtml", "<p>T.</p>")],
        files={"META-INF/container.xml": container_xml("OEBPS/missing.opf")},
    )
    with pytest.raises(ExtractionError, match="missing.opf"):
        extract(path, config)


def test_malformed_content_document_names_the_file(tmp_path, config):
    raw = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Unclosed</body></html>'
    with pytest.raises(ExtractionError, match="ch1.xhtml") as e:
        read(tmp_path, config, [Doc("ch1.xhtml", raw=raw)])
    assert "Calibre" in e.value.hint


# A real book


def test_standard_ebooks_jekyll_and_hyde(config):
    book = extract(JEKYLL, config)
    meta = book.metadata
    assert meta.title == "The Strange Case of Dr. Jekyll and Mr. Hyde"
    assert meta.authors == ["Robert Louis Stevenson"]
    assert meta.language == "en-GB"
    assert meta.publisher == "Standard Ebooks"
    kinds = [s.kind for s in book.sections]
    assert kinds[0] == "front" and kinds[-1] == "back"
    body = [s for s in book.sections if s.kind == "body"]
    assert len(body) == 10
    assert body[0].title == "Story of the Door"
    assert all(isinstance(s.blocks[0], Heading) for s in body)
    assert 20_000 < sum(s.word_count() for s in body) < 30_000
    assert " " in all_text(book)  # Standard Ebooks writes "Mr.&nbsp;Utterson"
