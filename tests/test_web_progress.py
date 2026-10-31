"""A book's progress lines: repeats collapsed, only the latest kept, saved now and then
instead of with every line, and never written into the book's record."""

import errno
import json
import logging
import re
from dataclasses import replace

import lxml.html
import pytest
from web_samples import CHOSEN, add_book, sample_app, sample_summary, visitor

from dogear.book_summary import SectionSummary
from dogear.web import progress
from dogear.web.books import BookStore
from dogear.web.progress import (
    LINES_FILE,
    MAX_KEPT,
    SAVE_EVERY_SECONDS,
    Line,
    ProgressLog,
    left_out_sentence,
)

NOTE = "WARNING: A note in OEBPS/notes.xhtml has no id; reading it as ordinary text."


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def writes(monkeypatch):
    """Every save, as the data written."""
    saved = []
    real = progress.write_atomically

    def write(path, data):
        saved.append(json.loads(data))
        real(path, data)

    monkeypatch.setattr(progress, "write_atomically", write)
    return saved


def test_a_line_repeated_in_a_row_is_one_line_with_a_count(tmp_path):
    log = ProgressLog(tmp_path / LINES_FILE)
    log.add("Making an audiobook of A Book.")
    for _ in range(412):
        log.add(NOTE)
    log.add("Section 1 of 3 done: One.")
    log.add(NOTE)  # not in a row with the others: a line of its own
    view = log.view()
    assert [line.shown for line in view.lines] == [
        "Making an audiobook of A Book.",
        f"{NOTE} (412 times)",
        "Section 1 of 3 done: One.",
        NOTE,
    ]
    assert Line("x", 1_234).shown == "x (1,234 times)"


def test_only_the_latest_lines_are_kept(tmp_path):
    log = ProgressLog(tmp_path / LINES_FILE)
    for n in range(1, 1001):
        log.add(f"WARNING: No pronunciation found for 'Xq{n}', so it will be skipped.")
    view = log.view()
    assert len(view.lines) == MAX_KEPT
    assert view.left_out == 1000 - MAX_KEPT
    assert view.lines[-1].text.endswith("'Xq1000', so it will be skipped.")
    last = view.last(20)
    assert (last.left_out, len(last.lines)) == (980, 20)
    assert last.lines == view.lines[-20:]
    assert left_out_sentence(1) == "1 earlier line isn't shown."
    assert left_out_sentence(4212) == "4,212 earlier lines aren't shown."


def test_the_latest_progress_skips_warnings(tmp_path):
    """It's what the status says (and a screen reader announces) while a book is made."""
    log = ProgressLog(tmp_path / LINES_FILE)
    assert log.view().latest == ""
    log.add("Section 2 of 9 done: Two.")
    log.add(NOTE)
    log.add("ERROR: something")
    assert log.view().latest == "Section 2 of 9 done: Two."


def test_lines_are_saved_now_and_then_not_with_every_line(tmp_path, writes):
    clock = Clock()
    log = ProgressLog(tmp_path / LINES_FILE, clock)
    for n in range(500):
        log.add(f"line {n}")
    assert len(writes) == 1  # the first line, then nothing until the time is up
    clock.now += SAVE_EVERY_SECONDS
    log.add("line 500")
    assert len(writes) == 2
    log.save()  # when making ends: whatever came since
    log.save()  # nothing new: nothing written
    assert len(writes) == 2
    log.add("the last line")
    log.save()
    assert len(writes) == 3
    assert writes[-1]["lines"][-1] == ["the last line", 1]


def test_saved_lines_come_back_after_a_restart(tmp_path):
    log = ProgressLog(tmp_path / LINES_FILE)
    log.add("Section 1 of 2 done: One.")
    for _ in range(3):
        log.add(NOTE)
    for n in range(MAX_KEPT + 5):
        log.add(f"line {n}")
    log.save()
    again = ProgressLog.load(tmp_path)
    assert again.view() == log.view()


def test_a_damaged_progress_file_is_ignored(tmp_path, caplog):
    (tmp_path / LINES_FILE).write_text('{"lines": "not lines"}')
    (tmp_path / f".{LINES_FILE}.x1.partial").write_text("{")  # a save that died
    with caplog.at_level(logging.WARNING, logger="dogear.web.progress"):
        log = ProgressLog.load(tmp_path)
    assert log.view().lines == ()
    assert "Ignoring the saved progress" in caplog.text
    assert sorted(p.name for p in tmp_path.iterdir()) == [LINES_FILE]


