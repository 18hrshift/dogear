"""Errors a user can act on. Each carries a hint saying what to do next.

Anything that is not a DogearError is a bug in Dogear and should surface with a traceback.
"""


class DogearError(Exception):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(DogearError):
    """The config file is missing, unreadable, or has a wrong key or type."""


class UnsupportedFormatError(DogearError):
    """Dogear can't read this kind of file."""


class ExtractionError(DogearError):
    """The book could be opened but not turned into a usable document."""


class ScannedPdfError(ExtractionError):
    """The PDF is images of pages with no text layer, so it needs OCR first."""


class ToolNotFoundError(DogearError):
    """An external program (ffmpeg, Tesseract, Calibre) isn't installed or isn't on PATH."""


class ToolFailedError(DogearError):
    """An external program ran but reported an error."""
