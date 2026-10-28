"""A stand-in voice for running `dogear make` without the Kokoro model."""

import hashlib

import numpy as np

from dogear.voice.engine import SpeechPlan

RATE = 24000


class HumEngine:
    """A voice that hums each sentence for a tenth of a second per word."""

    sample_rate = RATE

    def __init__(self) -> None:
        self.rendered: list[str] = []

    def plan(self, text: str) -> SpeechPlan:
        return SpeechPlan(key=hashlib.sha256(text.encode()).hexdigest(), payload=text)

    def render(self, plan: SpeechPlan) -> np.ndarray:
        self.rendered.append(plan.payload)
        seconds = 0.1 * len(plan.payload.split())
        t = np.arange(int(RATE * seconds)) / RATE
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
