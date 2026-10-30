"""Each book's record: the file that came in, what was chosen, and how making it went.

Every book has its own folder under the web folder's `books`, named by a random id. It
holds `book.json` (the record), the uploaded file (`book.epub` or similar), `made` (what
was made from it), and `zips` (folders zipped for download). The record is saved on every
change, so a restarted server lists every book. One that was waiting or being made when
the server stopped shows as stopped.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from dogear.book_summary import BookSummary, summary_from_json, summary_to_json
from dogear.extract import EXTRACTORS
from dogear.make import FORMATS
from dogear.web.atomic import remove_leftovers, write_atomically

log = logging.getLogger(__name__)

State = Literal[
    "reading",  # finding its sections with `dogear outline`
    "unreadable",  # Dogear couldn't read it
    "ready",  # read, and waiting for choices
    "waiting",  # in the queue to be made
    "making",
    "done",
    "failed",
    "stopped",  # by the user, or by the server stopping
]
STATES: tuple[State, ...] = (
    "reading",
    "unreadable",
    "ready",
    "waiting",
    "making",
    "done",
    "failed",
    "stopped",
)
RECORD = "book.json"
MADE = "made"
ZIPS = "zips"
MAX_LINES = 200  # progress lines kept per book; older ones are dropped
MAX_NAME_CHARS = 255  # of the uploaded file's name, as shown
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{16}")

CLOSED_ERROR = "Dogear was closed before this book was finished."
CLOSED_HINT = "Choose Start again to carry on. What was already spoken is kept."


@dataclass(frozen=True)
class Choices:
    formats: tuple[str, ...]  # in make.FORMATS order
    voice: str
    speed: float
    sections: tuple[int, ...]  # section numbers, from 1
    as_english: bool = False  # read as English, whatever language the book says it's in


@dataclass(frozen=True)
class Output:
    format: str  # one of make.FORMATS
    path: str  # inside the book's folder, such as "made/The Title.m4b"


@dataclass
class BookRecord:
    id: str
    original_name: str  # the uploaded file's name: shown, never used as a path
    extension: str  # ".epub", ".pdf", ...
    added: float  # when it was uploaded, in seconds since 1970
    state: State
    summary: BookSummary | None = None
    choices: Choices | None = None
    lines: list[str] = field(default_factory=list)
    lines_dropped: int = 0  # how many earlier lines MAX_LINES let go
    error: str = ""
    hint: str = ""
    outputs: list[Output] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.summary.title if self.summary else self.original_name

    @property
    def source_name(self) -> str:
        return "book" + self.extension


class BookStore:
    """Every book's record, kept in memory and saved to its folder. Thread-safe: pages
    and the workers that read and make books all use it."""

    def __init__(self, books_dir: Path) -> None:
        self.dir = books_dir
        self._lock = threading.RLock()
        self._books: dict[str, BookRecord] = {}

    def load(self) -> list[str]:
        """Read every saved record. Returns the ids of books that were still being read,
        which need reading again; books that were waiting or being made become stopped."""
        self.dir.mkdir(parents=True, exist_ok=True)
        unread = []
        with self._lock:
            for folder in sorted(self.dir.iterdir()):
                record = _read_record(folder)
                if record is not None:
                    remove_leftovers(folder, RECORD)
                if record is None:
                    continue
                if record.state in ("waiting", "making"):
                    record = replace(record, state="stopped", error=CLOSED_ERROR, hint=CLOSED_HINT)
                    self._books[record.id] = record
                    self._save(record)
                else:
                    self._books[record.id] = record
                if record.state == "reading":
                    unread.append(record.id)
        return unread

    def create(self, original_name: str, extension: str, upload: Path) -> BookRecord:
        """A new book, in state "reading", with `upload` moved into its folder. Raises
        OSError, keeping nothing, if it can't be saved."""
        with self._lock:
            book_id = secrets.token_urlsafe(12)
            while book_id in self._books or not ID_PATTERN.fullmatch(book_id):
                book_id = secrets.token_urlsafe(12)
            record = BookRecord(
                id=book_id,
                original_name=original_name[:MAX_NAME_CHARS],
                extension=extension,
                added=time.time(),
                state="reading",
            )
            folder = self.folder(book_id)
            try:
                folder.mkdir(parents=True)
                os.replace(upload, folder / record.source_name)
                self._save(record)
            except OSError:
                # A full disk, say: no half-made book is left behind or listed.
                shutil.rmtree(folder, ignore_errors=True)
                raise
            self._books[book_id] = record
            return copy.deepcopy(record)

    def get(self, book_id: str) -> BookRecord | None:
        with self._lock:
            record = self._books.get(book_id)
            return copy.deepcopy(record) if record else None

    def all(self) -> list[BookRecord]:
        """Every book, newest first."""
        with self._lock:
            records = [copy.deepcopy(r) for r in self._books.values()]
        return sorted(records, key=lambda r: r.added, reverse=True)

    def update(self, book_id: str, **changes: Any) -> BookRecord | None:
        """Change and save a record. None if the book was deleted in the meantime."""
        with self._lock:
            record = self._books.get(book_id)
            if record is None:
                return None
            record = replace(record, **changes)
            self._books[book_id] = record
            self._save(record)
            return copy.deepcopy(record)

    def add_line(self, book_id: str, line: str) -> None:
        with self._lock:
            record = self._books.get(book_id)
            if record is None:
                return
            lines = [*record.lines, line]
            dropped = max(0, len(lines) - MAX_LINES)
            self.update(
                book_id, lines=lines[dropped:], lines_dropped=record.lines_dropped + dropped
            )

    def delete(self, book_id: str) -> None:
        with self._lock:
            self._books.pop(book_id, None)
            shutil.rmtree(self.folder(book_id), ignore_errors=False)

    def folder(self, book_id: str) -> Path:
        if not ID_PATTERN.fullmatch(book_id):
            raise ValueError(f"not a book id: {book_id!r}")
        return self.dir / book_id

    def _save(self, record: BookRecord) -> None:
        data = json.dumps(_to_json(record), indent=1).encode("utf-8")
        write_atomically(self.folder(record.id) / RECORD, data)


