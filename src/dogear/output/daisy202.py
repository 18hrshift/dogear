"""A DAISY 2.02 talking book: a folder with an NCC, SMIL files, the text, and the audio.

Not built yet; this is the contract `make.py` calls.
"""

from __future__ import annotations

from pathlib import Path

from dogear.config import Config
from dogear.document import Metadata
from dogear.readalong.model import SectionText


def build_daisy202(
    sections: list[SectionText], metadata: Metadata, folder: Path, config: Config
) -> None:
    """Write the talking book into `folder`, creating it if needed.

    `sections` come from `readalong.build_readalong`, in reading order, each with its
    loudness-normalized WAV and the syncs that tie its text to that audio. Files Dogear
    didn't make in `folder` are left alone (see `folder_record`).
    """
    raise NotImplementedError("DAISY 2.02 output is not built yet")
