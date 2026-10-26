"""Rendered sentences on disk, so a crash resumes and a fix re-renders only what changed.

Each sentence's audio is stored under its plan key, which already covers the engine,
model, voice, settings, and the exact input. Files are written under a temporary name
and renamed when complete, so a crash never leaves a half-written entry behind.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from dogear.render.wav import read_wav, write_wav


class SpeechCache:
    def __init__(self, root: Path, sample_rate: int) -> None:
        self.root = root
        self.sample_rate = sample_rate

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.wav"

    def get(self, key: str) -> np.ndarray | None:
        path = self.path(key)
        if not path.is_file():
            return None
        samples, rate = read_wav(path)
        return samples if rate == self.sample_rate else None

    def put(self, key: str, samples: np.ndarray) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f"{path.stem}.{os.getpid()}.part")
        write_wav(partial, samples, self.sample_rate)
        os.replace(partial, path)
