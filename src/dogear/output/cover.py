"""The book's cover image, ready to hand to ffmpeg as an attached picture."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from dogear.document import Cover

log = logging.getLogger(__name__)

# File signature -> (file extension, ffmpeg demuxer that reads only that image format).
_FORMATS = {
    b"\xff\xd8\xff": (".jpg", "jpeg_pipe"),
    b"\x89PNG\r\n\x1a\n": (".png", "png_pipe"),
}


@dataclass(frozen=True)
class CoverInput:
    path: Path
    demuxer: str

    def input_args(self) -> list[str]:
        """ffmpeg arguments that add the cover as an input."""
        # Naming the demuxer stops ffmpeg from guessing the format, so a cover from an
        # untrusted book can't be read as a playlist or anything else that opens files.
        return ["-f", self.demuxer, "-i", str(self.path)]


def write_cover(cover: Cover | None, directory: Path) -> CoverInput | None:
    """Write the cover into `directory` for ffmpeg. None when there is no usable cover."""
    if cover is None:
        return None
    for signature, (extension, demuxer) in _FORMATS.items():
        if cover.data.startswith(signature):
            path = directory / f"cover{extension}"
            path.write_bytes(cover.data)
            return CoverInput(path, demuxer)
    log.warning(
        "The cover image (said to be %s) isn't a JPEG or PNG file, so it was left out.",
        cover.media_type,
    )
    return None