def _to_json(record: BookRecord) -> dict[str, Any]:
    data = asdict(record)
    data["summary"] = summary_to_json(record.summary) if record.summary else None
    return data


def _read_record(folder: Path) -> BookRecord | None:
    path = folder / RECORD
    if not ID_PATTERN.fullmatch(folder.name) or not path.is_file():
        return None
    try:
        return _from_json(json.loads(path.read_text(encoding="utf-8")), folder.name)
    except (OSError, ValueError, TypeError, KeyError) as e:
        log.warning("Skipping the book in %s: its record can't be read (%s).", folder, e)
        return None


def _from_json(data: dict[str, Any], book_id: str) -> BookRecord:
    if data["id"] != book_id or data["state"] not in STATES:
        raise ValueError("the record doesn't match its folder")
    if data["extension"] not in EXTRACTORS:
        raise ValueError(f"{data['extension']!r} isn't a kind of book Dogear reads")
    choices = data.get("choices")
    if choices is not None:
        choices = Choices(
            formats=tuple(f for f in choices["formats"] if f in FORMATS),
            voice=str(choices["voice"]),
            speed=float(choices["speed"]),
            sections=tuple(int(n) for n in choices["sections"]),
            as_english=bool(choices.get("as_english", False)),
        )
    return BookRecord(
        id=book_id,
        original_name=str(data["original_name"])[:MAX_NAME_CHARS],
        extension=str(data["extension"]),
        added=float(data["added"]),
        state=data["state"],
        summary=summary_from_json(data["summary"]) if data.get("summary") else None,
        choices=choices,
        lines=[str(line) for line in data.get("lines", [])][-MAX_LINES:],
        lines_dropped=int(data.get("lines_dropped", 0)),
        error=str(data.get("error", "")),
        hint=str(data.get("hint", "")),
        outputs=[
            Output(format=str(o["format"]), path=str(o["path"])) for o in data.get("outputs", [])
        ],
    )
