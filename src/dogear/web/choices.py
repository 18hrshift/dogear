"""The "Choose what to make" form: what it offers, what starts out chosen, and checking
what comes back. Defaults come from the config, or from the book's last choices."""

from __future__ import annotations

from dataclasses import dataclass

from dogear.book_summary import BookSummary
from dogear.config import Config
from dogear.make import FORMATS, speaks_language
from dogear.voice.catalog import describe_voice, kokoro_voices_best_first
from dogear.web.books import Choices
from dogear.web.forms import every, first


@dataclass(frozen=True)
class FormatInfo:
    name: str  # as `dogear make --format` takes it
    title: str
    description: str


FORMAT_INFO = {
    info.name: info
    for info in (
        FormatInfo(
            "m4b",
            "M4B audiobook",
            "One file with chapters, for audiobook apps on a phone or computer.",
        ),
        FormatInfo(
            "mp3",
            "MP3 folder",
            "A folder of MP3 files, one for each section, with a playlist. Plays almost "
            "anywhere, including older players.",
        ),
        FormatInfo(
            "epub",
            "EPUB talking book",
            "The text and the audio together, each sentence highlighted as it's read, for "
            "reading apps such as Thorium Reader.",
        ),
        FormatInfo(
            "daisy",
            "DAISY talking book",
            "For DAISY players and apps, such as a Victor Reader Stream, which move by "
            "heading and by print page.",
        ),
    )
}

# Speeds offered, in words. The configured speed is added if it isn't one of these.
SPEEDS: tuple[tuple[float, str], ...] = (
    (0.8, "Slower"),
    (0.9, "A little slower"),
    (1.0, "Natural"),
    (1.1, "Faster"),
)


@dataclass(frozen=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True)
class Picked:
    """What the form shows as chosen: the defaults, or what was sent back."""

    formats: frozenset[str]
    voice: str
    speed: str
    sections: frozenset[int]
    as_english: bool


def format_options() -> list[FormatInfo]:
    return list(FORMAT_INFO.values())


def voice_options() -> list[Option]:
    return [Option(v.name, describe_voice(v)) for v in kokoro_voices_best_first()]


def speed_options(config: Config) -> list[Option]:
    usual = float(config["voice"]["speed"])
    speeds = list(SPEEDS)
    if all(abs(usual - speed) > 1e-9 for speed, _ in speeds):
        speeds = sorted([*speeds, (usual, "Your usual speed")])
    return [
        Option(
            _speed_text(speed),
            f"{words} ({_speed_text(speed)})"
            + (", the usual" if abs(speed - usual) < 1e-9 else ""),
        )
        for speed, words in speeds
    ]


def asks_about_language(summary: BookSummary) -> bool:
    """Whether the book says it's in a language the voice doesn't speak. Books are often
    marked wrongly, so the form then asks whether to read it as English anyway."""
    return not speaks_language(summary.language)


def defaults(summary: BookSummary, config: Config, last: Choices | None) -> Picked:
    if last is not None:
        return Picked(
            formats=frozenset(last.formats),
            voice=last.voice,
            speed=_speed_text(last.speed),
            sections=frozenset(last.sections),
            as_english=last.as_english,
        )
    return Picked(
        formats=frozenset(f for f in config["output"]["formats"] if f in FORMATS),
        voice=config["voice"]["voice"],
        speed=_speed_text(float(config["voice"]["speed"])),
        sections=frozenset(s.number for s in summary.sections),
        as_english=False,
    )


def check(
    fields: list[tuple[str, str]], summary: BookSummary, config: Config
) -> tuple[Picked, Choices | None, dict[str, str]]:
    """What was sent back, as shown on the form; the choices, if they're all right; and
    an error for each field that isn't, keyed by the field's name."""
    numbers = {s.number for s in summary.sections}
    picked = Picked(
        formats=frozenset(f for f in every(fields, "format") if f in FORMATS),
        voice=first(fields, "voice"),
        speed=first(fields, "speed"),
        sections=frozenset(
            int(v) for v in every(fields, "section") if v.isdigit() and int(v) in numbers
        ),
        as_english=first(fields, "english") == "yes",
    )
    errors: dict[str, str] = {}
    if asks_about_language(summary) and not picked.as_english:
        errors["english"] = (
            "Dogear's voice speaks only English. To make this book anyway, choose Read it "
            "as English."
        )
    if not picked.formats:
        errors["format"] = "Choose at least one thing to make."
    if picked.voice not in {option.value for option in voice_options()}:
        errors["voice"] = "Choose a voice from the list."
    if picked.speed not in {option.value for option in speed_options(config)}:
        errors["speed"] = "Choose a speed."
    if not picked.sections:
        errors["section"] = "Choose at least one section."
    if errors:
        return picked, None, errors
    choices = Choices(
        formats=tuple(f for f in FORMATS if f in picked.formats),
        voice=picked.voice,
        speed=float(picked.speed),
        sections=tuple(sorted(picked.sections)),
        as_english=picked.as_english and asks_about_language(summary),
    )
    return picked, choices, {}


def _speed_text(speed: float) -> str:
    return f"{speed:.2f}".rstrip("0").rstrip(".") if speed % 1 else f"{speed:.1f}"
