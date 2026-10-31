"""Tesseract, the OCR program: finding it, checking it has the languages asked for, and
reading one page's picture with it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.errors import OcrLanguageError, ToolFailedError
from dogear.ocr.settings import OcrSettings
from dogear.tools import find_tool, run_tool

CHECK_TIMEOUT_SECONDS = 60  # for `tesseract --version` and `--list-langs`, which are quick


@dataclass(frozen=True)
class Tesseract:
    program: str
    version: str  # the first line of `tesseract --version`, such as "tesseract 5.3.4"


def find_tesseract(config: Config, settings: OcrSettings) -> Tesseract:
    """Tesseract, checked to have every language in ocr.language. Raises ToolNotFoundError
    if it isn't installed, and OcrLanguageError naming a language pack that's missing."""
    program = find_tool("tesseract", config)
    result = run_tool([program, "--version"], timeout=CHECK_TIMEOUT_SECONDS)
    lines = [line.strip() for line in (result.stdout + result.stderr).splitlines()]
    version = next((line for line in lines if line), "tesseract (version unknown)")
    installed = installed_languages(program)
    missing = [language for language in settings.languages if language not in installed]
    if missing:
        raise missing_language(missing[0], settings.language)
    return Tesseract(program=program, version=version)


def installed_languages(program: str) -> set[str]:
    """The languages `tesseract --list-langs` lists, one a line under a heading. Older
    versions print them on stderr."""
    result = run_tool([program, "--list-langs"], timeout=CHECK_TIMEOUT_SECONDS)
    words = (line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines())
    return {word for word in words if word and " " not in word}


def missing_language(language: str, asked: str) -> OcrLanguageError:
    package = "tesseract-ocr-" + language.lower().replace("_", "-")
    return OcrLanguageError(
        f"Tesseract doesn't have the language pack for '{language}', which ocr.language "
        f"({asked!r}) asks for.",
        hint=f"Install it (Debian/Ubuntu: sudo apt install {package}; macOS: brew install "
        "tesseract-lang; Windows: run the Tesseract installer again and choose the language "
        "under Additional language data), or change ocr.language in your settings file.",
    )


def read_image(
    tesseract: Tesseract,
    image: Path,
    out_base: Path,
    *,
    dpi: int,
    settings: OcrSettings,
    text_only: bool,
) -> Path:
    """Read the picture of a page into a one-page PDF at `out_base`.pdf, which it returns:
    the page's words as invisible text where they are printed, over the picture unless
    `text_only`. The page is `image`'s size at `dpi`, so positions and font sizes match
    the page it was drawn from."""
    command = [tesseract.program, str(image), str(out_base), "-l", settings.language]
    command += ["--dpi", str(dpi)]
    if text_only:
        command += ["-c", "textonly_pdf=1"]
    try:
        run_tool([*command, "pdf"])
    except ToolFailedError as e:
        if "Failed loading language" in e.message:
            raise missing_language(settings.language, settings.language) from None
        raise
    return out_base.with_suffix(".pdf")
