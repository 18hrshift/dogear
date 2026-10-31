"""Folders for the web page's books that only this user can open.

Books, what's made from them, and the access key are private. On Linux and macOS the
folders Dogear makes for them are owner-only (0700), and so are the files in them (0600):
each file is written with that mode, and child processes run with a umask that gives it
(child.py). On Windows, folders under the user's profile are private already.
"""

from __future__ import annotations

import os
from pathlib import Path

PRIVATE_FOLDER = 0o700


def private_folder(path: Path, *, tighten: bool = True) -> Path:
    """Make `path`, and any missing folders above it, owner-only. With `tighten`, a
    folder that exists already is made owner-only too: for folders that are Dogear's
    alone, never one a person chose."""
    missing = []
    folder = path
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for folder in reversed(missing):
        folder.mkdir(mode=PRIVATE_FOLDER, exist_ok=True)
    if tighten and os.name != "nt":
        path.chmod(PRIVATE_FOLDER)
    return path
