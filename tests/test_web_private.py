"""Books, what's made from them, and the access key are for this user only: their folders
are owner-only, and so are the files in them (on Linux and macOS)."""

import os
import stat
import sys
import time
from pathlib import Path

import pytest
from web_samples import sample_app, sample_config, visitor

from dogear.web import child
from dogear.web.private import private_folder
from dogear.web.server import lock_web_folder

pytestmark = pytest.mark.skipif(os.name == "nt", reason="file modes are for Linux and macOS")
FAKE = Path(__file__).parent / "fake_dogear.py"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_the_web_folder_is_made_owner_only_but_one_a_person_chose_is_left_alone(tmp_path):
    lock_web_folder(tmp_path / "new" / "web").release()
    assert mode(tmp_path / "new" / "web") == 0o700
    assert mode(tmp_path / "new") == 0o700
    chosen = tmp_path / "Audiobooks"
    chosen.mkdir(mode=0o755)
    chosen.chmod(0o755)
    lock_web_folder(chosen).release()
    assert mode(chosen) == 0o755


def test_dogears_own_folders_are_made_owner_only_even_if_they_exist(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    books.chmod(0o755)
    private_folder(books)
    assert mode(books) == 0o700


def test_books_and_what_is_made_from_them_are_owner_only(tmp_path, monkeypatch):
    monkeypatch.setattr(child, "dogear_command", lambda: [sys.executable, str(FAKE)])
    web = tmp_path / "web"
    app = sample_app(web, sample_config(web))
    with visitor(app) as client:
        response = client.post("/books", files={"book": ("a.epub", b"ok", "")})
        book_id = response.url.path.rsplit("/", 1)[1]
        deadline = time.monotonic() + 30
        while app.state.library.get(book_id).state != "ready":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        client.post(
            f"/books/{book_id}/choose",
            data={"format": ["m4b", "mp3"], "voice": "af_heart", "speed": "0.9", "section": "1"},
        )
        while app.state.library.get(book_id).state != "done":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert client.get(f"/books/{book_id}/files/1").status_code == 200  # a zip
    folder = app.state.library.folder(book_id)
    for path in (web, web / "books", web / "incoming", folder, folder / "made"):
        assert mode(path) == 0o700, path
    made = folder / "made"
    for path in (
        folder / "book.json",
        folder / "book.epub",
        folder / "progress.json",
        made / "Fake Book.m4b",
        made / "Fake Book MP3" / "01 One.mp3",
        *(folder / "zips").rglob("*.zip"),
    ):
        assert mode(path) == 0o600, path
