"""Mono 16-bit PCM audio: converting engine output, trimming edges, writing WAV files."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

_FULL_SCALE = 32767


def to_pcm16(samples: np.ndarray) -> np.ndarray:
    """Float samples in [-1, 1] as 16-bit integers, clipping anything outside."""
    return (np.clip(samples, -1.0, 1.0) * _FULL_SCALE).astype(np.int16)


def trim_edges(samples: np.ndarray, sample_rate: int, threshold_db: float, keep_ms: int):
    """Cut near-silence from both ends, keeping `keep_ms` of it before and after the sound.

    Engines pad their output differently; trimming it lets Dogear's own pauses decide
    the spacing. Audio that is all silence comes back empty.
    """
    threshold = _FULL_SCALE * 10 ** (threshold_db / 20)
    loud = np.flatnonzero(np.abs(samples.astype(np.int32)) > threshold)
    if loud.size == 0:
        return samples[:0]
    keep = sample_rate * keep_ms // 1000
    return samples[max(0, loud[0] - keep) : loud[-1] + 1 + keep]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path.name} is not mono 16-bit PCM")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        _setup(w, sample_rate)
        w.writeframes(samples.astype(np.int16).tobytes())


class WavWriter:
    """Appends audio and silence to one WAV file without holding it all in memory."""

    def __init__(self, path: Path, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.frames = 0
        self._wave = wave.open(str(path), "wb")
        _setup(self._wave, sample_rate)

    def audio(self, samples: np.ndarray) -> None:
        self._wave.writeframes(samples.astype(np.int16).tobytes())
        self.frames += len(samples)

    def silence(self, ms: int) -> None:
        count = self.sample_rate * ms // 1000
        self._wave.writeframes(bytes(2 * count))
        self.frames += count

    def close(self) -> None:
        self._wave.close()

    def __enter__(self) -> WavWriter:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _setup(w: wave.Wave_write, sample_rate: int) -> None:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sample_rate)
