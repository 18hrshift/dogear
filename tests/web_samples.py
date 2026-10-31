"""Sample web pages: the web app with books in every state, and each page saved as HTML.

The unit tests use the helpers, and so does the accessibility check, which runs outside
pytest (it needs a browser):

    uv run python tests/web_samples.py OUT_DIR
    scripts/check-web-a11y.sh OUT_DIR

No child process runs: the books' states are written straight into the store.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path

import lxml.html
from starlette.applications import Starlette
from starlette.testclient import TestClient

from dogear.book_summary import BookSummary, SectionSummary
from dogear.config import Config, default_config
from dogear.unknown_words import UnknownWord
from dogear.web.access_key import AccessKey
from dogear.web.app import STATIC, create_app
from dogear.web.books import Choices, Output
from dogear.web.library import Library
from dogear.web.listening import Listen, Listens
from dogear.web.page_words import PageWords
from dogear.web.settings import WebSettings, web_settings
from dogear.web.word_check import WordCheck

KEY = "abcde-fghjk-mnpqr-stuvw-xyz23"
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


def sample_config(folder: Path) -> Config:
    config = default_config()
    config["web"]["dir"] = str(folder)
    return config


def sample_app(
    folder: Path, config: Config | None = None, library: Library | None = None, **options
) -> Starlette:
    config = config or sample_config(folder)
    settings = web_settings(config, port=options.pop("port", PORT), **options)
    return create_app(settings, config, AccessKey(KEY), library)


def settings_of(app: Starlette) -> WebSettings:
    return app.state.settings


def visitor(app: Starlette, *, signed_in: bool = True) -> TestClient:
    """A browser on this computer: same-origin forms, and the access cookie if signed in."""
    base = f"http://127.0.0.1:{app.state.settings.port}"
    client = TestClient(app, base_url=base, headers={"Origin": base})
    if signed_in:
        response = client.get(f"/start?key={KEY}", follow_redirects=False)
        assert response.status_code == 303, response.text
    return client


def sample_summary(title: str = "The Strange Case of Dr Jekyll and Mr Hyde") -> BookSummary:
    sections = [
        ("Title Page", "front", 12, None, None, 0, 0),
        ("Story of the Door", "body", 2_510, "1", "12", 0, 1),
        ("Search for Mr. Hyde", "body", 3_120, "13", "26", 1, 0),
        ("Notes", "back", 400, "120", "121", 0, 0),
    ]
    return BookSummary(
        title=title,
        authors=("Robert Louis Stevenson",),
        language="en",
        source_format="epub",
        words=sum(s[2] for s in sections),
        sections=tuple(
            SectionSummary(n, t, k, w, first, last, images, notes, 0)
            for n, (t, k, w, first, last, images, notes) in enumerate(sections, start=1)
        ),
    )


def add_book(
    library: Library,
    folder: Path,
    name: str = "jekyll.epub",
    lines: Iterable[str] = (),
    **changes,
) -> str:
    """A book in the store, with whatever record fields `changes` gives it, and these
    progress lines."""
    upload = folder / "upload.partial"
    upload.write_bytes(b"ok")
    record = library.store.create(name, Path(name).suffix, upload)
    library.store.update(record.id, **changes)
    for line in lines:
        library.store.add_line(record.id, line)
    library.store.save_lines(record.id)
    return record.id


CHOSEN = Choices(formats=("m4b", "mp3"), voice="af_heart", speed=0.9, sections=(1, 2, 3, 4))
MAKING_LINES = [
    "Making an audiobook of The Strange Case of Dr Jekyll and Mr Hyde: 4 sections, about "
    "6,042 words, voice af_heart.",
    "Section 1 of 4 done: Title Page. About 12 minutes left.",
    "Section 2 of 4 done: Story of the Door. About 8 minutes left.",
]
# A book that warns about every note and many words: repeats in a row are one line with a
# count, and only the latest lines are shown.
LONG_LINES = [
    "Making an audiobook of A Long Book: 30 sections, about 250,000 words, voice af_heart.",
    *["WARNING: A note in OEBPS/notes.xhtml has no id; reading it as ordinary text."] * 412,
    *[f"WARNING: No pronunciation found for 'Xq{n}', so it will be skipped." for n in range(140)],
    *[f"Section {n} of 30 done: Chapter {n}. About {60 - n} minutes left." for n in range(1, 13)],
]


def render_pages(out_dir: Path) -> dict[str, Path]:
    """Every page in every state, saved as OUT_DIR/NAME.html, with the stylesheet and
    script beside them in OUT_DIR/static. Returns the files by name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        app = sample_app(folder)
        library: Library = app.state.library
        client = visitor(app)
        pages["home-empty"] = client.get("/").text
        pages["home-upload-error"] = client.post(
            "/books", files={"book": ("notes.txt", b"hello", "text/plain")}
        ).text
        summary = sample_summary()
        common = {"summary": summary}
        books = {
            "reading": add_book(library, folder, state="reading"),
            "unreadable": add_book(
                library,
                folder,
                "scan.pdf",
                state="unreadable",
                error="This PDF has no text layer: it is a scan.",
                hint="Run dogear ocr on it first, then upload the new file.",
            ),
            "choose": add_book(library, folder, state="ready", **common),
            "choose-language": add_book(
                library,
                folder,
                "roman.epub",
                state="ready",
                summary=replace(sample_summary("Le Roman"), language="fr"),
            ),
            "making": add_book(
                library, folder, state="making", choices=CHOSEN, lines=MAKING_LINES, **common
            ),
            "making-long": add_book(
                library,
                folder,
                state="making",
                choices=CHOSEN,
                lines=LONG_LINES,
                summary=sample_summary("A Long Book"),
            ),
            "waiting": add_book(library, folder, state="waiting", choices=CHOSEN, **common),
            "done": add_book(library, folder, state="done", choices=CHOSEN, **common),
            "failed": add_book(
                library,
                folder,
                state="failed",
                choices=CHOSEN,
                lines=MAKING_LINES[:1],
                error="ffmpeg isn't installed, or isn't on PATH.",
                hint="Install ffmpeg, then choose Start again.",
                **common,
            ),
            "stopped": add_book(
                library, folder, state="stopped", choices=CHOSEN, lines=MAKING_LINES, **common
            ),
        }
        library.maker.add(books["making"])
        library.maker.add(books["waiting"])
        _made_outputs(library, books["done"])
        for name, book_id in books.items():
            path = f"/books/{book_id}/choose" if name.startswith("choose") else f"/books/{book_id}"
            pages[name] = client.get(path).text
        # Voice and speed always have a value; formats and sections can all be unticked.
        pages["choose-errors"] = client.post(
            f"/books/{books['choose']}/choose", data={"voice": "af_heart", "speed": "0.9"}
        ).text
        pages["choose-language-errors"] = client.post(
            f"/books/{books['choose-language']}/choose",
            data={"format": "m4b", "voice": "af_heart", "speed": "0.9", "section": "1"},
        ).text
        pages["delete"] = client.get(f"/books/{books['done']}/delete").text
        pages.update(_word_pages(app, client, folder))
        pages.update(_listen_pages(app, client))
        pages.update(_pronunciation_pages(app, client))
        pages["home-books"] = client.get("/").text
        pages["home-deleted"] = client.get("/?deleted=1").text
        pages["help"] = client.get("/help").text
        pages["not-found"] = client.get("/no-such-page").text
        stranger = visitor(app, signed_in=False)
        pages["access"] = stranger.get("/").text
        pages["access-error"] = stranger.post("/access", data={"key": "wrong"}).text
    saved = {}
    for name, html in pages.items():
        saved[name] = out_dir / f"{name}.html"
        saved[name].write_text(html, encoding="utf-8")
    shutil.copytree(STATIC, out_dir / "static", dirs_exist_ok=True)
    return saved