def test_a_save_that_fails_is_logged_once_and_tried_again(tmp_path, monkeypatch, caplog):
    clock = Clock()
    log = ProgressLog(tmp_path / LINES_FILE, clock)
    real = progress.write_atomically

    def full(path, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(progress, "write_atomically", full)
    with caplog.at_level(logging.WARNING, logger="dogear.web.progress"):
        for n in range(5):
            log.add(f"line {n}")
            clock.now += SAVE_EVERY_SECONDS
    assert len(caplog.records) == 1
    monkeypatch.setattr(progress, "write_atomically", real)
    log.save()
    assert len(ProgressLog.load(tmp_path).view().lines) == 5


def test_adding_a_line_never_rewrites_the_record(tmp_path, monkeypatch):
    """A 3,000-section book's record is about 0.7 MB. Rewriting it for every line, under
    the store's lock, cost about 83 ms a line."""
    store = BookStore(tmp_path / "books")
    store.load()
    upload = tmp_path / "upload"
    upload.write_bytes(b"ok")
    book_id = store.create("big.epub", ".epub", upload).id
    sections = tuple(
        SectionSummary(n, f"Chapter {n}", "body", 5000, str(n), str(n + 9), 1, 2, 0)
        for n in range(1, 3001)
    )
    store.update(book_id, state="making", summary=replace(sample_summary(), sections=sections))
    saves = []
    monkeypatch.setattr(BookStore, "_save", lambda self, record: saves.append(record))
    for n in range(2000):
        store.add_line(book_id, f"WARNING: No pronunciation found for 'Xq{n}'.")
    assert saves == []
    assert store.get(book_id) is store.get(book_id)  # shared, not copied for every page
    assert len(store.progress(book_id).lines) == MAX_KEPT


def test_the_status_carries_only_the_latest_lines(tmp_path):
    app = sample_app(tmp_path / "web")
    lines = [f"WARNING: No pronunciation found for 'Xq{n}'." for n in range(1000)]
    book_id = add_book(
        app.state.library,
        tmp_path,
        state="making",
        choices=CHOSEN,
        summary=sample_summary(),
        lines=["Section 1 of 4 done: Title Page.", *lines],
    )
    status = visitor(app).get(f"/books/{book_id}/status").json()
    assert status["first"] == 981
    assert len(status["lines"]) == 20
    assert status["lines"][-1] == "WARNING: No pronunciation found for 'Xq999'."
    assert status["sentence"] == "Making: Section 1 of 4 done: Title Page."


def test_the_page_shows_the_latest_lines_and_says_how_many_came_before(tmp_path):
    app = sample_app(tmp_path / "web")
    book_id = add_book(
        app.state.library,
        tmp_path,
        state="stopped",
        choices=CHOSEN,
        summary=sample_summary(),
        lines=["Making an audiobook.", *[NOTE] * 50, *[f"line {n}" for n in range(150)]],
    )
    page = lxml.html.fromstring(visitor(app).get(f"/books/{book_id}").text)
    [left_out] = page.xpath("//p[@id='lines-left-out']")
    assert left_out.text_content() == "52 earlier lines aren't shown."
    assert left_out.get("hidden") is None
    [listed] = page.xpath("//ol[@id='progress-lines']")
    assert listed.get("start") == "53"
    assert listed.get("data-max-lines") == str(MAX_KEPT)
    assert len(listed.xpath("./li")) == MAX_KEPT
    assert listed.get("data-left-out-many") == "{n} earlier lines aren't shown."


def test_a_page_with_few_lines_says_nothing_was_left_out(tmp_path):
    app = sample_app(tmp_path / "web")
    book_id = add_book(
        app.state.library,
        tmp_path,
        state="making",
        choices=CHOSEN,
        summary=sample_summary(),
        lines=["Making an audiobook.", NOTE, NOTE],
    )
    page = lxml.html.fromstring(visitor(app).get(f"/books/{book_id}").text)
    [left_out] = page.xpath("//p[@id='lines-left-out']")
    assert left_out.get("hidden") is not None
    assert left_out.text_content() == ""
    items = [re.sub(r"\s+", " ", li.text_content()) for li in page.xpath("//ol/li")]
    assert items == ["Making an audiobook.", f"{NOTE} (2 times)"]
