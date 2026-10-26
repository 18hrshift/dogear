"""What every voice engine provides, so the renderer never depends on a particular one.

Rendering is split in two. `plan` is cheap: it turns text into the engine's input (for
Kokoro, phonemes) and a cache key. `render` is the slow part that makes audio. The
renderer plans every sentence, then renders only those whose key isn't cached yet, so a
changed pronunciation re-renders just the sentences it touches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class SpeechPlan:
    # Equal keys must mean identical audio: the key covers the engine, model, voice,
    # settings, and the prepared input below.
    key: str
    payload: str  # the engine's own input, such as phonemes


class VoiceEngine(Protocol):
    sample_rate: int

    def plan(self, text: str) -> SpeechPlan:
        """Prepare one sentence of spoken text. Fast; no audio yet."""
        ...

    def render(self, plan: SpeechPlan) -> np.ndarray:
        """Audio for a plan: mono float32 samples in [-1, 1] at `sample_rate`."""
        ...
