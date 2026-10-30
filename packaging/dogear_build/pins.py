"""`packaging/pins.toml`: the platforms installers are built for, and the source archives
they download, each pinned by SHA-256. Checked as it's read, so a mistake there stops the
build at the start."""

from __future__ import annotations

import platform
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dogear_build import BuildError

PINS = Path(__file__).resolve().parent.parent / "pins.toml"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ARCHIVES = (".tar.gz", ".tar.xz")
_SYSTEMS = {"linux": "linux", "darwin": "macos", "win32": "windows"}
_MACHINES = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    version: str
    license: str
    homepage: str
    url: str
    mirrors: tuple[str, ...]
    sha256: str
    size: int
    license_files: tuple[str, ...]  # inside the archive's top folder
    bundled: str  # what of it the bundle holds; empty if it's only used to build

    @property
    def archive_name(self) -> str:
        """The file name to keep it under: unique per pin, whatever the URL is called."""
        extension = next(e for e in _ARCHIVES if self.url.endswith(e))
        return f"{self.key}-{self.version[:12]}-{self.sha256[:12]}{extension}"


@dataclass(frozen=True)
class Pins:
    platforms: dict[str, dict[str, Any]]
    sources: dict[str, Source]

    def platform(self, key: str) -> dict[str, Any]:
        if key not in self.platforms:
            raise BuildError(
                f"Installers aren't built for {key}. They are built for: "
                f"{', '.join(self.platforms)}."
            )
        return self.platforms[key]


def load(path: Path = PINS) -> Pins:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sources = {key: _source(key, entry) for key, entry in data["sources"].items()}
    return Pins(platforms=data["platforms"], sources=sources)


def _source(key: str, entry: dict[str, Any]) -> Source:
    source = Source(
        key=key,
        name=entry["name"],
        version=entry["version"],
        license=entry["license"],
        homepage=entry["homepage"],
        url=entry["url"],
        mirrors=tuple(entry.get("mirrors", [])),
        sha256=entry["sha256"],
        size=entry["size"],
        license_files=tuple(entry["license_files"]),
        bundled=entry["bundled"],
    )
    for url in (source.url, *source.mirrors):
        if not url.startswith("https://") or not url.endswith(_ARCHIVES):
            raise BuildError(
                f"pins.toml: {key} has {url}; use an https URL to a .tar.gz or .tar.xz."
            )
    if not _SHA256.fullmatch(source.sha256):
        raise BuildError(f"pins.toml: {key}'s sha256 must be 64 lowercase hex digits.")
    if source.size <= 0:
        raise BuildError(f"pins.toml: {key}'s size must be its size in bytes.")
    if source.bundled and not source.license_files:
        raise BuildError(f"pins.toml: {key} is bundled, so list its license_files.")
    return source


def platform_key() -> str:
    """This machine, named the way pins.toml names platforms, such as linux-x86_64."""
    system = _SYSTEMS.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    return f"{system}-{_MACHINES.get(machine, machine)}"
