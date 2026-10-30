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
from dataclasses import replace
from pathlib import Path

from starlette.applications import Starlette
from starlette.testclient import TestClient

from dogear.book_summary import BookSummary, SectionSummary
from dogear.config import Config, default_config
from dogear.web.access_key import AccessKey
from dogear.web.app import STATIC, create_app
from dogear.web.books import Choices, Output
from dogear.web.library import Library
from dogear.web.settings import WebSettings, web_settings

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


def add_book(library: Library, folder: Path, name: str = "jekyll.epub", **changes) -> str:
    """A book in the store, with whatever record fields `changes` gives it."""
    upload = folder / "upload.partial"
    upload.write_bytes(b"ok")
    record = library.store.create(name, Path(name).suffix, upload)
    library.store.update(record.id, **changes)
    return record.id


CHOSEN = Choices(formats=("m4b", "mp3"), voice="af_heart", speed=0.9, sections=(1, 2, 3, 4))
MAKING_LINES = [
    "Making an audiobook of The Strange Case of Dr Jekyll and Mr Hyde: 4 sections, about "
    "6,042 words, voice af_heart.",
    "Section 1 of 4 done: Title Page. About 12 minutes left.",
    "Section 2 of 4 done: Story of the Door. About 8 minutes left.",
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
