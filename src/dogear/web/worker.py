"""A queue of books that runs one job at a time, in order, on its own thread."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable

from dogear.web.child import Stopper

log = logging.getLogger(__name__)

Job = Callable[[str, Stopper], None]  # (book id, its stopper)


class Worker:
    def __init__(self, name: str, job: Job) -> None:
        self._name = name
        self._job = job
        self._changed = threading.Condition()
        self._waiting: deque[str] = deque()
        self._current: tuple[str, Stopper] | None = None
        self._closed = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()

    def add(self, book_id: str) -> None:
        with self._changed:
            if book_id not in self._waiting and self.running() != book_id:
                self._waiting.append(book_id)
                self._changed.notify_all()

    def running(self) -> str | None:
        with self._changed:
            return self._current[0] if self._current else None

    def ahead(self, book_id: str) -> int | None:
        """How many books will run before this one, or None if it isn't waiting."""
        with self._changed:
            if book_id not in self._waiting:
                return None
            return self._waiting.index(book_id) + (1 if self._current else 0)

    def stop(self, book_id: str) -> bool:
        """Take the book out of the queue, or stop it if it's running. False if neither."""
        with self._changed:
            if book_id in self._waiting:
                self._waiting.remove(book_id)
                self._changed.notify_all()
                return True
            if self._current and self._current[0] == book_id:
                self._current[1].stop()
                return True
            return False

    def wait_until_not_running(self, book_id: str, timeout: float) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: self.running() != book_id, timeout=timeout)

    def close(self, timeout: float) -> None:
        """Forget the queue, stop the running job, and wait for the thread to finish."""
        with self._changed:
            self._closed = True
            self._waiting.clear()
            if self._current:
                self._current[1].stop()
            self._changed.notify_all()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while True:
            with self._changed:
                self._changed.wait_for(lambda: self._closed or self._waiting)
                if self._closed:
                    return
                book_id = self._waiting.popleft()
                stopper = Stopper()
                self._current = (book_id, stopper)
            try:
                self._job(book_id, stopper)
            except Exception:  # a bug: log it, and keep serving the other books
                log.exception("The %s job for book %s failed.", self._name, book_id)
            finally:
                with self._changed:
                    self._current = None
                    self._changed.notify_all()
