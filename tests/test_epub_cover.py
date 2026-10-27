import logging
from pathlib import Path

import pytest
from epub_builder import Doc, Resource, build_epub, encryption_xml

from dogear.config import load_config
from dogear.document import Book, Cover
from dogear.extract.epub import extract

LOGGER = "dogear.extract.epub_cover"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x01" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x02" * 64
GIF = b"GIF89a" + b"\x03" * 64
CHAPTER = Doc("ch1.xhtml", "<p>Alice was beginning to get very tired.</p>", toc_title="I")


def read(tmp_path: Path, config, docs=(CHAPTER,), **kwargs) -> Book:
    return extract(build_epub(tmp_path / "book.epub", list(docs), **kwargs), config)


def info_messages(caplog) -> list[str]:
    return [r.message for r in caplog.records if r.levelno == logging.INFO]


def test_epub3_cover_image_property(tmp_path, config):
    resources = [
        Resource("images/other.png", PNG, "image/png"),
        Resource("images/cover.jpg", JPEG, "image/jpeg", properties="cover-image"),
    ]
    book = read(tmp_path, config, resources=resources)
    assert book.metadata.cover == Cover(JPEG, "image/jpeg")


def test_epub2_meta_cover(tmp_path, config):
    resources = [Resource("cover.png", PNG, "image/png", id="cover-img")]
    book = read(tmp_path, config, resources=resources, cover_meta="cover-img", nav=False, ncx=True)
    assert book.metadata.cover == Cover(PNG, "image/png")


def test_meta_cover_naming_an_href_instead_of_an_id(tmp_path, config):
    resources = [Resource("images/cover.jpg", JPEG, "image/jpeg")]
    book = read(tmp_path, config, resources=resources, cover_meta="images/cover.jpg")
    assert book.metadata.cover == Cover(JPEG, "image/jpeg")


def test_cover_image_property_beats_meta_cover(tmp_path, config):
    resources = [
        Resource("old.png", PNG, "image/png", id="old"),
        Resource("new.jpg", JPEG, "image/jpeg", properties="cover-image"),
    ]
    book = read(tmp_path, config, resources=resources, cover_meta="old")
    assert book.metadata.cover == Cover(JPEG, "image/jpeg")


def test_type_comes_from_the_bytes_not_the_declaration(tmp_path, config):
    resources = [Resource("cover.jpg", PNG, "image/jpeg", properties="cover-image")]
    assert read(tmp_path, config, resources=resources).metadata.cover == Cover(PNG, "image/png")


def test_guide_cover_page_image(tmp_path, config):
    docs = [Doc("cover.xhtml", '<div><img src="images/c.jpg" alt="Cover"/></div>'), CHAPTER]
    resources = [Resource("images/c.jpg", JPEG, "image/jpeg")]
    book = read(
        tmp_path,
        config,
        docs,
        resources=resources,
        guide=[("cover", "cover.xhtml")],
        nav=False,
        ncx=True,
    )
    assert book.metadata.cover == Cover(JPEG, "image/jpeg")


def test_landmark_cover_page_with_an_svg_image(tmp_path, config):
    svg = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
      viewBox="0 0 600 800"><image xlink:href="../images/c.png"/></svg>"""
    docs = [Doc("text/cover.xhtml", svg, landmark="cover"), CHAPTER]
    resources = [Resource("images/c.png", PNG, "image/png")]
    book = read(tmp_path, config, docs, resources=resources)
    assert book.metadata.cover == Cover(PNG, "image/png")


def test_no_cover(tmp_path, config, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config)
    assert book.metadata.cover is None
    assert any("No cover image found" in m for m in info_messages(caplog))


@pytest.mark.parametrize(
    "resource",
    [
        Resource("cover.gif", GIF, "image/gif", properties="cover-image"),
        Resource("cover.jpg", GIF, "image/jpeg", properties="cover-image"),  # mislabeled
        Resource("cover.svg", b"<svg/>", "image/svg+xml", properties="cover-image"),
        Resource("cover.jpg", b"", "image/jpeg", properties="cover-image"),
    ],
)
def test_cover_that_is_not_jpeg_or_png_is_skipped(tmp_path, config, caplog, resource):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, resources=[resource])
    assert book.metadata.cover is None
    assert book.sections  # the book is still read
    assert any("isn't a JPEG or PNG" in m for m in info_messages(caplog))


def test_unusable_cover_falls_through_to_the_next_place(tmp_path, config):
    resources = [
        Resource("cover.gif", GIF, "image/gif", properties="cover-image"),
        Resource("cover.png", PNG, "image/png", id="fallback"),
    ]
    book = read(tmp_path, config, resources=resources, cover_meta="fallback")
    assert book.metadata.cover == Cover(PNG, "image/png")


def test_missing_cover_file(tmp_path, config, caplog):
    resources = [Resource("cover.jpg", None, "image/jpeg", properties="cover-image")]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, resources=resources)
    assert book.metadata.cover is None
    assert any("missing" in m for m in info_messages(caplog))


def test_meta_cover_naming_nothing(tmp_path, config, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, cover_meta="ghost")
    assert book.metadata.cover is None
    assert any("ghost" in m for m in info_messages(caplog))


def test_oversized_cover_is_skipped_not_fatal(tmp_path, caplog):
    path = tmp_path / "dogear.toml"
    path.write_text("[epub]\nmax_member_mb = 1\n")
    config = load_config(path)
    big = JPEG + b"\x00" * (1024 * 1024)  # just over 1 MB, compresses to almost nothing
    resources = [Resource("cover.jpg", big, "image/jpeg", properties="cover-image")]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, resources=resources)
    assert book.metadata.cover is None
    assert book.sections
    assert any("more than 1 MB" in m for m in info_messages(caplog))
    path.write_text("[epub]\nmax_member_mb = 2\n")
    assert read(tmp_path, load_config(path), resources=resources).metadata.cover == Cover(
        big, "image/jpeg"
    )


def test_encrypted_cover_is_skipped(tmp_path, config, caplog):
    enc = encryption_xml(["OEBPS/cover.jpg"], "http://www.w3.org/2001/04/xmlenc#aes256-cbc")
    resources = [Resource("cover.jpg", JPEG, "image/jpeg", properties="cover-image")]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        book = read(tmp_path, config, resources=resources, files={"META-INF/encryption.xml": enc})
    assert book.metadata.cover is None
    assert any("encrypted" in m for m in info_messages(caplog))
