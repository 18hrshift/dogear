"""The macOS installer: Dogear.app in a .dmg, beside a link to Applications and a read-me.

The app's own program is a short script (launcher.sh) that opens a Terminal window
running `dogear serve`: that window shows the link to open and is how you stop Dogear,
like the console window on Windows. The frozen bundle sits in Contents/Resources/dogear.

The app is unsigned; "Read me first.txt" says how to open it. Signing and notarizing
need an Apple Developer account (see packaging/README.md).
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from dogear_build import BuildError
from dogear_build.fetch import Report

FILES = Path(__file__).resolve().parent.parent / "macos"
APP = "Dogear.app"
EXECUTABLE = "Dogear"
BUNDLE_ID = "io.github.18hrshift.dogear"
README = "Read me first.txt"


def make_app(frozen: Path, folder: Path, version: str, minimum_os: str) -> Path:
    """Dogear.app in `folder`."""
    app = folder / APP
    contents = app / "Contents"
    shutil.rmtree(app, ignore_errors=True)
    shutil.copytree(frozen, contents / "Resources" / "dogear", symlinks=True)
    program = contents / "MacOS" / EXECUTABLE
    program.parent.mkdir(parents=True)
    shutil.copy2(FILES / "launcher.sh", program)
    program.chmod(0o755)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump(info_plist(version, minimum_os), f)
    return app


def info_plist(version: str, minimum_os: str) -> dict[str, str]:
    return {
        "CFBundleName": "Dogear",
        "CFBundleDisplayName": "Dogear",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": EXECUTABLE,
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": minimum_os,
        "NSHumanReadableCopyright": "Apache License 2.0",
    }


def make_dmg(
    frozen: Path, dist: Path, work: Path, name: str, version: str, minimum_os: str, report: Report
) -> Path:
    """dist/<name>.dmg holding Dogear.app, a link to Applications, and the read-me."""
    staging = work / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    make_app(frozen, staging, version, minimum_os)
    os.symlink("/Applications", staging / "Applications")
    shutil.copy2(FILES / README, staging / README)
    output = dist / f"{name}.dmg"
    report(f"Writing {output.name}.")
    command = ["hdiutil", "create", "-volname", "Dogear", "-srcfolder", str(staging)]
    command += ["-fs", "HFS+", "-format", "UDZO", "-ov", str(output)]
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise BuildError(f"hdiutil couldn't make the disk image: {e}") from None
    return output
