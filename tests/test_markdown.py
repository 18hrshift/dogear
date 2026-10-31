import codecs
import logging
from pathlib import Path

import pytest
from network_watch import remote_references, watched_server

from dogear import cli
from dogear.config import load_config
from dogear.document import (
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    Paragraph,
    SceneBreak,
    Table,
)
from dogear.errors import ConfigError, ExtractionError
from dogear.extract.markdown_book import extract

FRONT = """---
title: "Dogear: A Story"
authors:
  - Ada Writer
  - Bo Coauthor
lang: en-GB
date: 2026-10-30
---
"""


def read(tmp_path: Path, config, text: str | bytes, name: str = "book.md") -> Book:
    path = tmp_path / name
    if isinstance(text, str):
        path.write_text(text, encoding="utf-8")
    else:
        path.write_bytes(text)
    return extract(path, config)


def blocks(tmp_path: Path, config, text: str) -> list:
    book = read(tmp_path, config, text)
    assert len(book.sections) == 1
    return book.sections[0].blocks


# Metadata


def test_front_matter_gives_the_metadata(tmp_path, config):
    book = read(tmp_path, config, FRONT + "# Heading\n\nText.\n")
    assert book.metadata.title == "Dogear: A Story"
    assert book.metadata.authors == ["Ada Writer", "Bo Coauthor"]
    assert book.metadata.language == "en-GB"
    assert book.source_format == "md"
    assert book.sections[0].blocks == [Heading(1, "Heading"), Paragraph("Text.")]


@pytest.mark.parametrize(
    ("front", "authors", "language"),
    [
        ("author: Ada Writer\nlanguage: de\n", ["Ada Writer"], "de"),
        ("authors: [Ada, Bo, Ada]\nlang: no\n", ["Ada", "Bo"], "no"),  # Norwegian, not false
        ("Title: X\nAuthor: Cap\n", ["Cap"], None),  # keys in any case
    ],
)
def test_front_matter_variants(tmp_path, config, front, authors, language):
    book = read(tmp_path, config, f"---\n{front}---\n\nText.\n")
    assert book.metadata.authors == authors
    assert book.metadata.language == language


def test_without_front_matter_the_title_is_the_lone_top_heading(tmp_path, config):
    text = "# The Book\n\n## One\n\nA.\n\n## Two\n\nB.\n"
    book = read(tmp_path, config, text)
    assert book.metadata.title == "The Book"
    assert [(s.title, s.kind) for s in book.sections] == [
        ("The Book", "front"),
        ("One", "body"),
        ("Two", "body"),
    ]
    assert read(
        tmp_path, config, "# One\n\nA.\n\n# Two\n", name="notes.markdown"
    ).metadata.title == ("notes")


def test_a_rule_at_the_top_isnt_front_matter(tmp_path, config, caplog):
    with caplog.at_level(logging.INFO):
        found = blocks(tmp_path, config, "---\n\nIntro.\n\n---\n\nMore.\n")
    assert found == [Paragraph("Intro."), SceneBreak(), Paragraph("More.")]
    assert "aren't front matter" in caplog.text


def test_invalid_front_matter_says_how_to_fix_it(tmp_path, config):
    with pytest.raises(ExtractionError, match="isn't valid YAML.*line 2") as e:
        read(tmp_path, config, "---\ntitle: Dogear: A Story\n---\n\nText.\n")
    assert "needs quotes" in e.value.hint


def test_front_matter_cant_build_objects(tmp_path, config):
    marker = tmp_path / "ran"
    front = f"---\ntitle: !!python/object/apply:os.system ['touch {marker}']\n---\n\nText.\n"
    book = read(tmp_path, config, front)
    assert not marker.exists()
    assert book.metadata.title == "book"  # the value is a list, not text: ignored


def test_values_that_arent_text_are_ignored_with_a_warning(tmp_path, config, caplog):
    with caplog.at_level(logging.WARNING):
        book = read(tmp_path, config, "---\nauthor: {name: Ada}\n---\n\nText.\n")
    assert book.metadata.authors == []
    assert "Ignored 'author'" in caplog.text


# Blocks


def test_markdown_blocks(tmp_path, config):
    text = """Para with *emphasis*,
a soft line break, and ~~struck~~ text.

1. First
2. Second
   - nested

| Name | Age |
|------|-----|
| Ann  | 3   |

***

```
code  block
```

After.
"""
    assert blocks(tmp_path, config, text) == [
        Paragraph("Para with emphasis, a soft line break, and struck text."),
        ListBlock(("First", "Second", "nested"), ordered=True),
        Table((("Name", "Age"), ("Ann", "3")), header_rows=1),
        SceneBreak(),
        Paragraph("code block"),
        Paragraph("After."),
    ]


