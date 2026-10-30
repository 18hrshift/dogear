"""The folder each `dogear make` run works in, under `<cache>/work`, and clearing away the
folders of runs that died.

A run's folder holds its sections' audio until the outputs are built, and is deleted when
the run ends. A run that is killed (the power fails, or the web page ends a child that
didn't stop when asked) can't delete it, and it can hold gigabytes. So each run first
deletes the folders no running `dogear make` is using, from the command line or the web
page alike.

Each run holds a lock on a file in its folder for as long as it runs (file_lock.py), and
the system lets go of it when the run ends, however it ends. A folder whose lock can be
taken is therefore left over, and is deleted. A folder without a lock file is never
touched: it is being set up at this moment, or an older Dogear made it.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from dogear.errors import DogearError
from dogear.file_lock import FileLock

PREFIX = "run-"
LOCK_NAME = "in-use.lock"
ATTEMPTS = 5  # to set up a folder, if other runs clear it away while it's being set up


@contextlib.contextmanager
def work_folder(root: Path) -> Iterator[Path]:
    """A new, empty folder in `root` for this run, deleted when the run ends. Folders that
    runs which died left in `root` are deleted first."""
    root.mkdir(parents=True, exist_ok=True)
    remove_stale(root)
    folder, lock = _new_folder(root)
    try:
        yield folder
    finally:
        lock.release()  # first: Windows can't delete a file that is open
        shutil.rmtree(folder, ignore_errors=True)


def remove_stale(root: Path) -> list[Path]:
    """Delete every run's folder in `root` that no running `dogear make` holds. Returns
    the folders deleted."""
    removed = []
    for folder in sorted(root.glob(PREFIX + "*")):
        if folder.is_symlink() or not folder.is_dir():
            continue
        lock = FileLock.try_acquire(folder / LOCK_NAME, create=False)
        if lock is None:
            continue  # in use, or being set up
        try:
            # While the lock is held here, a run setting this folder up can't take it.
            shutil.rmtree(folder, ignore_errors=True)
        finally:
            lock.release()
        shutil.rmtree(folder, ignore_errors=True)  # the lock file too, on Windows
        removed.append(folder)
    return removed


def _new_folder(root: Path) -> tuple[Path, FileLock]:
    """A new folder in `root` and the lock on it. Its lock file exists unlocked for a
    moment, when another run's remove_stale can take it and clear the folder away; that
    shows as a lock that isn't taken, or isn't on the file any more, and a new folder is
    made instead."""
    for _ in range(ATTEMPTS):
        folder = Path(tempfile.mkdtemp(prefix=PREFIX, dir=root))
        try:
            lock = FileLock.try_acquire(folder / LOCK_NAME)
        except FileNotFoundError:
            continue  # cleared away already
        if lock is not None and lock.is_current():
            return folder, lock
        if lock is not None:
            lock.release()
    raise DogearError(
        f"Dogear couldn't set up a folder to work in, in {root}.",
        hint="Run the command again. If this keeps happening, delete that folder.",
    )
