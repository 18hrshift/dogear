"""The child's side: a `dogear` started by `dogear serve` stops when the server ends.

Children run in a process tree of their own (process_tree.py), so the server's end
doesn't reach them by itself: closing the terminal window, for one, ends only the server.
So the server keeps each child's stdin open and never writes to it. The end of stdin
means the server has gone, however it went, and the child then stops as if by Ctrl+C,
tidying up as it would in a terminal.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections.abc import Callable

# Set by the server for every child; the child then watches its stdin.
STOP_WITH_SERVER_ENV = "DOGEAR_STOP_WITH_SERVER"
# A child that hasn't stopped this long after the server ended (busy in code that
# Ctrl+C doesn't reach) ends at once.
GRACE_SECONDS = 10.0
INTERRUPTED = 130


def stop_with_server_when_asked() -> None:
    """In `dogear`'s main: watch for the server's end, if a server started this."""
    if os.environ.get(STOP_WITH_SERVER_ENV) == "1" and sys.stdin is not None:
        watch(sys.stdin.fileno())


def ctrl_c() -> None:
    """Press Ctrl+C for this process's main thread, so it also stops waiting for whatever
    it waits for (a sleep, a program it runs). _thread.interrupt_main() alone would let
    it finish that first. On Linux and macOS a SIGINT is sent to the main thread. On
    Windows, raising SIGINT runs Python's handler here, as a real Ctrl+C does, and that
    wakes the main thread's waits that watch for Ctrl+C. (If it still doesn't stop, the
    server's Job object ends it: windows_job.py.)"""
    if os.name == "nt":
        signal.raise_signal(signal.SIGINT)
    else:
        signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)


def watch(
    descriptor: int,
    interrupt: Callable[[], None] = ctrl_c,
    end: Callable[[int], None] = os._exit,
    grace: float = GRACE_SECONDS,
) -> threading.Thread:
    """Read the file `descriptor` to its end on a thread, then `interrupt` (Ctrl+C for
    the main thread), and `end` the process if it is still running `grace` seconds later.
    It reads the descriptor itself, not sys.stdin: a thread waiting in sys.stdin holds
    its lock, which stops Python from shutting down."""

    def run() -> None:
        try:
            while os.read(descriptor, 4096):
                pass  # the server writes nothing; anything else is ignored
        except OSError:
            pass  # a broken pipe is the end too
        interrupt()
        time.sleep(grace)
        end(INTERRUPTED)

    thread = threading.Thread(target=run, name="server-watch", daemon=True)
    thread.start()
    return thread
