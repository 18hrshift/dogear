"""The pinned list of files Dogear downloads for its built-in voice (`catalog.toml`)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from dogear.voice.downloads import RemoteFile

_GRADE_ORDER = "ABCDF"


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


def kokoro_voices_best_first() -> list[VoiceInfo]:
    return sorted(kokoro_voices(), key=lambda v: _grade_rank(v.grade))


def _grade_rank(grade: str) -> tuple[int, int]:
    """Sort key for grades such as "A", "B-", or "C+": best first."""
    return _GRADE_ORDER.index(grade[0]), {"+": -1, "-": 1}.get(grade[1:], 0)


def describe_voice(voice: VoiceInfo) -> str:
    """'af_heart: American English, female, grade A'"""
    return f"{voice.name}: {voice.accent} English, {voice.gender}, grade {voice.grade}"


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
    return RemoteFile(
        url=f"{kokoro['base_url']}/{path}",
        sha256=sha256,
        size=size,
        path=models_dir / "kokoro" / path,
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
    return models_dir / "spacy" / Path(catalog()["spacy"]["model_dir"]).name
