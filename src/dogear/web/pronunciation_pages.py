"""The Pronunciations page: every word fixed on the page, to change or remove, a form to
add one, and a field to hear any short text said with them.

It edits the page's own pronunciation file (page_words.py). Each saved word is a group
like those on a book's words page (spelling_forms.py), with its own Listen button. Save
saves only the words changed on the page, so a page opened earlier never undoes a
change made since. Phoneme entries, written into the file by hand, are listed but never
changed here.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from dogear.errors import DogearError
from dogear.web.forms import MAX_FIELDS, MAX_FORM_BYTES, FormTooBig, first, read_form
from dogear.web.listen_pages import start_listen, wants_json
from dogear.web.listening import MAX_LISTEN_CHARS, ListenError, clean_text
from dogear.web.page_words import EntryError, PageWords, clean_spelling, clean_word
from dogear.web.settings import WebSettings
from dogear.web.spelling_forms import (
    MAX_NUMBER_DIGITS,
    SentWord,
    WordItem,
    form_limits,
    save_sent,
    sent_words,
    shown_again,
)
from dogear.web.templating import message, render
from dogear.web.word_pages import word_file_problem

PAGE = "/pronunciations"
NOTICES = {"added": "Added. Its Listen button is with it below.", "saved": "Saved."}
NO_SPELLING = 'Type how the word should sound, such as "utter son" for Utterson.'


def _page_words(request: Request) -> PageWords:
    return request.app.state.page_words


def _settings(request: Request) -> WebSettings:
    return request.app.state.settings


async def pronunciations_page(request: Request) -> Response:
    notice = NOTICES.get(request.query_params.get("done", ""), "")
    return await _page(request, notice=notice)


async def save(request: Request) -> Response:
    """POST /pronunciations: every saved word's "Say it like"; an empty one removes it.
    Only the words changed on the page are saved."""
    limits = _settings(request).word_limits
    most_bytes, most_fields = form_limits(limits)
    try:
        fields = await read_form(
            request, max(MAX_FORM_BYTES, most_bytes), max(MAX_FIELDS, most_fields)
        )
    except FormTooBig:
        return message(request, 413, "Form too big", "That form was too big", "Try again.")
    sent = sent_words(fields, 10**MAX_NUMBER_DIGITS - 1)
    try:
        sent, errors = await run_in_threadpool(save_sent, _page_words(request), sent, limits)
    except DogearError as e:
        return word_file_problem(request, "Dogear couldn't save the words", e)
    if errors:
        return await _page(request, sent=sent, errors=errors, status_code=400)
    return RedirectResponse(f"{PAGE}?done=saved", status_code=303)


async def add(request: Request) -> Response:
    """POST /pronunciations/add: a new word and how to say it. A word saved already, in
    any capitals, gets the new spelling."""
    try:
        fields = await read_form(request)
    except FormTooBig:
        return message(request, 413, "Form too big", "That form was too big", "Try again.")
    typed_word, typed_spelling = first(fields, "word"), first(fields, "spelling")
    limits = _settings(request).word_limits
    errors: dict[str, str] = {}
    word = spelling = ""
    try:
        word = clean_word(typed_word, limits)
    except EntryError as e:
        errors["add-word"] = e.message
    try:
        spelling = clean_spelling(typed_spelling, word or "the word", limits)
        if not spelling:
            errors["add-spelling"] = NO_SPELLING
    except EntryError as e:
        errors["add-spelling"] = e.message
    if not errors:
        try:
            await run_in_threadpool(_page_words(request).save, {word: spelling})
        except EntryError as e:
            errors["add-word"] = e.message
        except DogearError as e:
            return word_file_problem(request, "Dogear couldn't save the word", e)
    if errors:
        return await _page(
            request, added=(typed_word, typed_spelling), errors=errors, status_code=400
        )
    return RedirectResponse(f"{PAGE}?done=added", status_code=303)


async def try_saying(request: Request) -> Response:
    """POST /pronunciations/try: say any short text, as Listen does."""
    try:
        fields = await read_form(request)
    except FormTooBig:
        return message(request, 413, "Form too big", "That form was too big", "Try again.")
    typed = first(fields, "text")
    try:
        text = clean_text(typed)
    except ListenError as e:
        if wants_json(request):
            return JSONResponse({"state": "failed", "error": e.message, "hint": ""}, 400)
        return await _page(request, tried=typed, errors={"try-text": e.message}, status_code=400)
    return await start_listen(request, text, f"{PAGE}#try")


async def _page(
    request: Request,
    *,
    sent: list[SentWord] | None = None,
    added: tuple[str, str] = ("", ""),
    tried: str = "",
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    notice: str = "",
) -> Response:
    try:
        entries = await run_in_threadpool(_page_words(request).entries)
    except DogearError as e:
        return word_file_problem(request, "Dogear can't read its word list", e)
    if sent is not None:
        items = shown_again(sent, entries)
    else:
        spelled = [(e.word, e.sounds_like) for e in entries if e.sounds_like is not None]
        items = [
            WordItem(n, word, "", spelling, spelling)
            for n, (word, spelling) in enumerate(spelled, 1)
        ]
    errors = errors or {}
    return render(
        request,
        "pronunciations.html",
        "Pronunciations",
        status_code=status_code,
        errors=errors,
        current="pronunciations",
        targets={field: field for field in errors},
        notice=notice,
        items=items,
        phonemes=[e for e in entries if e.phonemes is not None],
        added_word=added[0],
        added_spelling=added[1],
        tried=tried,
        max_try=MAX_LISTEN_CHARS,
        words_file=str(_settings(request).words_file),
    )
