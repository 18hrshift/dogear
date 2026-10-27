"""Unpack spaCy's English model from its downloaded wheel into the models folder.

The wheel is checked against its pinned SHA-256 before this runs. Only the model folder
inside it is kept; the Python package around it is never installed or imported.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from dogear.errors import DownloadError
from dogear.voice.catalog import catalog, spacy_model_dir, spacy_wheel


def unpack_spacy_model(models_dir: Path) -> Path:
    """The unpacked model folder, unpacking the downloaded wheel first if needed."""
    target = spacy_model_dir(models_dir)
    if target.is_dir():
        return target
    wheel = spacy_wheel(models_dir).path
    staging = target.with_name(target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    prefix = catalog()["spacy"]["model_dir"] + "/"
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.startswith(prefix):
                continue
            relative = PurePosixPath(member.filename[len(prefix) :])
            # A drive ("C:") or backslash in a part could escape the folder on Windows.
            if relative.is_absolute() or any(
                part == ".." or ":" in part or "\\" in part for part in relative.parts
            ):
                raise DownloadError(f"{wheel.name} contains an unsafe path: {member.filename}")
            destination = staging.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as out:
                shutil.copyfileobj(source, out)
    if not (staging / "config.cfg").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise DownloadError(f"{wheel.name} doesn't contain the spaCy model Dogear expected.")
    os.replace(staging, target)
    wheel.unlink()
    return target
