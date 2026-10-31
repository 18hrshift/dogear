"""The real espeak-ng program, as Dogear calls it for words misaki doesn't know.

Run on every CI platform, so the flags and the stdin handoff are checked on Windows and
macOS too, not just against a stand-in.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import require_tool

from dogear.errors import ToolFailedError
from dogear.tools import run_tool
from dogear.voice.g2p import EspeakFallback


def test_espeak_names_become_misaki_phonemes():
    fallback = EspeakFallback(require_tool("espeak-ng"), british=False)
    phonemes, rating = fallback(SimpleNamespace(text="Jekyll"))
    assert rating == 1
    assert phonemes.startswith("ʤ")  # espeak's tied d^ʒ, mapped to misaki's single symbol
    assert "^" not in phonemes


def test_text_that_looks_like_an_option_is_read_as_a_word():
    fallback = EspeakFallback(require_tool("espeak-ng"), british=True)
    phonemes, _ = fallback(SimpleNamespace(text="--version"))
    assert phonemes and "eSpeak" not in phonemes


def installed_data_folder(program: str) -> Path:
    """The folder holding this espeak-ng's espeak-ng-data, from what it prints."""
    printed = run_tool([program, "--version"]).stdout
    match = re.search(r"Data at: (.+)", printed)
    assert match, printed
    return Path(match.group(1).strip()).parent


def test_the_data_folder_given_is_the_one_read(tmp_path):
    # How a standalone build points its own espeak-ng at the data beside it.
    program = require_tool("espeak-ng")
    data = installed_data_folder(program)
    phonemes, _ = EspeakFallback(program, british=False, data=data)(SimpleNamespace(text="Jekyll"))
    assert phonemes.startswith("ʤ")
    # A folder without the data fails loudly instead of falling back to another copy.
    with pytest.raises(ToolFailedError, match="phontab"):
        EspeakFallback(program, british=False, data=tmp_path)(SimpleNamespace(text="Jekyll"))
