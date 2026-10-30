"""Put the bundle together: the frozen program, then the programs and the default voice
where `dogear.bundle` looks for them, then the licenses beside the program.

    dogear/
      dogear (dogear.exe on Windows)
      LICENSE.txt, THIRD-PARTY-NOTICES.txt
      _internal/                      PyInstaller's folder (freeze.CONTENTS)
        bundled/tools/                ffmpeg, ffprobe, espeak-ng, espeak-ng-data
        bundled/models/               the default voice, and manifest.json
"""

from __future__ import annotations

import shutil
from pathlib import Path

from dogear import bundle
from dogear_build import BuildError
from dogear_build.fetch import Report
from dogear_build.freeze import CONTENTS
from dogear_build.notices import NAME as NOTICES
from dogear_build.notices import write_notices
from dogear_build.pins import Pins
from dogear_build.programs import program_names
from dogear_build.voice import bundle_voice

ROOT = Path(__file__).resolve().parents[2]


def assemble(
    frozen: Path,
    programs: Path,
    platform: str,
    pins: Pins,
    downloads: Path,
    voice_cache: Path,
    report: Report,
) -> None:
    folder = frozen / CONTENTS / bundle.FOLDER
    if not folder.parent.is_dir():
        raise BuildError(f"{folder.parent} is missing: was {frozen} made by this build?")
    shutil.rmtree(folder, ignore_errors=True)
    tools = folder / bundle.TOOLS
    tools.mkdir(parents=True)
    for name in program_names(platform):
        shutil.copy2(programs / name, tools / name)
    shutil.copytree(programs / bundle.ESPEAK_DATA, tools / bundle.ESPEAK_DATA)
    report("Adding the default voice.")
    spacy_model = bundle_voice(voice_cache, folder / bundle.MODELS, report)
    shutil.copy2(ROOT / "LICENSE", frozen / "LICENSE.txt")
    write_notices(frozen / NOTICES, pins, downloads, spacy_model)
