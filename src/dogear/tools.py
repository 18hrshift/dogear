"""Find and run external programs (ffmpeg, Tesseract, Calibre) with clear errors."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from dogear.config import Config
from dogear.errors import ToolFailedError, ToolNotFoundError

# Config key -> (program name, where to get it).
TOOLS = {
    "ffmpeg": (
        "ffmpeg",
        "Install ffmpeg (Windows: winget install ffmpeg; macOS: brew install ffmpeg; "
        "Debian/Ubuntu: sudo apt install ffmpeg).",
    ),
    "ffprobe": ("ffprobe", "ffprobe comes with ffmpeg. Install ffmpeg."),
    "tesseract": (
        "tesseract",
        "Install Tesseract OCR (Windows: winget install UB-Mannheim.TesseractOCR; "
        "macOS: brew install tesseract; Debian/Ubuntu: sudo apt install tesseract-ocr).",
    ),
    "ebook_convert": (
        "ebook-convert",
        "Install Calibre from https://calibre-ebook.com/download. "
        "It provides the ebook-convert program.",
    ),
    "espeak_ng": (
        "espeak-ng",
        "Install eSpeak NG (Windows: winget install eSpeak-NG.eSpeak-NG; "
        "macOS: brew install espeak-ng; Debian/Ubuntu: sudo apt install espeak-ng).",
    ),
}

# Common install folders that are often missing from PATH on Windows.
_WINDOWS_CANDIDATES = {
    "tesseract": [
        r"%ProgramFiles%\Tesseract-OCR\tesseract.exe",
        r"%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe",
        r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe",
    ],
    "ebook_convert": [r"%ProgramFiles%\Calibre2\ebook-convert.exe"],
    "espeak_ng": [
        r"%ProgramFiles%\eSpeak NG\espeak-ng.exe",
        r"%ProgramFiles(x86)%\eSpeak NG\espeak-ng.exe",
    ],
}


def find_tool(key: str, config: Config) -> str:
    """Path to the program for `key`, from config, PATH, or a known install folder."""
    program, install_hint = TOOLS[key]
    configured = config["tools"][key]
    if configured:
        found = shutil.which(configured)
        if found:
            return found
        raise ToolNotFoundError(
            f"tools.{key} is set to '{configured}', but that program wasn't found.",
            hint=f"Fix the path in your config, or clear it to search for it. {install_hint}",
        )
    found = shutil.which(program)
    if found:
        return found
    if os.name == "nt":
        for candidate in _WINDOWS_CANDIDATES.get(key, []):
            path = Path(os.path.expandvars(candidate))
            if path.is_file():
                return str(path)
    raise ToolNotFoundError(f"{program} was not found.", hint=install_hint)


def run_tool(
    cmd: list[str], *, timeout: float | None = None, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a program, raising ToolFailedError with the tail of its output on failure.

    Text from a book goes in through `input`, never as an argument, so it can't be
    mistaken for an option.
    """
    name = Path(cmd[0]).name
    try:
        # These programs print UTF-8 (file names, tags). Decoding with the system code page
        # instead, as Windows would by default, can crash on a byte it doesn't map.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired:
        raise ToolFailedError(
            f"{name} took longer than {timeout} seconds and was stopped."
        ) from None
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip()[-2000:]
        raise ToolFailedError(f"{name} failed (exit code {result.returncode}):\n{tail}")
    return result
