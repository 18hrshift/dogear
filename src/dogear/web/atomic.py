"""Writing a file whole or not at all."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

PARTIAL_SUFFIX = ".partial"
# On Windows, a file another program has open (a Dogear child reading it, or a virus
# checker looking at it) can't be replaced: the rename fails with PermissionError. Such
# programs usually let go within moments, so the rename is tried this many times, this
# far apart: about 2 seconds in all.
REPLACE_TRIES = 9
REPLACE_PAUSE_SECONDS = 0.25


class FileInUse(PermissionError):
    """The file couldn't be replaced, even after trying for a while: another program had
    it open, or (rarely, on Linux and macOS) Dogear isn't allowed to replace it."""


def write_atomically(path: Path, data: bytes, check: Callable[[Path], None] | None = None) -> None:
    """Write `data` to a new temporary file beside `path`, then rename it over `path`.
    The temporary name is one no other writer uses, and the file is readable by this
    user only (on Linux and macOS). Nothing is left behind if writing fails.

    `check`, if given, is called with the temporary file before the rename. If it
    raises, `path` is left as it was. Raises FileInUse if `path` can't be replaced."""
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=PARTIAL_SUFFIX
    )
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        if check is not None:
            check(Path(temporary))
        _replace(Path(temporary), path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _replace(source: Path, target: Path) -> None:
    for attempt in range(1, REPLACE_TRIES + 1):
        try:
            os.replace(source, target)
            return
        except PermissionError as e:
            if attempt == REPLACE_TRIES:
                raise FileInUse(e.errno, e.strerror, str(target)) from e
            time.sleep(REPLACE_PAUSE_SECONDS)


def remove_leftovers(folder: Path, name: str) -> None:
    """Delete temporary files a process that died left beside `folder / name`."""
    for leftover in folder.glob(f".{name}.*{PARTIAL_SUFFIX}"):
        leftover.unlink(missing_ok=True)