# Words a check found, most frequent first. The book has more than the check kept.
CHECKED_WORDS = (
    UnknownWord("Utterson", 131),
    UnknownWord("Lanyon", 40),
    UnknownWord("Poole", 12),
    UnknownWord("Enfield", 9),
)
# More words than the page lists at first, so it links to them all.
MANY_WORDS = (*CHECKED_WORDS, *(UnknownWord(f"Name{n:02d}", 8) for n in range(1, 57)))


def keep_check(library: Library, book_id: str, check: WordCheck) -> None:
    """The book's word check in this state, as a check would leave it."""
    library.words._checks[book_id] = check


def keep_listen(listens: Listens, listen: Listen) -> None:
    """A listen in this state, with its recording if it's done, as saying it would leave it."""
    listens._listens[listen.id] = listen
    if listen.state == "done":
        (listens.folder / f"{listen.id}.wav").write_bytes(b"RIFF" + bytes(44_000))


def _word_pages(app: Starlette, client: TestClient, folder: Path) -> dict[str, str]:
    """A book's "Check how words are said" page in each state."""
    library: Library = app.state.library
    pages = {}
    summary = {"summary": sample_summary()}
    start = add_book(library, folder, state="ready", **summary)
    pages["words-start"] = client.get(f"/books/{start}/words").text
    roman = replace(sample_summary("Le Roman"), language="fr")
    language = add_book(library, folder, "roman.epub", state="ready", summary=roman)
    pages["words-start-language"] = client.get(f"/books/{language}/words").text
    states = {
        "words-waiting": WordCheck("waiting"),
        "words-checking": WordCheck("checking", sections=(2, 3)),
        "words-list": WordCheck("done", words=CHECKED_WORDS, total=64),
        "words-many": WordCheck("done", words=MANY_WORDS, total=len(MANY_WORDS)),
        "words-empty": WordCheck("done", sections=(1,)),
        "words-failed": WordCheck(
            "failed",
            error="This book is marked as being in 'fr', but Dogear's voice only speaks "
            "English so far.",
            hint="If the book is really in English, check its words as English.",
        ),
    }
    books = {}
    for name, check in states.items():
        books[name] = add_book(library, folder, state="done", choices=CHOSEN, **summary)
        keep_check(library, books[name], check)
        pages[name] = client.get(f"/books/{books[name]}/words").text
    pages["words-all"] = client.get(f"/books/{books['words-many']}/words/all").text
    page_words: PageWords = app.state.page_words
    page_words.save({"Lanyon": "lan yon"})
    listed = books["words-list"]
    pages["words-list"] = client.get(f"/books/{listed}/words").text
    pages["words-saved"] = client.get(f"/books/{listed}/words?saved=1").text
    pages["words-errors"] = client.post(
        f"/books/{listed}/words",
        data={
            "word-1": "Utterson",
            "say-1": "utter son " * 30,
            "word-2": "Lanyon",
            "say-2": "lan yon",
            "word-3": "Poole",
            "say-3": "pool\x00",
            "word-4": "Enfield",
            "say-4": "",
        },
    ).text
    pages["words-changed"] = changed_elsewhere(
        client,
        f"/books/{listed}/words",
        "Lanyon",
        "lanny on",
        lambda: page_words.save({"Lanyon": "lan yun"}),
    )
    page_words.save({"Lanyon": ""})
    return pages


