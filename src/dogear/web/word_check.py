"""Checking a book's words: `dogear words --json` in a child process, checked here.

A check lists the words in a book (or in the sections chosen for it) that the voice
doesn't know, so a person can listen to them and fix the ones it says wrong. The child
gets the page's own pronunciation file, so words fixed already aren't listed again.
Checks run on their own queue, one at a time, apart from reading, making, and Listen.

The child's JSON is checked word by word, and bounded: the server reads at most
MAX_WORDS_BYTES of it and keeps the WORDS_SHOWN most frequent words, with how many there
were in all. Each book's latest check is kept in memory only, so after a restart the
page offers to check again.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from dogear.unknown_words import UnknownWord, words_from_json
from dogear.web.books import BookRecord, BookStore
from dogear.web.child import Stopper, child_command, interrupted, run_captured
from dogear.web.making import section_spec
from dogear.web.page_words import words_option
from dogear.web.reading import problem_from_output
from dogear.web.settings import WebSettings
from dogear.web.worker import Worker

WORDS_SHOWN = 50  # words listed on the page, most frequent first
MAX_WORDS_BYTES = 4 * 1024 * 1024
BUG_HINT = "This is a bug in Dogear. Please report it, with the kind of book you used."
CHECK_AGAIN = "Choose Check again."

CheckState = Literal["waiting", "checking", "done", "failed"]


@dataclass(frozen=True)
class WordCheck:
    state: CheckState
    sections: tuple[int, ...] = ()  # the sections checked; () is the whole book
    as_english: bool = False  # read as English, whatever language the book says
    voice: str = ""  # the voice whose accent counts, or "" for the usual one
    words: tuple[UnknownWord, ...] = ()  # the most frequent, at most WORDS_SHOWN
    total: int = 0  # how many words the voice doesn't know, listed here or not
    error: str = ""
    hint: str = ""


def check_for(record: BookRecord, as_english: bool = False) -> WordCheck:
    """A new check of the book: of the sections and voice chosen for it, if it has
    choices, else of the whole book with the usual voice."""
    choices = record.choices
    if choices is None:
        return WordCheck("waiting", as_english=as_english)
    every = record.summary is not None and len(choices.sections) == len(record.summary.sections)
    return WordCheck(
        "waiting",
        sections=() if every else choices.sections,
        as_english=as_english or choices.as_english,
        voice=choices.voice,
    )


def words_args(source: Path, check: WordCheck) -> list[str]:
    """`dogear words`'s arguments for the check."""
    args = ["words", str(source), "--json"]
    if check.sections:
        args += ["--sections", section_spec(check.sections)]
    if check.voice:
        args += ["--voice", check.voice]
    if check.as_english:
        args += ["--language", "en"]
    return args


# Whatever runs a check: `check_words`, or a stand-in in tests. It returns the check,
# done or failed, or None if it was stopped (the book deleted, or the server stopping).
CheckFunction = Callable[[BookStore, WebSettings, str, WordCheck, Stopper], WordCheck | None]


def check_words(
    store: BookStore, settings: WebSettings, book_id: str, check: WordCheck, stopper: Stopper
) -> WordCheck | None:
    record = store.get(book_id)
    if record is None:
        return None
    source = store.folder(book_id) / record.source_name
    command = child_command(
        [*words_args(source, check), *words_option(settings.words_file)], settings.config_file
    )
    result = run_captured(
        command,
        timeout=settings.read_timeout_seconds,
        max_stdout=MAX_WORDS_BYTES,
        stopper=stopper,
    )
    if stopper.requested.is_set():
        return None
    if result.timed_out:
        return _failed(
            check,
            f"Checking the words took longer than {settings.read_timeout_seconds:g} seconds, "
            "so Dogear stopped.",
            "If the book is very long, choose a few sections to make, then check again. Or "
            "raise web.read_timeout_seconds in your config file.",
        )
    if interrupted(result.returncode):
        return _failed(
            check, "Something stopped Dogear while it was checking the words.", CHECK_AGAIN
        )
    if result.returncode != 0:
        problem = problem_from_output(result.stderr)
        return _failed(check, problem.error, problem.hint)
    if result.too_long:
        return _failed(
            check, "The list of this book's words was too long for the page to read.", BUG_HINT
        )
    return parse_words(result.stdout, check)


def parse_words(data: bytes, check: WordCheck) -> WordCheck:
    try:
        words = words_from_json(json.loads(data.decode("utf-8")))
    except (UnicodeDecodeError, ValueError) as e:
        return _failed(
            check, f"Dogear couldn't understand the list of this book's words ({e}).", BUG_HINT
        )
    return replace(check, state="done", words=tuple(words[:WORDS_SHOWN]), total=len(words))


def _failed(check: WordCheck, error: str, hint: str) -> WordCheck:
    return replace(check, state="failed", error=error, hint=hint)


class WordChecks:
    """Each book's latest word check, and the queue that runs them. Thread-safe."""

    def __init__(
        self, store: BookStore, settings: WebSettings, run: CheckFunction = check_words
    ) -> None:
        self._store = store
        self._settings = settings
        self._run = run
        self._lock = threading.Lock()
        self._checks: dict[str, WordCheck] = {}
        self.worker = Worker("checker", self._job)

    def start(self) -> None:
        self.worker.start()

    def close(self, timeout: float) -> None:
        self.worker.close(timeout)

    def get(self, book_id: str) -> WordCheck | None:
        with self._lock:
            return self._checks.get(book_id)

    def ahead(self, book_id: str) -> int | None:
        return self.worker.ahead(book_id)

    def request(self, book_id: str, check: WordCheck) -> None:
        """Check the book's words, unless a check is waiting or running already."""
        with self._lock:
            current = self._checks.get(book_id)
            if current is not None and current.state in ("waiting", "checking"):
                return
            self._checks[book_id] = check
        self.worker.add(book_id)

    def forget(self, book_id: str, timeout: float) -> None:
        """Stop any check of the book and forget it, for a book being deleted."""
        if self.worker.stop(book_id):
            self.worker.wait_until_not_running(book_id, timeout)
        with self._lock:
            self._checks.pop(book_id, None)

    def _job(self, book_id: str, stopper: Stopper) -> None:
        with self._lock:
            check = self._checks.get(book_id)
            if check is None:
                return
            check = self._checks[book_id] = replace(check, state="checking")
        result: WordCheck | None = None
        try:
            result = self._run(self._store, self._settings, book_id, check, stopper)
        except Exception:
            result = _failed(
                check,
                "Dogear stopped because of a problem it didn't expect.",
                "Choose Check again. If it happens again, please report it.",
            )
            raise  # the worker logs the traceback
        finally:
            with self._lock:
                if result is None:
                    self._checks.pop(book_id, None)
                elif book_id in self._checks:  # not forgotten meanwhile
                    self._checks[book_id] = result
