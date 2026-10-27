"""Stand-ins for Kokoro's model files and onnxruntime, so no test loads the real voice."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

STYLE_WIDTH = 256


def write_tokenizer(path: Path, symbols: str) -> dict[str, int]:
    """A tokenizer.json in the shape Kokoro's has. Ids start at 1; 0 is the pad."""
    vocab = {"$": 0, **{symbol: i for i, symbol in enumerate(symbols, start=1)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": {"vocab": vocab}}), encoding="utf-8")
    return vocab


def write_voice(path: Path, rows: int) -> None:
    """A voice file whose style row n is filled with the number n, to see which row is used."""
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = np.repeat(np.arange(rows, dtype=np.float32), STYLE_WIDTH)
    styles.tofile(path)


class FakeSession:
    """Records what Kokoro would be given. Returns 10 samples per input token."""

    instances: list[FakeSession] = []

    def __init__(self, model: str, options, providers: list[str]) -> None:
        self.model = model
        self.options = options
        self.providers = providers
        self.feeds: list[dict[str, np.ndarray]] = []
        FakeSession.instances.append(self)

    def run(self, outputs, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.feeds.append(feeds)
        count = feeds["input_ids"].shape[1] * 10
        return [np.full((1, count), len(self.feeds) / 100, dtype=np.float32)]


def use_fake_session(monkeypatch) -> type[FakeSession]:
    import onnxruntime

    FakeSession.instances = []
    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    return FakeSession
