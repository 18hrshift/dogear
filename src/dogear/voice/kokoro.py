"""Kokoro-82M (Apache-2.0), run on the CPU with onnxruntime.

Kokoro reads phonemes, not text. Each sentence becomes token ids from the model's
vocabulary, plus a style vector from the voice file chosen by the sentence's length.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

import numpy as np

from dogear.voice.engine import SpeechPlan

log = logging.getLogger(__name__)

_STYLE_WIDTH = 256
_PAD = 0  # token id that starts and ends every input
# Where to split an overlong phoneme string: after punctuation first, then at a space.
_PUNCTUATION_BREAK = re.compile(r"[.!?;:,—…]\s*")


class KokoroEngine:
    def __init__(
        self,
        *,
        model: Path,
        tokenizer: Path,
        voice: Path,
        g2p: Callable[[str], str],
        speed: float,
        threads: int,
        sample_rate: int,
        max_phonemes: int,
        identity: str,
    ) -> None:
        import onnxruntime  # slow to import, so only when a voice is actually needed

        self.sample_rate = sample_rate
        self._g2p = g2p
        self._speed = speed
        self._max_phonemes = max_phonemes
        self._vocab = load_vocab(tokenizer)
        self._styles = np.fromfile(voice, dtype=np.float32).reshape(-1, 1, _STYLE_WIDTH)
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        options.log_severity_level = 3  # errors only
        self._session = onnxruntime.InferenceSession(
            str(model), options, providers=["CPUExecutionProvider"]
        )
        self._identity = f"{identity}|speed={speed}"

    def plan(self, text: str) -> SpeechPlan:
        phonemes = self._g2p(text)
        dropped = {c for c in phonemes if c not in self._vocab}
        if dropped:
            log.debug("Kokoro has no token for %s; left out.", "".join(sorted(dropped)))
            phonemes = "".join(c for c in phonemes if c in self._vocab)
        key = hashlib.sha256(f"{self._identity}\n{phonemes}".encode()).hexdigest()
        return SpeechPlan(key=key, payload=phonemes)

    def render(self, plan: SpeechPlan) -> np.ndarray:
        pieces = [self._infer(p) for p in split_phonemes(plan.payload, self._max_phonemes)]
        return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)

    def _infer(self, phonemes: str) -> np.ndarray:
        ids = [self._vocab[c] for c in phonemes]
        feeds = {
            "input_ids": np.array([[_PAD, *ids, _PAD]], dtype=np.int64),
            # As in Kokoro's reference pipeline: the style row for this input length.
            "style": self._styles[len(ids) - 1],
            "speed": np.array([self._speed], dtype=np.float32),
        }
        audio = self._session.run(None, feeds)[0]
        return np.asarray(audio, dtype=np.float32).reshape(-1)


def load_vocab(tokenizer: Path) -> dict[str, int]:
    """Phoneme to token id, from the model's tokenizer.json."""
    data = json.loads(tokenizer.read_text(encoding="utf-8"))
    return {symbol: int(i) for symbol, i in data["model"]["vocab"].items()}


def split_phonemes(phonemes: str, limit: int) -> list[str]:
    """Pieces of at most `limit` phonemes, broken after punctuation or at spaces if possible."""
    phonemes = phonemes.strip()
    pieces = []
    while len(phonemes) > limit:
        head = phonemes[:limit]
        cut = max((m.end() for m in _PUNCTUATION_BREAK.finditer(head)), default=0)
        if cut == 0:
            cut = head.rfind(" ") + 1 or limit
        pieces.append(phonemes[:cut].strip())
        phonemes = phonemes[cut:].strip()
    if phonemes:
        pieces.append(phonemes)
    return [p for p in pieces if p]
