"""Writing a file whole or not at all, and waiting out a program that has it open, as
Windows refuses to replace a file another program has open. The refusal is simulated."""

import errno
import os

import pytest

from dogear.web import atomic
from dogear.web.atomic import REPLACE_TRIES, FileInUse, write_atomically


@pytest.fixture
def pauses(monkeypatch):
    """The pauses between tries, recorded instead of waited."""
    waited = []
    monkeypatch.setattr(atomic.time, "sleep", waited.append)
    return waited


def refuse_replacing(monkeypatch, path, times: int, error: OSError) -> list[str]:
    """os.replace onto `path` fails with `error` the first `times` times. Returns what
    each try was."""
    real_replace = os.replace
    tries = []

    def replace(source, target):
        if os.fspath(target) == os.fspath(path):
            tries.append("refused" if len(tries) < times else "replaced")
            if tries[-1] == "refused":
                raise error
        real_replace(source, target)

    monkeypatch.setattr(atomic.os, "replace", replace)
    return tries


def in_use() -> PermissionError:
    return PermissionError(errno.EACCES, "The process cannot access the file")


def test_a_file_let_go_of_within_moments_is_replaced(tmp_path, monkeypatch, pauses):
    path = tmp_path / "words.toml"
    path.write_bytes(b"old")
    tries = refuse_replacing(monkeypatch, path, 2, in_use())
    write_atomically(path, b"new")
    assert tries == ["refused", "refused", "replaced"]
    assert pauses == [atomic.REPLACE_PAUSE_SECONDS] * 2
    assert path.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["words.toml"]


def test_a_file_kept_open_is_file_in_use_after_about_two_seconds(tmp_path, monkeypatch, pauses):
    path = tmp_path / "words.toml"
    path.write_bytes(b"old")
    tries = refuse_replacing(monkeypatch, path, REPLACE_TRIES, in_use())
    with pytest.raises(FileInUse) as error:
        write_atomically(path, b"new")
    assert isinstance(error.value, PermissionError)
    assert error.value.filename == str(path)
    assert len(tries) == REPLACE_TRIES
    assert 1.5 <= sum(pauses) <= 2.5
    assert path.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["words.toml"]  # nothing left behind


def test_other_errors_are_not_tried_again(tmp_path, monkeypatch, pauses):
    path = tmp_path / "words.toml"
    tries = refuse_replacing(monkeypatch, path, 1, OSError(errno.ENOSPC, "No space left"))
    with pytest.raises(OSError) as error:
        write_atomically(path, b"new")
    assert not isinstance(error.value, FileInUse)
    assert tries == ["refused"]
    assert pauses == []
