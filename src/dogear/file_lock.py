"""An exclusive lock on a file, held for as long as this process keeps it.

Keeps two Dogear processes off one folder: a second `dogear serve` off a web folder in
use, `dogear make` off a work folder another run is using, and a second download into
the models folder until the first is done. The operating system releases the lock when
the file is closed or the process ends, however it ends, so a crash never leaves a
folder locked.

On Linux and macOS it is flock(2), which also holds between two opens of the file in one
process. On Windows it is a lock on the file's first byte (msvcrt.locking).
"""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# What locking a file someone else has locked fails with, on each system.
HELD_ELSEWHERE = {
    errno.EACCES,
    errno.EAGAIN,
    errno.EWOULDBLOCK,
    getattr(errno, "EDEADLOCK", errno.EDEADLK),
}


class FileLock:
    def __init__(self, path: Path, descriptor: int) -> None:
        self.path = path
        self._descriptor: int | None = descriptor

    @classmethod
    def try_acquire(cls, path: Path, *, create: bool = True) -> FileLock | None:
        """The lock on `path`, or None if another holder has it. With create=False, also
        None if there is no such file, which is then left uncreated."""
        flags = os.O_RDWR | (os.O_CREAT if create else 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileNotFoundError:
            if create:
                raise
            return None
        try:
            _lock(descriptor)
        except OSError as e:
            os.close(descriptor)
            if e.errno in HELD_ELSEWHERE:
                return None
            raise
        return cls(path, descriptor)

    @classmethod
    def wait_for(
        cls, path: Path, waiting: Callable[[], None], poll_seconds: float = 0.25
    ) -> FileLock:
        """The lock on `path`, waiting for as long as another holder keeps it. `waiting`
        is called once, before the wait, if there is one."""
        lock = cls.try_acquire(path)
        if lock is None:
            waiting()
            while (lock := cls.try_acquire(path)) is None:
                time.sleep(poll_seconds)
        return lock

    def is_current(self) -> bool:
        """Whether `path` is still the file this lock is on: not deleted or replaced."""
        if self._descriptor is None:
            return False
        try:
            return os.path.samestat(os.fstat(self._descriptor), os.stat(self.path))
        except OSError:
            return False

    def release(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        try:
            _unlock(descriptor)
        finally:
            os.close(descriptor)

    def __enter__(self) -> FileLock:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


def _lock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