def _listen_pages(app: Starlette, client: TestClient) -> dict[str, str]:
    """A Listen's page: waiting, done (the player), failed, and gone."""
    listens: Listens = app.state.listens
    states = {
        "listen-waiting": Listen("1" * 32, "Utterson", "/pronunciations", state="saying"),
        "listen-done": Listen(
            "2" * 32,
            "Mr. Utterson the lawyer.",
            "/books/" + "A" * 16 + "/words#word-1",
            state="done",
            said=("Mister Utter son the lawyer.",),
        ),
        "listen-failed": Listen(
            "3" * 32,
            "Lanyon",
            "/pronunciations#try",
            state="failed",
            error="The voice couldn't be loaded.",
            hint="Check your internet connection, then choose Listen again.",
        ),
    }
    pages = {}
    for name, listen in states.items():
        keep_listen(listens, listen)
        pages[name] = client.get(f"/listen/{listen.id}").text
    pages["listen-gone"] = client.get("/listen/" + "4" * 32).text
    return pages


def _pronunciation_pages(app: Starlette, client: TestClient) -> dict[str, str]:
    """The Pronunciations page: empty, full, and with errors in each form."""
    pages = {"pronunciations-empty": client.get("/pronunciations").text}
    words_file = app.state.settings.words_file
    words_file.write_text('[words]\nLanyon = { phonemes = "lˈænjən" }\n', encoding="utf-8")
    app.state.page_words.save(
        {"Utterson": "utter son", "St. John": "sin jun", "Zoë": "zo ee", "Poole": "pool"}
    )
    pages["pronunciations-full"] = client.get("/pronunciations").text
    pages["pronunciations-added"] = client.get("/pronunciations?done=added").text
    pages["pronunciations-add-errors"] = client.post(
        "/pronunciations/add", data={"word": "--", "spelling": ""}
    ).text
    pages["pronunciations-errors"] = client.post(
        "/pronunciations",
        data={"word-1": "Poole", "say-1": "pool " * 50, "word-2": "St. John", "say-2": ""},
    ).text
    pages["pronunciations-try-error"] = client.post(
        "/pronunciations/try", data={"text": "..."}
    ).text
    pages["pronunciations-changed"] = changed_elsewhere(
        client,
        "/pronunciations",
        "Utterson",
        "otter son",
        lambda: app.state.page_words.save({"Utterson": "utter sun"}),
    )
    words_file.unlink()
    return pages


def save_form(client: TestClient, path: str) -> dict[str, str]:
    """What the Save form on the page at `path` sends as the page comes."""
    page = lxml.html.fromstring(client.get(path).text)
    [form] = page.xpath(f"//form[@action='{path}']")
    return dict(form.form_values())


def changed_elsewhere(
    client: TestClient, path: str, word: str, typed: str, meanwhile: Callable[[], None]
) -> str:
    """The page that Save on the page at `path` gives when `typed` was typed for `word`,
    and `meanwhile` changed words in another window after the page was opened."""
    form = save_form(client, path)
    meanwhile()
    [number] = [
        key[len("word-") :]
        for key, value in form.items()
        if key.startswith("word-") and value == word
    ]
    form[f"say-{number}"] = typed
    return client.post(path, data=form).text


def _made_outputs(library: Library, book_id: str) -> None:
    made = library.folder(book_id) / "made"
    made.mkdir()
    (made / "The Strange Case of Dr Jekyll and Mr Hyde.m4b").write_bytes(b"m" * 3_500_000)
    mp3 = made / "The Strange Case of Dr Jekyll and Mr Hyde MP3"
    mp3.mkdir()
    for n in range(1, 5):
        (mp3 / f"{n:02d}.mp3").write_bytes(b"3" * 900_000)
    library.store.update(
        book_id,
        outputs=[
            Output("m4b", "made/The Strange Case of Dr Jekyll and Mr Hyde.m4b"),
            Output("mp3", "made/The Strange Case of Dr Jekyll and Mr Hyde MP3"),
        ],
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: uv run python tests/web_samples.py OUT_DIR")
    for name, path in render_pages(Path(sys.argv[1])).items():
        print(f"Wrote {name}: {path}")
