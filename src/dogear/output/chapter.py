"""One rendered section of the book, as the packagers receive it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChapterAudio:
    """A section's raw audio from the renderer (a WAV file) and the title to show for it."""

    title: str
    path: Path
