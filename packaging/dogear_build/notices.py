"""THIRD-PARTY-NOTICES.txt: each third-party part of the bundle, its license in full, and
where its source code is.

Plain text with short labelled lines, read top to bottom, so it works with a screen
reader. Python packages are found by walking Dogear's requirements in the environment
doing the build, the one PyInstaller freezes, and their license files come from their
own metadata, so the list can't drift from what is installed.
"""

from __future__ import annotations

import sys
import sysconfig
import tarfile
from importlib import metadata
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from dogear_build import BuildError
from dogear_build.pins import Pins, Source

NAME = "THIRD-PARTY-NOTICES.txt"
_LICENSE_WORDS = ("LICEN", "COPYING", "NOTICE")
_KOKORO = [
    "Kokoro-82M: the model, its tokenizer, and the af_heart voice",
    "License: Apache-2.0, the same license text as Dogear's own, in LICENSE.txt",
    "By: hexgrad, https://huggingface.co/hexgrad/Kokoro-82M",
    "Converted to ONNX by: onnx-community, "
    "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX",
    "",
]


def write_notices(path: Path, pins: Pins, downloads: Path, spacy_model: Path) -> None:
    """Write the notices for a bundle whose spaCy model folder is `spacy_model`."""
    dogear = metadata.distribution("dogear")
    parts = [
        f"Third-party notices for Dogear {dogear.version}",
        "",
        "Dogear itself is free software under the Apache License 2.0, in LICENSE.txt",
        "beside this file. This copy of Dogear also holds the software and data below.",
        "Each part keeps its own license, given in full after it.",
        "",
        "Contents:",
        "1. Programs Dogear runs: FFmpeg, built with LAME, and eSpeak NG.",
        "2. The voice: Kokoro-82M and spaCy's English model.",
        "3. Python and the Python packages Dogear uses.",
        "4. PyInstaller's bootloader, which starts Dogear.",
        _heading("1. Programs Dogear runs"),
        "Dogear runs these as separate programs; they are not part of Dogear's own code.",
        "They were built with packaging/build-programs.sh, in Dogear's source code at",
        f"{_home_page(dogear)}",
        "",
    ]
    for source in pins.sources.values():
        if source.bundled:
            parts += _program(source, downloads / source.archive_name)
    parts += [_heading("2. The voice"), *_KOKORO, *_spacy_model(spacy_model)]
    parts += [_heading("3. Python and Python packages"), *_python()]
    for dist in runtime_distributions():
        parts += _package(dist)
    parts += [_heading("4. PyInstaller's bootloader"), *_pyinstaller()]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def runtime_distributions(root: str = "dogear") -> list[metadata.Distribution]:
    """Every installed package Dogear needs to run, found by following requirements."""
    found: dict[str, metadata.Distribution] = {}
    waiting = [root]
    while waiting:
        name = canonicalize_name(waiting.pop())
        if name in found:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            raise BuildError(f"{name} is required but not installed. Run uv sync.") from None
        found[name] = dist
        for line in dist.requires or []:
            requirement = Requirement(line)
            # Extras aren't installed, and markers can rule a requirement out on this platform.
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            waiting.append(requirement.name)
    del found[canonicalize_name(root)]
    return sorted(found.values(), key=lambda d: canonicalize_name(d.metadata["Name"]))


def license_files(dist: metadata.Distribution) -> list[metadata.PackagePath]:
    """A package's license texts: its licenses folder (PEP 639) and any file named like one."""
    files = []
    for file in dist.files or []:
        in_licenses_folder = len(file.parts) > 2 and file.parts[1] == "licenses"
        named_like_one = any(word in file.name.upper() for word in _LICENSE_WORDS)
        if (in_licenses_folder or named_like_one) and file.suffix not in (".py", ".pyc"):
            files.append(file)
    return sorted(files, key=str)


