"""A record of the files Dogear wrote into an output folder, so it only ever touches its own.

The record (`.dogear.json`, hidden on macOS and Linux) names the book and each file Dogear
made in the folder. With it:

- a run for the same book replaces its earlier files and removes ones that no longer
  belong (a chapter renamed or dropped), so stale tracks don't play in the middle;
- a run for a different book stops with an error instead of mixing two books;
- a file Dogear didn't make is never overwritten or deleted.
"""

from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path
from typing import Any

from dogear.document import Metadata
from dogear.errors import OutputFolderError

RECORD_NAME = ".dogear.json"
_FORMAT_VERSION = 1


def claim_folder(folder: Path, metadata: Metadata, names: list[str]) -> list[str]:
    """Check that Dogear may write `names` into `folder`, and record that it is about to.

    Returns the files from an earlier run that this run doesn't rewrite. Pass them to
    `finish_folder` once every new file is written.
    """
    book = _book(metadata)
    old = _read_record(folder)
    if old is not None and not _same_book(old["book"], book):
        raise OutputFolderError(
            f"The folder {folder} already holds Dogear audio for another book, "
            f'"{old["book"]["title"]}".',
            hint="Choose a different folder for this book, or delete the other book's "
            "files from it first.",
        )
    owned: list[str] = old["files"] if old else []
    owned_keys = {_key(name) for name in owned}
    for name in names:
        if (folder / name).exists() and _key(name) not in owned_keys:
            raise OutputFolderError(
                f'The folder {folder} already has a file named "{name}" that Dogear didn\'t make.',
                hint="Move or rename that file, or choose a different folder. Dogear never "
                "replaces files it didn't make.",
            )
    new_keys = {_key(name) for name in names}
    stale = [name for name in owned if _key(name) not in new_keys]
    # Recorded before any audio is written, so an interrupted run's files still count
    # as Dogear's next time.
    _write_record(folder, book, owned + [n for n in names if _key(n) not in owned_keys])
    return stale


def finish_folder(folder: Path, metadata: Metadata, names: list[str], stale: list[str]) -> None:
    """Remove the earlier run's leftover files and record exactly what the folder now holds."""
    for name in stale:
        path = folder / name
        if path.is_file():
            path.unlink()
    _write_record(folder, _book(metadata), names)


def _book(metadata: Metadata) -> dict[str, Any]:
    return {
        "title": metadata.title,
        "authors": list(metadata.authors),
        "identifier": metadata.identifier,
    }


def _same_book(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if old.get("identifier") and new.get("identifier"):
        return old["identifier"] == new["identifier"]
    return old["title"] == new["title"] and old["authors"] == new["authors"]


def _key(name: str) -> str:
    # Windows and macOS treat names that differ only in case or Unicode form as the same file.
    return unicodedata.normalize("NFC", name).casefold()


def _read_record(folder: Path) -> dict[str, Any] | None:
    path = folder / RECORD_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if not _valid_record(data):
        raise OutputFolderError(
            f"Dogear's list of the files it made in {folder} ({RECORD_NAME}) is damaged.",
            hint=f"Choose a different folder, or empty this one (including {RECORD_NAME}).",
        )
    return data


def _valid_record(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    book, files = data.get("book"), data.get("files")
    return (
        isinstance(book, dict)
        and isinstance(book.get("title"), str)
        and isinstance(book.get("authors"), list)
        and all(isinstance(a, str) for a in book["authors"])
        and isinstance(book.get("identifier"), str | None)
        and isinstance(files, list)
        and all(_plain_name(name) for name in files)
    )


def _plain_name(name: Any) -> bool:
    # A bare file name inside the folder: the record must never point anywhere else.
    return (
        isinstance(name, str)
        and name not in ("", ".", "..", RECORD_NAME)
        and not any(char in name for char in "/\\:\x00")
    )


def _write_record(folder: Path, book: dict[str, Any], files: list[str]) -> None:
    record = {"made_by": "Dogear", "version": _FORMAT_VERSION, "book": book, "files": files}
    partial = folder / (RECORD_NAME + ".partial")
    partial.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(partial, folder / RECORD_NAME)
