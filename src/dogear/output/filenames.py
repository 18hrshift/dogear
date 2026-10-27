"""File names that work on Windows, macOS, and Linux, and sort in reading order."""

from __future__ import annotations

import re
import unicodedata

# Characters Windows forbids in names (macOS Finder also forbids ":"), plus control codes.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')

# Device names Windows reserves, with or without an extension ("CON.mp3" is reserved too).
_PORT_DIGITS = [*"0123456789", "¹", "²", "³"]  # superscript 1-3 count too
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{port}{digit}" for port in ("COM", "LPT") for digit in _PORT_DIGITS
}

# Longest whole name in UTF-8 bytes. Linux allows 255 bytes and Windows 255 UTF-16 units;
# staying well under leaves room for a deep folder within Windows' 260-character path limit.
MAX_NAME_BYTES = 120


def track_filenames(titles: list[str], extension: str) -> list[str]:
    """'01 - Chapter One.mp3' and so on, zero-padded so every player sorts them in order."""
    width = max(2, len(str(len(titles))))
    names = []
    for number, title in enumerate(titles, start=1):
        prefix = f"{number:0{width}d}"
        cleaned = _clean(title)
        names.append(safe_filename(f"{prefix} - {cleaned}" if cleaned else prefix, extension))
    return names


def safe_filename(stem: str, extension: str, fallback: str = "untitled") -> str:
    """`stem` + `extension` with anything a common file system rejects taken out."""
    budget = MAX_NAME_BYTES - len(extension.encode("utf-8"))
    name = _clean(_fit(_clean(stem), budget)) or fallback
    if name.split(".")[0].rstrip().upper() in _RESERVED:
        name = "_" + name
    return name + extension


def _clean(text: str) -> str:
    text = _ILLEGAL.sub(" ", unicodedata.normalize("NFC", text))
    # One space between words; no leading dot (hidden on macOS and Linux) and no trailing
    # dot or space (Windows drops them, so the file can't be opened by its real name).
    return " ".join(text.split()).strip(" .")


def _fit(text: str, max_bytes: int) -> str:
    # Cut at a character boundary, never inside a multi-byte character.
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
