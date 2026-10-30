"""A book's "Check how words are said" page: the words the voice doesn't know, each with
a Listen button and a "Say it like" field, and one Save for them all.

The page shows the book's latest check (word_check.py) in whatever state it's in: not
checked yet, with a button that starts it (no GET changes anything); waiting or
checking, with a status that progress.js keeps up to date; failed; or done, with the
list. Save writes the page's own pronunciation file (page_words.py).
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from dogear.book_summary import count
from dogear.errors import DogearError
from dogear.pronunciations import Pronunciation, word_key
from dogear.web.book_pages import requested_book
from dogear.web.books import BookRecord
from dogear.web.choices import asks_about_language
from dogear.web.forms import FormTooBig, first, read_form
from dogear.web.library import Library
from dogear.web.page_words import EntryError, PageWords
from dogear.web.settings import WebSettings
from dogear.web.spelling_forms import (
    SentWord,
    WordItem,
    field_for,
    sent_words,
    spellings_to_save,
)
from dogear.web.status import Status
from dogear.web.templating import message, render
from dogear.web.word_check import WORDS_SHOWN, WordCheck, check_for

SAVED = "Saved. Choose Listen to hear a word the new way."
HEADING = "Check how words are said"


def describe_check(check: WordCheck | None, ahead: int | None) -> Status:
    """The check's state in words: the page title's start, the heading, and the status."""
    if check is None:
        return Status(HEADING, HEADING, "")
    match check.state:
        case "waiting":
            if not ahead:
                sentence = "Waiting: checking starts in a moment."
            else:
                books = "1 other book" if ahead == 1 else f"{ahead} other books"
                sentence = f"Waiting: Dogear is checking the words of {books} first."
            return Status("Waiting to check words", HEADING, sentence)
        case "checking":
            return Status(
                "Checking words",
                HEADING,
                "Checking the words. This usually takes a minute or two. The first time, "
                "Dogear also downloads a small language model.",
            )
        case "done":
            if not check.total:
                return Status("No words to check", HEADING, "Checked: the voice knows every word.")
            return Status(
                "Words to check",
                HEADING,
                f"Checked: {count(check.total, 'word')} the voice doesn't know.",
            )
        case "failed":
            return Status(
                "Couldn't check words",
                "Dogear couldn't check the words",
                "Dogear couldn't check the words.",
            )
    raise ValueError(f"unknown state: {check.state}")


def sections_in_words(numbers: tuple[int, ...]) -> str:
    """() as "the whole book"; (1, 2, 3, 7, 8) as "sections 1 to 3, 7 and 8"."""
    if not numbers:
        return "the whole book"
    runs: list[list[int]] = []
    for n in sorted(set(numbers)):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    parts: list[str] = []
    for a, b in runs:
        parts += [f"{a} to {b}"] if b > a + 1 else [str(n) for n in range(a, b + 1)]
    if len(parts) == 1:
        return f"section {parts[0]}" if runs[0][0] == runs[0][1] else f"sections {parts[0]}"
    return "sections " + ", ".join(parts[:-1]) + " and " + parts[-1]


def _library(request: Request) -> Library:
    return request.app.state.library


async def words_page(request: Request) -> Response:
    record = requested_book(request)
    if record.summary is None:
        return RedirectResponse(f"/books/{record.id}", status_code=303)
    notice = SAVED if request.query_params.get("saved") == "1" else ""
    return await _page(request, record, notice=notice)


async def words_status(request: Request) -> Response:
    """The check's state as JSON, for progress.js."""
    record = requested_book(request)
    checks = _library(request).words
    check = checks.get(record.id)
    status = describe_check(check, checks.ahead(record.id))
    return JSONResponse(
        {
            "state": check.state if check else "none",
            "title": f"{status.title}: {record.title} - Dogear",
            "sentence": status.sentence,
            "first": 0,  # progress.js shows lines; a check has none
            "lines": [],
        }
    )