def license_name(dist: metadata.Distribution) -> str:
    """The license as the package declares it, short enough for one line."""
    meta = dist.metadata
    if meta.get("License-Expression"):
        return meta["License-Expression"]
    declared = (meta.get("License") or "").strip()
    if declared and "\n" not in declared and len(declared) <= 100:
        return declared
    classifiers = [
        c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    return ", ".join(classifiers) or "as given in the license text below"


def _heading(text: str) -> str:
    return f"\n{text}\n{'=' * len(text)}\n"


def _program(source: Source, archive: Path) -> list[str]:
    lines = [
        f"{source.name} {source.version}",
        f"License: {source.license}",
        f"In this copy: {source.bundled}",
        f"Home page: {source.homepage}",
        f"Source code, exactly as built: {source.url}",
        f"SHA-256 of that file: {source.sha256}",
        "",
    ]
    for name in source.license_files:
        lines += [f"--- {source.name}: {name} ---", _archive_member(archive, name), ""]
    return lines


def _archive_member(archive: Path, name: str) -> str:
    """A file from a source archive's top folder, as text."""
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if len(parts) == 2 and parts[1] == name and member.isfile():
                data = tar.extractfile(member)
                assert data is not None
                return data.read().decode("utf-8", errors="replace").strip()
    raise BuildError(f"{archive.name} has no {name}; fix license_files in pins.toml.")


def _spacy_model(folder: Path) -> list[str]:
    lines = [
        f"spaCy's English model, {folder.name}",
        "License: MIT",
        "By: Explosion, https://github.com/explosion/spacy-models",
        "",
    ]
    for name in ("LICENSE", "LICENSES_SOURCES"):
        text = (folder / name).read_text(encoding="utf-8", errors="replace").strip()
        lines += [f"--- spaCy's English model: {name} ---", text, ""]
    return lines


def _python() -> list[str]:
    version = ".".join(map(str, sys.version_info[:3]))
    candidates = [
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",  # Linux and macOS
        Path(sys.base_prefix) / "LICENSE.txt",  # Windows
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        raise BuildError("Python's LICENSE.txt wasn't found, so its notice can't be written.")
    return [
        f"Python {version}",
        "License: PSF-2.0; its text also covers the parts Python includes",
        "Home page: https://www.python.org",
        "",
        "--- Python: LICENSE.txt ---",
        found.read_text(encoding="utf-8", errors="replace").strip(),
        "",
    ]


def _package(dist: metadata.Distribution) -> list[str]:
    lines = [f"{dist.metadata['Name']} {dist.version}", f"License: {license_name(dist)}"]
    home = _home_page(dist)
    if home:
        lines.append(f"Home page: {home}")
    return [*lines, "", *_license_texts(dist)]


def _pyinstaller() -> list[str]:
    dist = metadata.distribution("pyinstaller")
    return [
        f"PyInstaller {dist.version}",
        "License: GPL-2.0-or-later, with an exception that lets the programs it builds,",
        "such as this one, use any license. Its bootloader is the program that starts Dogear.",
        "Home page: https://pyinstaller.org",
        "",
        *_license_texts(dist),
    ]


def _license_texts(dist: metadata.Distribution) -> list[str]:
    name = dist.metadata["Name"]
    files = license_files(dist)
    if not files:
        # Some packages ship without their license file (flatbuffers, Apache-2.0, does).
        return [
            f"No license file came with {name}. Its license is {license_name(dist)}; the",
            "Apache License 2.0 text is in LICENSE.txt, and other licenses' texts are at",
            "https://spdx.org/licenses",
            "",
        ]
    lines = []
    for file in files:
        text = Path(file.locate()).read_text(encoding="utf-8", errors="replace").strip()
        lines += [f"--- {name}: {PurePosixPath(*file.parts[1:])} ---", text, ""]
    return lines


def _home_page(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    if meta.get("Home-page"):
        return meta["Home-page"]
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository"):
            return url.strip()
    return ""
