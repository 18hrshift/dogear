"""Running the `dogear` command as a child process: starting it, reading it, stopping it.

The server runs `dogear outline --json` and `dogear make` this way, so a book file that
crashes or hangs the reader takes down only the child. Children write UTF-8.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# Set for every child: `dogear` then writes its output as UTF-8 (see cli.py).
UTF8_OUTPUT_ENV = "DOGEAR_UTF8_OUTPUT"
# A child asked to stop gets this long to tidy up before it is killed.
STOP_GRACE_SECONDS = 10.0
# Longest output line kept. Longer lines are cut (a traceback can hold a whole sentence).
MAX_LINE_CHARS = 2000


def dogear_command() -> list[str]:
    """How to run `dogear`: this Python with `-m dogear`, or this program itself when it
    is a frozen build (an installer's PyInstaller executable), which is `dogear` already."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "dogear"]


def child_command(args: list[str], config_file: Path | None) -> list[str]:
    """The full command for `dogear ARGS`, with the server's own --config if it has one."""
    command = [*dogear_command(), *args]
    if config_file is not None:
        command += ["--config", str(config_file)]
    return command


def popen_options() -> dict:
    """What every child is started with: UTF-8 text, and no console window on Windows."""
    options: dict = {
        "env": {**os.environ, UTF8_OUTPUT_ENV: "1", "PYTHONIOENCODING": "utf-8"},
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return options


def start_lines(command: list[str]) -> subprocess.Popen[bytes]:
    """Start a child whose stdout and stderr are read together, line by line."""
    return subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **popen_options()
    )


def read_lines(stream: IO[bytes]) -> Iterator[str]:
    """Each line of a child's output, decoded, without its line end, and cut to a bound."""
    while True:
        raw = stream.readline(MAX_LINE_CHARS * 4)
        if not raw:
            return
        if not raw.endswith(b"\n"):
            # The rest of an overlong line is dropped, not shown as lines of its own.
            while (more := stream.readline(64 * 1024)) and not more.endswith(b"\n"):
                pass
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        yield line[:MAX_LINE_CHARS]


@dataclass(frozen=True)
class Captured:
    returncode: int
    stdout: bytes
    stderr: str
    too_long: bool  # stdout went past its limit, so `stdout` is incomplete
    timed_out: bool


def run_captured(
    command: list[str], *, timeout: float, max_stdout: int, stopper: Stopper | None = None
) -> Captured:
    """Run a child to the end, keeping at most `max_stdout` bytes of its stdout."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen_options()
    )
    if stopper is not None:
        stopper.attach(process)
    out = _Collector(process.stdout, max_stdout)
    err = _Collector(process.stderr, 64 * 1024)
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_process(process)
        try:
            process.wait(timeout=STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    finally:
        if stopper is not None:
            stopper.detach()
    out.join()
    err.join()
    return Captured(
        returncode=process.returncode,
        stdout=out.data(),
        stderr=err.data().decode("utf-8", errors="replace"),
        too_long=out.overflowed,
        timed_out=timed_out,
    )


class _Collector:
    """Reads a pipe to its end on a thread, keeping the first `limit` bytes."""

    def __init__(self, stream: IO[bytes] | None, limit: int) -> None:
        self._chunks: list[bytes] = []
        self._kept = 0
        self._limit = limit
        self.overflowed = False
        self._thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self._thread.start()

    def _read(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        with stream:
            while chunk := stream.read(64 * 1024):
                room = self._limit - self._kept
                if len(chunk) > room:
                    self.overflowed = True
                    chunk = chunk[: max(0, room)]
                self._chunks.append(chunk)
                self._kept += len(chunk)

    def join(self) -> None:
        self._thread.join()

    def data(self) -> bytes:
        return b"".join(self._chunks)


def stop_process(process: subprocess.Popen) -> None:
    """Ask a child to stop: Ctrl+C on Linux and macOS, so it tidies up as it does in a
    terminal; on Windows, which has no such signal for a windowless child, end it."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            process.send_signal(signal.SIGINT)
    except OSError:
        pass  # it ended in the meantime


class Stopper:
    """Lets another thread stop whichever child a job is running now, or the next one it
    starts. A child that hasn't stopped after STOP_GRACE_SECONDS is killed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self.requested = threading.Event()

    def attach(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._process = process
            if self.requested.is_set():
                self._stop_locked()

    def detach(self) -> None:
        with self._lock:
            self._process = None

    def stop(self) -> None:
        with self._lock:
            self.requested.set()
            self._stop_locked()

    def _stop_locked(self) -> None:
        process = self._process
        if process is None:
            return
        stop_process(process)
        timer = threading.Timer(STOP_GRACE_SECONDS, _kill_if_running, args=(process,))
        timer.daemon = True
        timer.start()


def _kill_if_running(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
