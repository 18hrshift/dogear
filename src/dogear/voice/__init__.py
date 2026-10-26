"""Voices: turning sentences into audio.

`engine.py` defines what every engine provides. Kokoro is the built-in engine; its model
files are downloaded on first use and checked against `catalog.toml`.
"""

from __future__ import annotations

from dataclasses import dataclass

from dogear.config import Config
from dogear.errors import VoiceError
from dogear.paths import models_dir
from dogear.tools import find_tool
from dogear.voice.catalog import (
    VoiceInfo,
    catalog,
    kokoro_file,
    kokoro_voices,
    spacy_model_dir,
    spacy_wheel,
)
from dogear.voice.downloads import RemoteFile, Report, ensure_files
from dogear.voice.engine import VoiceEngine
from dogear.voice.spacy_model import unpack_spacy_model

ENGINES = ("kokoro",)


@dataclass(frozen=True)
class KokoroSetup:
    voice: VoiceInfo
    model: RemoteFile
    tokenizer: RemoteFile
    voice_file: RemoteFile


def make_engine(config: Config, report: Report) -> VoiceEngine:
    """The configured voice, downloading its files first if needed."""
    # Checked first, so a missing program is reported before a long download.
    espeak = find_tool("espeak_ng", config)
    setup = prepare_kokoro(config, report)

    from dogear.voice.g2p import EnglishG2P
    from dogear.voice.kokoro import KokoroEngine

    models = models_dir(config)
    kokoro = catalog()["kokoro"]
    return KokoroEngine(
        model=setup.model.path,
        tokenizer=setup.tokenizer.path,
        voice=setup.voice_file.path,
        g2p=EnglishG2P(spacy_model_dir(models), setup.voice.british, espeak),
        speed=config["voice"]["speed"],
        threads=config["kokoro"]["threads"],
        sample_rate=kokoro["sample_rate"],
        max_phonemes=kokoro["max_phonemes"],
        identity=f"kokoro|{setup.model.sha256}|{setup.voice_file.sha256}",
    )


def prepare_kokoro(config: Config, report: Report) -> KokoroSetup:
    """Check the voice settings and make sure every file the voice needs is on disk."""
    _check_engine(config)
    voice = find_voice(config["voice"]["voice"])
    build = config["kokoro"]["model"]
    builds = catalog()["kokoro"]["models"]
    if build not in builds:
        raise VoiceError(
            f"kokoro.model is '{build}', which isn't a Kokoro model build.",
            hint=f"Use one of: {', '.join(builds)}.",
        )
    models = models_dir(config)
    setup = KokoroSetup(
        voice=voice,
        model=kokoro_file("model", build, models),
        tokenizer=kokoro_file("tokenizer", "", models),
        voice_file=kokoro_file("voice", voice.name, models),
    )
    needed = [setup.model, setup.tokenizer, setup.voice_file]
    if not spacy_model_dir(models).is_dir():
        needed.append(spacy_wheel(models))
    ensure_files(needed, config, report)
    unpack_spacy_model(models)
    return setup


def find_voice(name: str) -> VoiceInfo:
    for voice in kokoro_voices():
        if voice.name == name:
            return voice
    raise VoiceError(
        f"There's no voice called '{name}'.",
        hint="Run `dogear voices` to list them.",
    )


def _check_engine(config: Config) -> None:
    engine = config["voice"]["engine"]
    if engine not in ENGINES:
        raise VoiceError(
            f"voice.engine is '{engine}', which Dogear doesn't have.",
            hint=f"Use one of: {', '.join(ENGINES)}.",
        )
