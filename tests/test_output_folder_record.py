import json

import pytest

from dogear.document import Metadata
from dogear.errors import OutputFolderError
from dogear.output.folder_record import RECORD_NAME, claim_folder, finish_folder

BOOK = Metadata(title="Book One", authors=["A. Writer"])


def run(folder, metadata, names):
    """What a packager does: claim, write the files, finish."""
    stale = claim_folder(folder, metadata, names)
    for name in names:
        (folder / name).write_text("audio")
    finish_folder(folder, metadata, names, stale)


def recorded(folder):
    return json.loads((folder / RECORD_NAME).read_text(encoding="utf-8"))


def test_empty_folder_is_claimed_and_recorded(tmp_path):
    run(tmp_path, BOOK, ["01 - A.mp3", "Book One.m3u"])
    record = recorded(tmp_path)
    assert record["files"] == ["01 - A.mp3", "Book One.m3u"]
    assert record["book"]["title"] == "Book One"


def test_rerun_removes_only_its_own_leftovers(tmp_path):
    (tmp_path / "my notes.txt").write_text("mine")
    run(tmp_path, BOOK, ["01 - A.mp3", "02 - B.mp3"])
    run(tmp_path, BOOK, ["01 - A.mp3", "02 - Bee.mp3"])
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        RECORD_NAME,
        "01 - A.mp3",
        "02 - Bee.mp3",
        "my notes.txt",
    ]
    assert recorded(tmp_path)["files"] == ["01 - A.mp3", "02 - Bee.mp3"]


def test_case_only_rename_is_not_stale(tmp_path):
    # On Windows and macOS these are one file; removing the "old" one would remove the new.
    run(tmp_path, BOOK, ["01 - chapter one.mp3"])
    assert claim_folder(tmp_path, BOOK, ["01 - Chapter One.mp3"]) == []


def test_different_book_is_refused(tmp_path):
    run(tmp_path, BOOK, ["01 - A.mp3"])
    other = Metadata(title="Book Two", authors=["A. Writer"])
    with pytest.raises(OutputFolderError, match='another book, "Book One"') as err:
        claim_folder(tmp_path, other, ["01 - A.mp3"])
    assert "different folder" in err.value.hint
    assert recorded(tmp_path)["book"]["title"] == "Book One"


def test_same_identifier_is_the_same_book_even_if_retitled(tmp_path):
    run(tmp_path, Metadata(title="Draft Title", identifier="urn:isbn:1"), ["01 - A.mp3"])
    renamed = Metadata(title="Final Title", identifier="urn:isbn:1")
    assert claim_folder(tmp_path, renamed, ["01 - A.mp3"]) == []


def test_file_dogear_did_not_make_is_never_overwritten(tmp_path):
    (tmp_path / "01 - A.mp3").write_text("mine")
    with pytest.raises(OutputFolderError, match="didn't make"):
        claim_folder(tmp_path, BOOK, ["01 - A.mp3"])
    assert (tmp_path / "01 - A.mp3").read_text() == "mine"


def test_interrupted_run_still_owns_its_files(tmp_path):
    claim_folder(tmp_path, BOOK, ["01 - A.mp3"])
    (tmp_path / "01 - A.mp3").write_text("half")  # then the run stopped
    run(tmp_path, BOOK, ["01 - A.mp3"])
    assert (tmp_path / "01 - A.mp3").read_text() == "audio"


@pytest.mark.parametrize(
    "record",
    [
        "not json",
        json.dumps([]),
        json.dumps({"book": {"title": "B", "authors": []}, "files": ["../escape.mp3"]}),
        json.dumps({"book": {"title": "B", "authors": []}, "files": ["C:evil.mp3"]}),
        json.dumps({"book": {"title": "B"}, "files": []}),
    ],
)
def test_damaged_record_stops_the_run(tmp_path, record):
    (tmp_path / RECORD_NAME).write_text(record, encoding="utf-8")
    with pytest.raises(OutputFolderError, match="damaged") as err:
        claim_folder(tmp_path, BOOK, ["01 - A.mp3"])
    assert RECORD_NAME in err.value.hint