async def start_check(request: Request) -> Response:
    """Check the book's words: the sections and voice chosen for it, if any. A book that
    says it's in another language is read as English when the form says so."""
    record = requested_book(request)
    if record.summary is None:
        return RedirectResponse(f"/books/{record.id}", status_code=303)
    try:
        fields = await read_form(request)
    except FormTooBig:
        fields = []
    as_english = first(fields, "english") == "yes" and asks_about_language(record.summary)
    _library(request).words.request(record.id, check_for(record, as_english))
    return RedirectResponse(f"/books/{record.id}/words", status_code=303)


async def save_words(request: Request) -> Response:
    """Save every "Say it like" on the page; an empty one removes that word's entry."""
    record = requested_book(request)
    if record.summary is None:
        return RedirectResponse(f"/books/{record.id}", status_code=303)
    try:
        fields = await read_form(request)
    except FormTooBig:
        return message(request, 413, "Form too big", "That form was too big", "Try again.")
    settings: WebSettings = request.app.state.settings
    sent = sent_words(fields, WORDS_SHOWN)
    spellings, errors = spellings_to_save(sent, settings.word_limits)
    if not errors:
        page_words: PageWords = request.app.state.page_words
        try:
            await run_in_threadpool(page_words.save, spellings)
        except EntryError as e:
            errors[field_for(sent, e.word)] = e.message
        except DogearError as e:
            return word_file_problem(request, "Dogear couldn't save the words", e)
    if errors:
        return await _page(request, record, sent=sent, errors=errors, status_code=400)
    return RedirectResponse(f"/books/{record.id}/words?saved=1", status_code=303)


def word_file_problem(request: Request, heading: str, error: DogearError) -> Response:
    """A page for a word list that can't be read or saved, saying why and what to do."""
    return message(
        request, 500, heading, heading, *[text for text in (error.message, error.hint) if text]
    )


async def _page(
    request: Request,
    record: BookRecord,
    *,
    sent: list[SentWord] | None = None,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    notice: str = "",
) -> Response:
    summary = record.summary
    assert summary is not None
    checks = _library(request).words
    check = checks.get(record.id)
    page_words: PageWords = request.app.state.page_words
    try:
        saved = await run_in_threadpool(page_words.entries)
    except DogearError as e:
        return word_file_problem(request, "Dogear can't read its word list", e)
    status = describe_check(check, checks.ahead(record.id))
    items = _items(check, saved, sent)
    errors = errors or {}
    upcoming = check_for(record)
    shown = check or upcoming
    more = check.total - len(check.words) if check and check.state == "done" else 0
    return render(
        request,
        "words.html",
        f"{status.title}: {record.title}",
        status_code=status_code,
        errors=errors,
        targets={field: field for field in errors},
        notice=notice,
        book_id=record.id,
        book_title=record.title,
        check=check,
        status=status,
        watching=check is not None and check.state in ("waiting", "checking"),
        where=sections_in_words(shown.sections),
        needs_english=asks_about_language(summary) and not upcoming.as_english,
        language=summary.language or "",
        items=items,
        more=more,
        fewest=check.words[-1].count if more and check and check.words else 0,
        back=f"/books/{record.id}/words",
    )


def _items(
    check: WordCheck | None, saved: list[Pronunciation], sent: list[SentWord] | None
) -> list[WordItem]:
    """The words to show: those sent back, with what was typed, when a Save had errors;
    otherwise the check's words, each with the spelling saved for it, if any."""
    if check is None and sent is None:
        return []
    found = check.words if check is not None and check.state == "done" else ()
    where = "In the checked sections" if check is not None and check.sections else "In the book"
    counts = {word_key(w.word): w.count for w in found}

    def about(word: str) -> str:
        times = counts.get(word_key(word))
        return f"{where} {count(times, 'time')}." if times else ""

    if sent is not None:
        return [WordItem(s.number, s.word, about(s.word), s.typed) for s in sent]
    spellings = {word_key(e.word): e.sounds_like or "" for e in saved}
    return [
        WordItem(n, w.word, about(w.word), spellings.get(word_key(w.word), ""))
        for n, w in enumerate(found, start=1)
    ]
