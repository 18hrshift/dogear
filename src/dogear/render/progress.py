"""Progress for long renders, as occasional plain sentences a screen reader can read.

No spinners, bars, or rewritten lines: each report is one complete line, printed when a
section finishes and at most every few minutes in between.
"""

from __future__ import annotations

import time
from collections.abc import Callable

Report = Callable[[str], None]


class Progress:
    def __init__(
        self,
        total_words: int,
        total_sections: int,
        every_seconds: float,
        report: Report,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total_words = total_words
        self.total_sections = total_sections
        self.every_seconds = every_seconds
        self.report = report
        self.clock = clock
        self.started = clock()
        self.last_report = self.started
        self.words_done = 0
        self.new_words = 0  # words rendered now, not taken from the cache
        self.render_seconds = 0.0
        self.new_sentences = 0
        self.cached_sentences = 0

    def sentence(self, words: int, *, cached: bool, seconds: float = 0.0) -> None:
        self.words_done += words
        if cached:
            self.cached_sentences += 1
        else:
            self.new_sentences += 1
            self.new_words += words
            self.render_seconds += seconds

    def check_in(self, number: int, title: str) -> None:
        """Report how a long section is going, if it's been a while since the last line."""
        if self.clock() - self.last_report < self.every_seconds:
            return
        percent = round(100 * self.words_done / max(1, self.total_words))
        self._say(
            f"Working on section {number} of {self.total_sections}, {title}. "
            f"{percent}% of the book done.{self._time_left()}"
        )

    def section_done(self, number: int, title: str) -> None:
        self._say(f"Section {number} of {self.total_sections} done: {title}.{self._time_left()}")

    def summary(self) -> str:
        took = describe_duration(self.clock() - self.started)
        parts = [f"{self.new_sentences:,} new"]
        if self.cached_sentences:
            parts.append(f"{self.cached_sentences:,} already made in an earlier run")
        total = self.new_sentences + self.cached_sentences
        return f"Spoke {_count(total, 'sentence')} ({', '.join(parts)}) in {took}."

    def _time_left(self) -> str:
        if self.new_words == 0 or self.render_seconds < 1:
            return ""
        remaining = max(0, self.total_words - self.words_done)
        seconds = remaining * self.render_seconds / self.new_words
        if not remaining:
            return ""
        if seconds < 60:
            return " Less than a minute left."
        return f" About {describe_duration(seconds)} left."

    def _say(self, line: str) -> None:
        self.last_report = self.clock()
        self.report(line)


def describe_duration(seconds: float) -> str:
    """'2 hours 5 minutes', '1 minute', or 'less than a minute'."""
    minutes = round(seconds / 60)
    if minutes < 1:
        return "less than a minute"
    hours, minutes = divmod(minutes, 60)
    parts = [_count(hours, "hour")] if hours else []
    if minutes:
        parts.append(_count(minutes, "minute"))
    return " ".join(parts)


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"
