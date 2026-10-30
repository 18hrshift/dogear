"""Each book's record and folder: saving, loading, and deleting."""

import errno
import logging
import os

import pytest
from web_samples import add_book, sample_app, sample_config, visitor

from dogear.web import atomic, books
from dogear.web.books import RECORD, TRASH_PREFIX, BookStore
from dogear.web.library import Library
from dogear.web.settings import web_settings


@pytest.fixture
def library(tmp_path):
    return Library(web_settings(sample_config(tmp_path / "web")))


def test_a_delete_that_fails_keeps_the_book_whole_and_listed(tmp_path, monkeypatch):
    """Windows won't move a folder holding a file another program has open (a player, a
    download in progress). Then nothing is deleted, and deleting again works later."""
    app = sample_app(tmp_path / "web")
    book_id = add_book(app.state.library, tmp_path, state="unreadable", error="e")
    folder = app.state.library.folder(book_id)
    (folder / "made").mkdir()
    (folder / "made" / "a.mp3").write_bytes(b"a")

    def in_use(source, target):
        raise PermissionError(errno.EACCES, "The process cannot access the file")

    monkeypatch.setattr(books.os, "rename", in_use)
    client = visitor(app)
    response = client.post(f"/books/{book_id}/delete")
    assert response.status_code == 500
    assert "<h1>Dogear couldn&#39;t delete the book</h1>" in response.text
    assert "nothing was deleted" in response.text
    assert "close that program. Then try again." in response.text
    assert f'href="/books/{book_id}"' in client.get("/").text
    assert client.get(f"/books/{book_id}").status_code == 200
    assert (folder / "made" / "a.mp3").exists() and (folder / RECORD).exists()

    monkeypatch.undo()
    response = client.post(f"/books/{book_id}/delete", follow_redirects=False)
    assert response.headers["location"] == "/?deleted=1"
    assert not folder.exists()
    assert list(app.state.settings.books_dir.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="file modes are for Linux and macOS")
def test_files_left_by_a_delete_are_removed_when_the_server_next_starts(library, tmp_path, caplog):
    book_id = add_book(library, tmp_path, state="unreadable", error="e")
    stuck = library.folder(book_id) / "made" / "sub"
    stuck.mkdir(parents=True)
    (stuck / "a.mp3").write_bytes(b"a")
    stuck.chmod(0o500)  # its file can't be deleted
    try:
        with caplog.at_level(logging.WARNING, logger="dogear.web.books"):
            library.delete(book_id)
        assert library.get(book_id) is None  # deleted, as far as anyone can see
        [left] = list(library.store.dir.iterdir())
        assert left.name.startswith(TRASH_PREFIX + book_id)
        assert "Dogear tries again when it next starts." in caplog.text
    finally:
        for sub in library.store.dir.glob("*/made/sub"):
            sub.chmod(0o700)
    BookStore(library.store.dir).load()
    assert list(library.store.dir.iterdir()) == []


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
