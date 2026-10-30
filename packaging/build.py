"""Build Dogear's standalone bundle and installer for this computer's platform.

    uv run --no-dev --group installer python packaging/build.py

It downloads and checks the pinned sources (pins.toml), builds ffmpeg and espeak-ng,
freezes Dogear with PyInstaller, adds those programs, the default voice, and the
licenses, and makes the installer. Downloads and the built programs are kept in
build/packaging and reused by the next build. It saves dist/dogear (the bundle) and the
installer: dist/Dogear-<version>-<platform>.tar.gz, .dmg, or -setup.exe.

packaging/README.md says what each platform needs to build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dogear_build import BuildError
from dogear_build.assemble import assemble
from dogear_build.fetch import Report
from dogear_build.freeze import freeze
from dogear_build.linux import make_tarball
from dogear_build.macos import make_dmg
from dogear_build.pins import load, platform_key
from dogear_build.programs import build_programs
from dogear_build.windows import make_setup

from dogear import __version__
from dogear.errors import DogearError

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Dogear's installer for this platform.")
    parser.add_argument(
        "--work",
        type=Path,
        default=ROOT / "build" / "packaging",
        help="folder for downloads and intermediate files (default: build/packaging)",
    )
    parser.add_argument(
        "--dist", type=Path, default=ROOT / "dist", help="folder to save in (default: dist)"
    )
    parser.add_argument(
        "--bundle-only", action="store_true", help="make the bundle but not the installer"
    )
    args = parser.parse_args(argv)
    try:
        saved = build(args.work.resolve(), args.dist.resolve(), not args.bundle_only, _report)
    except BuildError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except DogearError as e:  # from Dogear's own code, such as a failed download
        print(f"Error: {e.message}", file=sys.stderr)
        if e.hint:
            print(f"What to do: {e.hint}", file=sys.stderr)
        return 1
    print(f"Saved: {saved}")
    return 0


def build(work: Path, dist: Path, installer: bool, report: Report) -> Path:
    pins = load()
    platform = platform_key()
    settings = pins.platform(platform)
    downloads = work / "downloads"
    programs = build_programs(pins, platform, downloads, work, report)
    frozen = freeze(work, dist, report)
    assemble(frozen, programs, platform, pins, downloads, work / "voice", report)
    if not installer:
        return frozen
    name = f"Dogear-{__version__}-{platform}"
    system = platform.split("-")[0]
    if system == "linux":
        return make_tarball(frozen, dist, name, report)
    if system == "macos":
        return make_dmg(frozen, dist, work, name, __version__, settings["minimum_os"], report)
    return make_setup(frozen, dist, f"{name}-setup", __version__, report)


def _report(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
