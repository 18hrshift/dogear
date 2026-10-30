"""A child process together with every process it starts, so the server can stop them all.

On Linux and macOS the child starts a new session, so it leads a process group of its
own. Ctrl+C in the server's terminal then reaches only the server, which decides when
its children stop, and stopping signals the whole group, so ffmpeg and espeak-ng stop
with `dogear`. On Windows the child is put in a Job object (windows_job.py) for the same
reason; Ctrl+C in the server's console doesn't reach children there already, because
they run without a console window.
"""

from __future__ import annotations

import os
import signal
import subprocess

from dogear.web.windows_job import Job

# The exit code of a child stopped as if by Ctrl+C. Windows children ended through their
# job get it too, so every system reports a stop the same way.
INTERRUPTED = 130


def popen_options() -> dict:
    """What a child is started with to make it a tree of its own."""
    return {} if os.name == "nt" else {"start_new_session": True}


class ProcessTree:
    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._job = Job.adopt(process.pid) if os.name == "nt" else None

    def interrupt(self) -> None:
        """Ask every process in the tree to stop: Ctrl+C on Linux and macOS, so `dogear`
        tidies up as it does in a terminal. Windows has no such signal for a child
        without a console, so there they are ended."""
        if self._ended():
            return
        if self._job is not None:
            self._job.terminate(INTERRUPTED)
        else:
            self._signal_group(signal.SIGINT)

    def kill(self) -> None:
        """End every process in the tree now."""
        if self._ended():
            return
        if self._job is not None:
            self._job.terminate(INTERRUPTED)
        else:
            self._signal_group(signal.SIGKILL)

    def close(self) -> None:
        """Once the child has ended: end anything it left running, and let go of the
        tree. On Linux and macOS the group outlives its leader while any process in it
        runs, so its number can't belong to anything else then."""
        if self._job is not None:
            self._job.close()
        else:
            self._signal_group(signal.SIGKILL)

    def _ended(self) -> bool:
        """Whether the child has ended and been waited for already."""
        return self._process.returncode is not None

    def _signal_group(self, number: int) -> None:
        try:
            os.killpg(self._process.pid, number)
        except OSError:
            pass  # every process in the group has ended
