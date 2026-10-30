"""Each book's record and folder: saving, loading, and deleting."""

import errno
import os

import pytest
from web_samples import add_book, sample_config

from dogear.web import atomic
from dogear.web.books import RECORD, BookStore
from dogear.web.library import Library
from dogear.web.settings import web_settings


@pytest.fixture
def library(tmp_path):
    return Library(web_settings(sample_config(tmp_path / "web")))


def test_records_are_saved_under_names_no_other_writer_uses(library, tmp_path, monkeypatch):
    book_id = add_book(library, tmp_path, state="ready")
    folder = library.folder(book_id)
    names = []
    real_replace = os.replace

    def replace(source, target):
        names.append(os.path.basename(source))
        real_replace(source, target)

    monkeypatch.setattr(atomic.os, "replace", replace)
    library.store.update(book_id, error="x")
    library.store.update(book_id, error="y")
    assert len(set(names)) == 2
    assert all(name.startswith(".book.json.") and name.endswith(".partial") for name in names)
    assert sorted(p.name for p in folder.iterdir()) == ["book.epub", RECORD]


def test_a_save_that_fails_leaves_nothing_half_written(library, tmp_path, monkeypatch):
    book_id = add_book(library, tmp_path, state="ready")
    folder = library.folder(book_id)

    def full(source, target):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(atomic.os, "replace", full)
    with pytest.raises(OSError):
        library.store.update(book_id, error="x")
    assert sorted(p.name for p in folder.iterdir()) == ["book.epub", RECORD]


def test_leftovers_of_a_save_that_died_are_cleared_on_start(library, tmp_path):
    book_id = add_book(library, tmp_path, state="ready")
    folder = library.folder(book_id)
    (folder / ".book.json.abc123.partial").write_text("{")
    store = BookStore(library.store.dir)
    store.load()
    assert store.get(book_id).state == "ready"
    assert sorted(p.name for p in folder.iterdir()) == ["book.epub", RECORD]
