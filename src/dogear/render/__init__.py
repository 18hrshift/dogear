"""Speaking a narrated book: one WAV per section, built sentence by sentence.

Each sentence is planned by the voice engine, taken from the speech cache if it was made
before, and rendered otherwise. Sentences and the pauses between them are written
straight to the section's WAV file, so memory use doesn't grow with the book.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from dogear.config import Config
from dogear.narration import SectionNarration
from dogear.output import ChapterAudio
from dogear.paths import cache_dir
from dogear.render.cache import SpeechCache
from dogear.render.progress import Progress, Report
from dogear.render.wav import WavWriter, to_pcm16, trim_edges
from dogear.voice.engine import VoiceEngine


def render_book(
    narrations: list[SectionNarration],
    engine: VoiceEngine,
    config: Config,
    work_dir: Path,
    report: Report,
    progress: Progress | None = None,
) -> list[ChapterAudio]:
    """One WAV per narrated section in `work_dir`, in order."""
    settings = config["render"]
    cache = SpeechCache(cache_dir(config) / "speech", engine.sample_rate)
    progress = progress or Progress(
        total_words=sum(n.words() for n in narrations),
        total_sections=len(narrations),
        every_seconds=settings["progress_every_seconds"],
        report=report,
    )
    chapters = []
    for index, narration in enumerate(narrations, start=1):
        path = work_dir / f"{index:03d}.wav"
        title = narration.section.title
        with WavWriter(path, engine.sample_rate) as out:
            for utterance in narration.utterances:
                if utterance.spoken:
                    samples = _speak(utterance.spoken, engine, cache, progress)
                    trimmed = trim_edges(
                        samples,
                        engine.sample_rate,
                        settings["edge_silence_db"],
                        settings["edge_silence_keep_ms"],
                    )
                    out.audio(trimmed)
                    progress.check_in(index, title)
                out.silence(utterance.pause_ms)
        chapters.append(ChapterAudio(title=title, path=path))
        progress.section_done(index, title)
    return chapters


def _speak(text: str, engine: VoiceEngine, cache: SpeechCache, progress: Progress) -> np.ndarray:
    plan = engine.plan(text)
    words = len(text.split())
    cached = cache.get(plan.key)
    if cached is not None:
        progress.sentence(words, cached=True)
        return cached
    started = time.monotonic()
    samples = to_pcm16(engine.render(plan))
    cache.put(plan.key, samples)
    progress.sentence(words, cached=False, seconds=time.monotonic() - started)
    return samples
