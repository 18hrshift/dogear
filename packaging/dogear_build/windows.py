"""The Windows installer, made with Inno Setup from windows/dogear.iss.

Inno Setup was chosen over NSIS. Both build their wizards from standard Windows controls,
which screen readers read, and both install per user without administrator rights. But
NSIS's usual build caps strings at 1024 characters, which is known to cut a long PATH
short when an installer edits it, and Inno Setup comes installed on GitHub's Windows
runners. Inno Setup is free to use; since 6.5 its makers ask commercial users to buy a
license, which doesn't apply to this project.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from dogear_build import BuildError
from dogear_build.fetch import Report

SCRIPT = Path(__file__).resolve().parent.parent / "windows" / "dogear.iss"
# Where Inno Setup 6 installs ISCC, its compiler, when it isn't on PATH.
ISCC_FOLDERS = [
    r"%ProgramFiles(x86)%\Inno Setup 6",
    r"%ProgramFiles%\Inno Setup 6",
    r"%LOCALAPPDATA%\Programs\Inno Setup 6",
]


def make_setup(frozen: Path, dist: Path, name: str, version: str, report: Report) -> Path:
    """dist/<name>.exe, the installer."""
    report(f"Writing {name}.exe with Inno Setup.")
    command = [
        find_iscc(),
        f"/DAppVersion={version}",
        f"/DBundleDir={frozen}",
        f"/DOutputDir={dist}",
        f"/DOutputBaseName={name}",
        str(SCRIPT),
    ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        raise BuildError(f"Inno Setup failed (exit code {e.returncode}).") from None
    return dist / f"{name}.exe"


def find_iscc() -> str:
    found = shutil.which("ISCC")
    if found:
        return found
    for folder in ISCC_FOLDERS:
        path = Path(os.path.expandvars(folder)) / "ISCC.exe"
        if path.is_file():
            return str(path)
    raise BuildError(
        "Inno Setup's compiler (ISCC.exe) wasn't found. Install Inno Setup 6 from "
        "https://jrsoftware.org/isdl.php, or put ISCC.exe on PATH."
    )
