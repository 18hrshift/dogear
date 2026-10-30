"""Writing a file whole or not at all."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PARTIAL_SUFFIX = ".partial"


def write_atomically(path: Path, data: bytes) -> None:
    """Write `data` to a new temporary file beside `path`, then rename it over `path`.
    The temporary name is one no other writer uses, and the file is readable by this
    user only (on Linux and macOS). Nothing is left behind if writing fails."""
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=PARTIAL_SUFFIX
    )
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def remove_leftovers(folder: Path, name: str) -> None:
    """Delete temporary files a process that died left beside `folder / name`."""
    for leftover in folder.glob(f".{name}.*{PARTIAL_SUFFIX}"):
        leftover.unlink(missing_ok=True)
