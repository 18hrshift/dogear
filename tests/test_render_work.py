"""The folders `dogear make` works in: each run's own, and clearing away those of runs
that died without ever touching one a running `dogear make` is using."""

import subprocess
import sys
from pathlib import Path

from dogear.file_lock import FileLock
from dogear.render import work
from dogear.render.work import LOCK_NAME, PREFIX, remove_stale, work_folder

# A `dogear make` stand-in: holds a work folder until it's killed.
RUN = """
import sys, time
from pathlib import Path
from dogear.render.work import work_folder
with work_folder(Path(sys.argv[1])) as folder:
    (folder / "section.wav").write_bytes(b"x" * 1000)
    print(folder, flush=True)
    time.sleep(60)
"""


def start_run(root):
    process = subprocess.Popen(
        [sys.executable, "-c", RUN, str(root)], stdout=subprocess.PIPE, text=True
    )
    folder = process.stdout.readline().strip()
    assert folder, "the run didn't start"
    return process, Path(folder)


def stop_run(process):
    process.kill()  # like a power cut: the run can't tidy up
    process.wait()
    process.stdout.close()


def stale_folder(root, name="run-old", with_lock=True):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "section.wav").write_bytes(b"x")
    if with_lock:
        (folder / LOCK_NAME).write_bytes(b"")
    return folder


def test_a_run_gets_its_own_folder_and_deletes_it(tmp_path):
    with work_folder(tmp_path / "work") as folder:
        assert folder.parent == tmp_path / "work"
        assert folder.name.startswith(PREFIX)
        assert FileLock.try_acquire(folder / LOCK_NAME) is None  # held by this run
        (folder / "a.wav").write_bytes(b"x")
    assert not folder.exists()


def test_a_folder_left_by_a_run_that_died_is_deleted_by_the_next_run(tmp_path):
    root = tmp_path / "work"
    old = stale_folder(root)
    with work_folder(root) as folder:
        assert not old.exists()
        assert [p for p in root.iterdir()] == [folder]


def test_a_folder_in_use_by_another_run_is_kept_until_that_run_dies(tmp_path):
    root = tmp_path / "work"
    other, theirs = start_run(root)
    try:
        assert theirs.is_dir()
        with work_folder(root):
            assert (theirs / "section.wav").exists()
        assert remove_stale(root) == []
        assert (theirs / "section.wav").exists()
    finally:
        stop_run(other)
    assert theirs.exists()  # killed, so it couldn't delete its folder
    assert remove_stale(root) == [theirs]
    assert not theirs.exists()


def test_folders_without_a_lock_file_are_never_touched(tmp_path):
    """Such a folder is being set up at this moment, or an older Dogear made it."""
    root = tmp_path / "work"
    setting_up = stale_folder(root, "run-new", with_lock=False)
    older = stale_folder(root, "tmpabc123", with_lock=False)
    assert remove_stale(root) == []
    assert setting_up.exists() and older.exists()


def test_a_folder_cleared_away_while_being_set_up_is_replaced(tmp_path, monkeypatch):
    """Another run took the new folder's lock first: this run makes another folder."""
    real = FileLock.try_acquire
    tries = []

    def acquire(path, **options):
        tries.append(path)
        return None if len(tries) == 1 else real(path, **options)

    monkeypatch.setattr(work.FileLock, "try_acquire", acquire)
    with work_folder(tmp_path / "work") as folder:
        assert folder == tries[-1].parent
        assert len(tries) == 2
