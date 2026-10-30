"""The pinned list of files Dogear downloads for its built-in voice (`catalog.toml`).

Each file lives in the models folder, unless a standalone build carries the same file
(same SHA-256): then that read-only copy is used and nothing is downloaded.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from dogear import bundle
from dogear.voice.downloads import RemoteFile


@dataclass(frozen=True)
class VoiceInfo:
    name: str
    accent: str  # "American" or "British"
    gender: str
    grade: str  # Kokoro's own quality grade, A best

    @property
    def british(self) -> bool:
        return self.accent == "British"


@cache
def catalog() -> dict[str, Any]:
    text = resources.files("dogear.voice").joinpath("catalog.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def kokoro_voices() -> list[VoiceInfo]:
    return [
        VoiceInfo(name, v["accent"], v["gender"], v["grade"])
        for name, v in catalog()["kokoro"]["voices"].items()
    ]


def kokoro_file(kind: str, name: str, models_dir: Path) -> RemoteFile:
    """A Kokoro file: kind "model" (name is a build such as "full"), "voice", or "tokenizer"."""
    kokoro = catalog()["kokoro"]
    if kind == "model":
        entry = kokoro["models"][name]
        path, sha256, size = entry["path"], entry["sha256"], entry["size"]
    elif kind == "voice":
        path, sha256 = f"voices/{name}.bin", kokoro["voices"][name]["sha256"]
        size = 1 << 20  # each voice is about half a megabyte
    elif kind == "tokenizer":
        entry = kokoro["tokenizer"]
        path, sha256, size = entry["path"], entry["sha256"], entry["size"]
    else:
        raise ValueError(f"unknown Kokoro file kind: {kind}")
    relative = f"kokoro/{path}"
    return RemoteFile(
        url=f"{kokoro['base_url']}/{path}",
        sha256=sha256,
        size=size,
        path=bundle.model(relative, sha256) or models_dir / relative,
    )


def spacy_wheel(models_dir: Path) -> RemoteFile:
    spacy = catalog()["spacy"]
    return RemoteFile(
        url=spacy["url"],
        sha256=spacy["sha256"],
        size=spacy["size"],
        path=models_dir / "downloads" / spacy["url"].rsplit("/", 1)[-1],
    )


def spacy_model_dir(models_dir: Path) -> Path:
    """The unpacked model folder. A bundled one is known by the SHA-256 of its wheel."""
    spacy = catalog()["spacy"]
    relative = f"spacy/{Path(spacy['model_dir']).name}"
    return bundle.model(relative, spacy["sha256"]) or models_dir / relative
