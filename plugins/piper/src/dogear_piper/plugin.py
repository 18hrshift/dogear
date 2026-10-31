"""Piper as a Dogear voice engine: what the `dogear.engines` entry point gives Dogear.

This package's pyproject.toml registers `ENGINE`. Importing this module is cheap: Piper
and onnxruntime load only when a voice is made.
"""

from __future__ import annotations

from importlib import resources

from dogear.config import Config
from dogear.paths import models_dir
from dogear.pronunciations import PronunciationDictionary
from dogear.voice.downloads import Report, ensure_downloaded
from dogear.voice.engine import VoiceEngine
from dogear.voice.engines import Voice

from dogear_piper.catalog import PiperFiles, piper_voices, voice_files


class PiperPlugin:
    name = "piper"
    title = "Piper"
    license = "GPL-3.0-or-later"
    # Piper reads eSpeak NG's phonemes, not misaki's, so phoneme entries don't apply.
    reads_misaki_phonemes = False
    about_voices = (
        "Highest quality first. Quality is Piper's measure of a voice's size and detail, "
        "not a rating."
    )

    @property
    def settings(self) -> str:
        return resources.files("dogear_piper").joinpath("settings.toml").read_text(encoding="utf-8")

    def voices(self) -> list[Voice]:
        return piper_voices()

    def prepare(self, config: Config, voice: Voice, report: Report) -> None:
        prepare_piper(config, voice.name, report)

    def engine(
        self,
        config: Config,
        voice: Voice,
        pronunciations: PronunciationDictionary,
        report: Report,
    ) -> VoiceEngine:
        files = prepare_piper(config, voice.name, report)

        from dogear_piper.engine import PiperEngine

        return PiperEngine(
            model=files.model.path,
            config=files.config.path,
            speed=config["voice"]["speed"],
            threads=config["piper"]["threads"],
            identity=f"piper|{files.model.sha256}|{files.config.sha256}",
        )


ENGINE = PiperPlugin()


def prepare_piper(config: Config, name: str, report: Report) -> PiperFiles:
    """The voice's files, downloading whichever aren't on disk yet."""
    models = models_dir(config)
    files = voice_files(name, models)
    ensure_downloaded([files.model, files.config], models, config, report)
    return files
