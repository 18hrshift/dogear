"""Downloads: only files inside a book's made folder, and folders as cached zips."""

import os
import zipfile

import pytest
from web_samples import CHOSEN, add_book, sample_app, sample_summary, visitor

from dogear.web.books import Output
from dogear.web.downloads import NotAvailable, describe_size, output_path, zip_folder


@pytest.fixture
def app(tmp_path):
    return sample_app(tmp_path / "web")


def done_book(app, tmp_path, outputs):
    return add_book(
        app.state.library,
        tmp_path,
        state="done",
        choices=CHOSEN,
        summary=sample_summary(),
        outputs=outputs,
    )


@pytest.mark.parametrize(
    "path",
    ["book.epub", "book.json", "made/../book.json", "../../access-key.txt", "made", "/etc/passwd"],
)
def test_nothing_outside_the_made_folder_is_served(app, tmp_path, path):
    book_id = done_book(app, tmp_path, [Output("m4b", path)])
    folder = app.state.library.folder(book_id)
    with pytest.raises(NotAvailable):
        output_path(Output("m4b", path), folder)
    response = visitor(app).get(f"/books/{book_id}/files/0")
    assert response.status_code == 404
    assert "<h1>Page not found</h1>" in response.text


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need extra rights on Windows")
def test_a_link_out_of_the_made_folder_is_not_followed(app, tmp_path):
    book_id = done_book(app, tmp_path, [Output("m4b", "made/link.m4b")])
    made = app.state.library.folder(book_id) / "made"
    made.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    (made / "link.m4b").symlink_to(secret)
    assert visitor(app).get(f"/books/{book_id}/files/0").status_code == 404


def test_only_numbered_outputs_of_finished_books_are_served(app, tmp_path):
    book_id = done_book(app, tmp_path, [])
    client = visitor(app)
    assert client.get(f"/books/{book_id}/files/0").status_code == 404
    assert client.get(f"/books/{book_id}/files/-1").status_code == 404
    assert client.get(f"/books/{book_id}/files/x").status_code == 404
    assert client.get("/books/..%2F..%2Fx/files/0").status_code == 404


def test_a_folder_is_zipped_once_without_compression(app, tmp_path):
    book_id = done_book(app, tmp_path, [Output("daisy", "made/Book DAISY")])
    book_folder = app.state.library.folder(book_id)
    daisy = book_folder / "made" / "Book DAISY"
    (daisy / "sub").mkdir(parents=True)
    (daisy / "ncc.html").write_text("<html/>")
    (daisy / "sub" / "a.mp3").write_bytes(b"a" * 5000)
    (daisy / ".dogear.json").write_text("{}")  # Dogear's own record: not for the listener
    first = zip_folder(daisy, book_folder)
    assert first == book_folder / "zips" / "Book DAISY.zip"
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["Book DAISY/ncc.html", "Book DAISY/sub/a.mp3"]
        assert {i.compress_type for i in archive.infolist()} == {zipfile.ZIP_STORED}
    made_at = first.stat().st_mtime_ns
    assert zip_folder(daisy, book_folder).stat().st_mtime_ns == made_at
    response = visitor(app).get(f"/books/{book_id}/files/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == first.read_bytes()


def test_a_missing_output_is_said_not_skipped(app, tmp_path):
    book_id = done_book(app, tmp_path, [Output("m4b", "made/Gone.m4b")])
    page = visitor(app).get(f"/books/{book_id}").text
    assert "M4B audiobook: Gone.m4b is no longer in its folder." in page


@pytest.mark.parametrize(
    ("size", "words"),
    [
        (1, "1 byte"),
        (999, "999 bytes"),
        (2048, "2 KB"),
        (3_000_000, "2.9 MB"),
        (121_634_816, "116 MB"),
        (1_288_490_189, "1.2 GB"),
    ],
)
def test_sizes_in_words(size, words):
    assert describe_size(size) == words
