"""The Linux installer: a .tar.gz holding the bundle, install.sh, uninstall.sh, and a
read-me. install.sh puts Dogear in ~/.local/opt and adds it to the applications menu with
a .desktop file that opens a terminal window running `dogear serve`.

Chosen over an AppImage: an AppImage usually needs FUSE 2 (libfuse2), which Ubuntu stopped
installing by default in 22.04, and it can't open a terminal window by itself, while a
.desktop file with Terminal=true lets the desktop open its own terminal.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from dogear_build.fetch import Report

FILES = Path(__file__).resolve().parent.parent / "linux"
SCRIPTS = ("install.sh", "uninstall.sh")


def make_tarball(frozen: Path, dist: Path, name: str, report: Report) -> Path:
    """dist/<name>.tar.gz, unpacking to a folder <name>."""
    output = dist / f"{name}.tar.gz"
    report(f"Writing {output.name}.")
    with tarfile.open(output, "w:gz", compresslevel=6) as tar:
        tar.add(frozen, arcname=f"{name}/dogear", filter=_owned_by_root)
        for script in SCRIPTS:
            tar.add(FILES / script, arcname=f"{name}/{script}", filter=_executable)
        tar.add(FILES / "README.txt", arcname=f"{name}/README.txt", filter=_owned_by_root)
    return output


def _owned_by_root(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """No build machine user names or ids in the archive."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def _executable(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.mode = 0o755
    return _owned_by_root(info)