def test_images(tmp_path, config):
    text = '![A sleeping cat](cat.png)\n\n![](photo.jpg)\n\n<img src="rule.png" alt="">\n'
    assert blocks(tmp_path, config, text) == [
        Image(alt="A sleeping cat"),
        Image(alt=None),  # Markdown with no description: none given, not decorative
        Image(alt=""),  # HTML can mark an image decorative
    ]


def test_footnotes(tmp_path, config):
    text = "# One\n\nIt began.[^a] It went on.[^b]\n\n[^a]: First note.\n[^b]: Second, *long*.\n"
    [section] = read(tmp_path, config, text).sections
    assert section.kind == "body"  # notes at the end don't make the chapter back matter
    assert section.blocks == [
        Heading(1, "One"),
        Paragraph("It began. It went on.", note_refs=("book.md#fn1", "book.md#fn2")),
        Footnote("book.md#fn1", "First note.", label="1"),
        Footnote("book.md#fn2", "Second, long.", label="2"),
    ]


def test_html_in_markdown_is_read_safely(tmp_path, config):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET")
    text = (
        f'<!DOCTYPE x [<!ENTITY s SYSTEM "{secret.as_uri()}">]>\n\n'
        'English, <span lang="fr">un peu</span>. &s;\n\n'
        '<p lang="fr">Tout en français.</p>\n\n'
        "<script>alert('hi')</script>\n\n"
        "<!-- a comment -->\n"
    )
    found = blocks(tmp_path, config, "---\nlang: en\n---\n" + text)
    assert Paragraph("Tout en français.", lang="fr") in found
    assert all("SECRET" not in getattr(b, "text", "") for b in found)
    assert all("alert" not in getattr(b, "text", "") for b in found)


def test_nothing_is_fetched(tmp_path, config):
    with watched_server() as (base, requests):
        text = f"![A photo]({base}/photo.jpg)\n\n{remote_references(base)}\n\nText.\n"
        found = blocks(tmp_path, config, text)
    assert requests == []
    assert found[0] == Image(alt="A photo")


# Character sets and limits


def test_utf16_with_a_byte_order_mark(tmp_path, config):
    data = codecs.BOM_UTF16_LE + "# Café\n\nText.\n".encode("utf-16-le")
    assert read(tmp_path, config, data).sections[0].title == "Café"


def test_text_that_isnt_utf8_is_an_error(tmp_path, config):
    with pytest.raises(ExtractionError, match="isn't UTF-8") as e:
        read(tmp_path, config, "# Café\n".encode("cp1252"))
    assert "UTF-8" in e.value.hint


def test_nesting_too_deep_to_read_is_an_error(tmp_path, config):
    with pytest.raises(ExtractionError, match="more than 100 levels deep"):
        read(tmp_path, config, ">" * 150 + " deep\n\nAfter.\n")


def test_size_limit_is_a_setting(tmp_path):
    text = "word " * 250_000  # about 1.25 MB
    config = load_config(_write(tmp_path / "dogear.toml", "[markdown]\nmax_file_mb = 1\n"))
    with pytest.raises(ExtractionError, match="bigger than 1 MB") as e:
        read(tmp_path, config, text)
    assert "markdown.max_file_mb" in e.value.hint
    raised = load_config(_write(tmp_path / "big.toml", "[markdown]\nmax_file_mb = 2\n"))
    assert read(tmp_path, raised, text).word_count() == 250_000


def test_size_limit_must_be_positive(tmp_path):
    config = load_config(_write(tmp_path / "dogear.toml", "[markdown]\nmax_file_mb = -1\n"))
    with pytest.raises(ConfigError, match="markdown.max_file_mb"):
        read(tmp_path, config, "Text.\n")


def test_an_empty_file_has_no_text(tmp_path, config):
    with pytest.raises(ExtractionError, match="no readable text"):
        read(tmp_path, config, FRONT)


# The command line


def test_outline_of_a_markdown_file(tmp_path, capsys):
    path = tmp_path / "story.md"
    path.write_text(FRONT + "# One\n\nFirst.[^1]\n\n# Two\n\nSecond.\n\n[^1]: A note.\n")
    assert cli.main(["outline", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Title: Dogear: A Story" in out
    assert "By: Ada Writer, Bo Coauthor" in out
    assert "MD file, 2 sections" in out
    assert "1. One: main text, 2 words." in out


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path
