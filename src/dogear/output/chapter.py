"""One rendered section of the book, as the packagers receive it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChapterAudio:
    """A section's raw audio from the renderer (a WAV file) and the title to show for it."""

    title: str
    path: Path
    # Where each utterance of the section's narration starts, in samples from the start
    # of the file, then the file's length: what talking-book output syncs text to.
    # Empty when unknown, such as for audio Dogear didn't speak.
    marks: tuple[int, ...] = ()
    sample_rate: int = 0  # of `marks`
