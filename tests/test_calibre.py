import io
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import require_tool
from epub_builder import Doc, Resource, build_epub
from PIL import Image

from dogear.document import Paragraph
from dogear.errors import ConfigError, ExtractionError, ToolFailedError, ToolNotFoundError
from dogear.extract import calibre, extract_book


def jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 90), "navy").save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def epub(tmp_path) -> Path:
    """What the fake ebook-convert produces: an EPUB 2 with a cover, as Calibre writes."""
    return build_epub(
        tmp_path / "made-by-calibre.epub",
        [Doc("ch1.xhtml", "<h1>One</h1><p>Converted text.</p>")],
        title=None,
        nav=False,
        ncx=True,
        resources=[Resource("cover.jpeg", jpeg(), "image/jpeg", id="cover")],
        cover_meta="cover",
    )


@pytest.fixture
def fake_convert(monkeypatch, epub):
    """Replace Calibre with a stand-in that copies `epub` to the output path."""
    calls = []

    def run_tool(cmd, *, timeout=None):
        calls.append((cmd, timeout))
        shutil.copyfile(epub, cmd[2])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(calibre, "find_tool", lambda key, config: f"/opt/{key}")
    monkeypatch.setattr(calibre, "run_tool", run_tool)
    return calls


def kindle_file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"BOOKMOBI")
    return path


@pytest.mark.parametrize(("name", "fmt"), [("Story.mobi", "mobi"), ("Story.AZW3", "azw3")])
def test_converts_then_reads_the_epub(tmp_path, config, fake_convert, name, fmt):
    source = kindle_file(tmp_path, name)
    book = calibre.extract(source, config)
    assert book.source_path == source
    assert book.source_format == fmt
    assert book.metadata.title == "Story"  # no title in the EPUB: falls back to the original
    assert book.metadata.cover is not None and book.metadata.cover.media_type == "image/jpeg"
    assert book.sections[0].blocks[1] == Paragraph("Converted text.")
    [(cmd, timeout)] = fake_convert
    assert cmd[:2] == ["/opt/ebook_convert", str(source)]
    assert cmd[2].endswith(".epub")
    assert timeout == config["kindle"]["convert_timeout_seconds"]


def test_configured_timeout_reaches_ebook_convert(tmp_path, config, fake_convert):
    config["kindle"]["convert_timeout_seconds"] = 42
    calibre.extract(kindle_file(tmp_path, "book.mobi"), config)
    [(_, timeout)] = fake_convert
    assert timeout == 42


def test_timeout_must_be_positive(tmp_path, config, fake_convert):
    config["kindle"]["convert_timeout_seconds"] = 0
    with pytest.raises(ConfigError, match="convert_timeout_seconds"):
        calibre.extract(kindle_file(tmp_path, "book.mobi"), config)
    assert not fake_convert


def test_temporary_epub_is_removed(tmp_path, config, fake_convert):
    calibre.extract(kindle_file(tmp_path, "book.azw"), config)
    [(cmd, _)] = fake_convert
    assert not Path(cmd[2]).exists()
    assert not Path(cmd[2]).parent.exists()


def test_extract_book_dispatches_kindle_formats(tmp_path, config, fake_convert):
    assert extract_book(kindle_file(tmp_path, "book.azw3"), config).source_format == "azw3"


def test_drm_failure_becomes_a_clear_error(tmp_path, config, monkeypatch):
    def run_tool(cmd, *, timeout=None):
        raise ToolFailedError("ebook-convert failed (exit code 1):\ncalibre.ebooks.DRMError: ...")

    monkeypatch.setattr(calibre, "find_tool", lambda key, config: "ebook-convert")
    monkeypatch.setattr(calibre, "run_tool", run_tool)
    with pytest.raises(ExtractionError, match="DRM") as e:
        calibre.extract(kindle_file(tmp_path, "locked.azw"), config)
    assert "DRM-free" in e.value.hint


def test_other_conversion_failures_pass_through(tmp_path, config, monkeypatch):
    def run_tool(cmd, *, timeout=None):
        raise ToolFailedError("ebook-convert failed (exit code 1):\nUnknown format")

    monkeypatch.setattr(calibre, "find_tool", lambda key, config: "ebook-convert")
    monkeypatch.setattr(calibre, "run_tool", run_tool)
    with pytest.raises(ToolFailedError, match="Unknown format"):
        calibre.extract(kindle_file(tmp_path, "odd.mobi"), config)


def test_conversion_without_output_is_an_error(tmp_path, config, monkeypatch):
    monkeypatch.setattr(calibre, "find_tool", lambda key, config: "ebook-convert")
    monkeypatch.setattr(calibre, "run_tool", lambda cmd, *, timeout=None: None)
    with pytest.raises(ExtractionError, match="didn't produce an EPUB"):
        calibre.extract(kindle_file(tmp_path, "book.mobi"), config)


def test_missing_calibre_says_how_to_install(tmp_path, config):
    config["tools"]["ebook_convert"] = str(tmp_path / "no-such-ebook-convert")
    with pytest.raises(ToolNotFoundError) as e:
        calibre.extract(kindle_file(tmp_path, "book.mobi"), config)
    assert "calibre-ebook.com" in e.value.hint


@pytest.mark.skipif(os.name == "nt", reason="the stand-in program is a shell script")
def test_uses_the_ebook_convert_named_in_config(tmp_path, config, epub):
    script = tmp_path / "my-ebook-convert"
    script.write_text(f'#!/bin/sh\ncp "{epub}" "$2"\n')
    script.chmod(0o755)
    config["tools"]["ebook_convert"] = str(script)
    book = calibre.extract(kindle_file(tmp_path, "book.mobi"), config)
    assert book.sections[0].blocks[1] == Paragraph("Converted text.")


def test_real_calibre_round_trip(tmp_path, config):
    program = require_tool("ebook-convert")
    cover = jpeg()
    source = build_epub(
        tmp_path / "source.epub",
        [Doc("ch1.xhtml", "<h1>Chapter One</h1><p>The quick brown fox.</p>")],
        title="Round Trip",
        resources=[Resource("cover.jpg", cover, "image/jpeg", properties="cover-image")],
    )
    azw3 = tmp_path / "round-trip.azw3"
    subprocess.run([program, str(source), str(azw3)], check=True, capture_output=True)
    book = calibre.extract(azw3, config)
    assert book.metadata.title == "Round Trip"
    assert book.source_format == "azw3"
    # The cover survives both conversions (Calibre may re-encode it, so compare the type).
    assert book.metadata.cover is not None
    assert book.metadata.cover.media_type == "image/jpeg"
    text = " ".join(b.text for s in book.sections for b in s.blocks if isinstance(b, Paragraph))
    assert "The quick brown fox." in text
