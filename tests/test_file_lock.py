"""The file lock that keeps two Dogear processes off one folder."""

import os
import subprocess
import sys
import threading
import time

import pytest

from dogear.file_lock import FileLock

HOLDER = """
import sys, time
from pathlib import Path
from dogear.file_lock import FileLock
lock = FileLock.try_acquire(Path(sys.argv[1]))
print("held" if lock else "busy", flush=True)
time.sleep(60)
"""


def test_a_lock_is_held_until_released(tmp_path):
    path = tmp_path / "x.lock"
    first = FileLock.try_acquire(path)
    assert first is not None
    assert FileLock.try_acquire(path) is None  # another open, in this same process
    first.release()
    first.release()  # twice is harmless
    with FileLock.try_acquire(path) as again:
        assert again is not None
    assert FileLock.try_acquire(path) is not None


def test_another_process_holds_it_until_it_dies(tmp_path):
    path = tmp_path / "x.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        assert FileLock.try_acquire(path) is None
    finally:
        holder.kill()  # no tidying up: the system lets go of the lock
        holder.wait()
        holder.stdout.close()
    lock = acquire_soon(path)
    assert lock is not None
    lock.release()


def acquire_soon(path, seconds: float = 10):
    """The lock, once the system lets go of a dead holder's. Windows may take a moment."""
    deadline = time.monotonic() + seconds
    while (lock := FileLock.try_acquire(path)) is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return lock


def test_wait_for_waits_until_the_holder_lets_go(tmp_path):
    path = tmp_path / "x.lock"
    calls = []
    with FileLock.wait_for(path, lambda: calls.append("waiting")):
        pass
    assert calls == []  # no one else had it: no wait
    holder = FileLock.try_acquire(path)
    threading.Timer(0.5, holder.release).start()
    started = time.monotonic()
    lock = FileLock.wait_for(path, lambda: calls.append("waiting"), poll_seconds=0.05)
    assert time.monotonic() - started >= 0.4
    assert calls == ["waiting"]  # said once, however long the wait
    lock.release()


def test_without_create_a_missing_file_is_not_made(tmp_path):
    path = tmp_path / "missing.lock"
    assert FileLock.try_acquire(path, create=False) is None
    assert not path.exists()
    path.write_bytes(b"")
    lock = FileLock.try_acquire(path, create=False)
    assert lock is not None
    lock.release()


@pytest.mark.skipif(os.name == "nt", reason="Windows doesn't delete a file that is open")
def test_a_lock_knows_when_its_file_was_deleted(tmp_path):
    path = tmp_path / "x.lock"
    lock = FileLock.try_acquire(path)
    assert lock.is_current()
    path.unlink()
    assert not lock.is_current()
    path.write_bytes(b"")  # a new file with the same name isn't the locked one
    assert not lock.is_current()
    lock.release()
    assert not lock.is_current()


@pytest.mark.skipif(os.name == "nt", reason="file modes are for Linux and macOS")
def test_the_lock_file_is_private(tmp_path):
    path = tmp_path / "x.lock"
    FileLock.try_acquire(path).release()
    assert path.stat().st_mode & 0o777 == 0o600
