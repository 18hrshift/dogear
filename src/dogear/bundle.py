"""What a standalone build of Dogear carries with it: programs and the default voice.

The installers (see `packaging/`) freeze Dogear with PyInstaller and put ffmpeg, ffprobe,
espeak-ng, and the default voice in a folder beside the frozen code. This module says
where that folder is and what it holds. Run from a normal Python install, every answer
is None, so those installs find programs and download voice files exactly as before.

The build checks each voice file against `catalog.toml` and writes its SHA-256 into the
manifest. A bundled file is used only when the manifest's SHA-256 is the one Dogear
expects, so nothing is hashed again when Dogear starts.
"""

from __future__ import annotations

import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any

FOLDER = "bundled"  # inside the folder PyInstaller unpacks to (sys._MEIPASS)
TOOLS = "tools"  # programs, and espeak-ng's data beside espeak-ng
MODELS = "models"  # laid out like the per-user models folder
MANIFEST = "manifest.json"  # in MODELS: {"files": {relative path: {"sha256": ...}}}
ESPEAK_DATA = "espeak-ng-data"


def folder() -> Path | None:
    """The bundled folder, when Dogear runs from a standalone build."""
    if not getattr(sys, "frozen", False):
        return None
    # PyInstaller names its folder in sys._MEIPASS; other freezers keep files by the program.
    base = getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent
    return Path(base) / FOLDER


def program(name: str) -> Path | None:
    """The bundled copy of the program `name` (such as "ffmpeg"), if this build has one."""
    root = folder()
    if root is None:
        return None
    path = root / TOOLS / (name + (".exe" if os.name == "nt" else ""))
    return path if path.is_file() else None


def espeak_data(espeak: str) -> Path | None:
    """The folder to give espeak-ng with --path, when `espeak` is the bundled espeak-ng.

    That folder holds espeak-ng-data. Any other espeak-ng finds its own data.
    """
    bundled = program("espeak-ng")
    if bundled is None or Path(espeak).resolve() != bundled.resolve():
        return None
    return bundled.parent


def program_environment() -> dict[str, str] | None:
    """The environment to run another program in: None (Dogear's own) in a normal install.

    A standalone build on Linux starts with LD_LIBRARY_PATH pointing into its own folder,
    so its Python finds the libraries it carries; PyInstaller keeps the value from before
    in LD_LIBRARY_PATH_ORIG. A program inheriting that, such as Tesseract or Calibre,
    would load Dogear's older copies of libraries like libstdc++ in place of its own, so
    it gets the value from before back, or none.
    """
    if folder() is None:
        return None
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        env.pop("LD_LIBRARY_PATH", None)
    else:
        env["LD_LIBRARY_PATH"] = original
    return env


def model(relative: str, sha256: str) -> Path | None:
    """The bundled voice file or unpacked model folder at `relative` (a path inside the
    models folder, with / between parts), if it is the one whose SHA-256 is `sha256`.

    For a folder unpacked from a download, the SHA-256 is the download's.
    """
    root = folder()
    if root is None:
        return None
    entry = _manifest(root).get(relative)
    if entry is None or entry["sha256"] != sha256:
        return None
    path = root / MODELS / relative
    return path if path.exists() else None


@cache
def _manifest(root: Path) -> dict[str, Any]:
    path = root / MODELS / MANIFEST
    if not path.is_file():
        return {}  # a build without bundled voice files
    return json.loads(path.read_text(encoding="utf-8"))["files"]
