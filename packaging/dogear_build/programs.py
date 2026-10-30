"""Build ffmpeg, ffprobe, and espeak-ng for this platform with `build-programs.sh`.

The result is kept and reused while the script and the pinned archives stay the same.
On Windows the script runs in MSYS2's UCRT64 shell (see packaging/README.md).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from platform import libc_ver
from typing import Any

from dogear_build import BuildError
from dogear_build.fetch import Report, fetch
from dogear_build.pins import Pins

SCRIPT = Path(__file__).resolve().parent.parent / "build-programs.sh"
ARCHIVES = ("lame", "ffmpeg", "espeak-ng", "sonic")  # in the order the script takes them
STAMP = "built-from.txt"
MSYS2_DEFAULT = r"C:\msys64"


def build_programs(pins: Pins, platform: str, downloads: Path, work: Path, report: Report) -> Path:
    """A folder holding ffmpeg, ffprobe, espeak-ng, and espeak-ng-data for `platform`."""
    archives = [fetch(pins.sources[key], downloads, report) for key in ARCHIVES]
    settings = pins.platform(platform)
    out = work / "programs"
    fingerprint = _fingerprint(pins, settings)
    stamp = out / STAMP
    if stamp.is_file() and stamp.read_text(encoding="utf-8") == fingerprint:
        report("Using the programs built before.")
        return out
    report("Building ffmpeg and espeak-ng from source. This takes several minutes.")
    command = [*_bash(), _script_path(), *map(str, archives), str(work / "programs-work"), str(out)]
    try:
        subprocess.run(command, check=True, env=_environment(settings))
    except subprocess.CalledProcessError as e:
        raise BuildError(f"Building the programs failed (exit code {e.returncode}).") from None
    stamp.write_text(fingerprint, encoding="utf-8")
    return out


def program_names(platform: str) -> list[str]:
    """The program files a build of the programs holds on `platform`."""
    suffix = ".exe" if platform.startswith("windows") else ""
    return [f"{name}{suffix}" for name in ("ffmpeg", "ffprobe", "espeak-ng")]


def _fingerprint(pins: Pins, settings: dict[str, Any]) -> str:
    """What the programs were built from and for: the script, the archives, the platform
    settings, and the C library they link to (so a build in an older Linux container
    doesn't reuse programs built for the newer one outside it)."""
    digest = hashlib.sha256(SCRIPT.read_bytes())
    for key in ARCHIVES:
        digest.update(pins.sources[key].sha256.encode())
    digest.update(repr(sorted(settings.items())).encode())
    digest.update(repr(libc_ver()).encode())
    return digest.hexdigest()


def _bash() -> list[str]:
    if os.name != "nt":
        return ["bash"]
    root = Path(os.environ.get("DOGEAR_MSYS2") or MSYS2_DEFAULT)
    bash = root / "usr" / "bin" / "bash.exe"
    if not bash.is_file():
        raise BuildError(
            f"MSYS2 wasn't found at {root}. Install it from https://www.msys2.org, or set "
            "DOGEAR_MSYS2 to its folder. packaging/README.md lists the packages it needs."
        )
    # -l: a login shell, which puts UCRT64's compilers on PATH (MSYSTEM, set below).
    return [str(bash), "-l"]


def _script_path() -> str:
    # MSYS2's bash reads C:/like/this; forward slashes work on every platform.
    return SCRIPT.as_posix()


def _environment(settings: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ, JOBS=str(os.cpu_count() or 2))
    if "minimum_os" in settings:
        env["MACOSX_DEPLOYMENT_TARGET"] = settings["minimum_os"]
    if os.name == "nt":
        env.update(MSYSTEM="UCRT64", CHERE_INVOKING="1")
    return env
