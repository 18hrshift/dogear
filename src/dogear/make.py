"""Book file in, audiobook out: extract, narrate, speak, package.

Each step lives in its own module; this one only runs them in order and reports
progress as plain sentences.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.document import Book
from dogear.errors import DogearError, OutputFolderError, VoiceError
from dogear.extract import extract_book
from dogear.narration import SectionNarration, narrate_book, narrate_title
from dogear.output import build_m4b, build_mp3_folder, normalize_chapters
from dogear.output.daisy202 import build_daisy202
from dogear.output.epub3 import build_epub3
from dogear.output.ffmpeg import check_ffmpeg
from dogear.output.filenames import safe_filename
from dogear.paths import cache_dir
from dogear.readalong import build_readalong
from dogear.render import render_book
from dogear.render.progress import Progress, Report
from dogear.voice import make_engine

# m4b: one audiobook file with chapters. mp3: a folder of MP3 files with a playlist.
# epub: an EPUB 3 talking book, text and audio in step. daisy: a DAISY 2.02 talking book.
FORMATS = ("m4b", "mp3", "epub", "daisy")


@dataclass(frozen=True)
class MakeRequest:
    book: Path
    output_dir: Path
    sections: set[int] | None = None  # numbers from `dogear outline`; None means all
    language: str | None = None  # overrides the language the book declares


def make_audiobook(request: MakeRequest, config: Config, report: Report) -> list[Path]:
    """Make the configured outputs for one book. Returns what was saved, in order."""
    formats = _formats(config)
    book = extract_book(request.book, config)
    if request.language:
        book.metadata.language = request.language
    check_language(book)
    check_ffmpeg(config)
    outputs = _output_paths(book, request, formats)
    narrations = _chosen(narrate_book(book, config), request.sections, len(book.sections))
    chosen = len(narrations)
    if config["narration"]["announce_title"]:
        narrations.insert(0, narrate_title(book, config))
    progress = Progress(
        total_words=sum(n.words() for n in narrations),
        total_sections=len(narrations),
        every_seconds=config["render"]["progress_every_seconds"],
        report=report,
    )
    title_track = " and a title track" if len(narrations) > chosen else ""
    report(
        f"Making an audiobook of {book.metadata.title}: {_count(chosen, 'section')}"
        f"{title_track}, about {_count(progress.total_words, 'word')}, "
        f"voice {config['voice']['voice']}."
    )
    engine = make_engine(config, report)
    work_root = cache_dir(config) / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work_root) as work:
        chapters = render_book(narrations, engine, config, Path(work), report, progress)
        report(progress.summary())
        report("Evening out the volume across chapters.")
        chapters = normalize_chapters(chapters, Path(work), config)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        if "m4b" in formats:
            report("Building the M4B audiobook file.")
            build_m4b(chapters, book.metadata, outputs["m4b"], config, normalized=True)
        if "mp3" in formats:
            report("Building the MP3 folder.")
            build_mp3_folder(chapters, book.metadata, outputs["mp3"], config, normalized=True)
        if "epub" in formats or "daisy" in formats:
            sections = build_readalong(narrations, chapters, book.metadata.language)
            if "epub" in formats:
                report("Building the EPUB talking book.")
                build_epub3(sections, book.metadata, outputs["epub"], config)
            if "daisy" in formats:
                report("Building the DAISY talking book.")
                build_daisy202(sections, book.metadata, outputs["daisy"], config)
    return [outputs[f] for f in FORMATS if f in formats]


def _output_paths(book: Book, request: MakeRequest, formats: list[str]) -> dict[str, Path]:
    """Where each format is saved, checked before any speaking starts."""
    title, stem = book.metadata.title, request.book.stem
    names = {
        "m4b": safe_filename(title, ".m4b", fallback=stem),
        "mp3": safe_filename(f"{title} MP3", "", fallback=f"{stem} MP3"),
        "epub": safe_filename(f"{title} talking book", ".epub", fallback=f"{stem} talking book"),
        "daisy": safe_filename(f"{title} DAISY", "", fallback=f"{stem} DAISY"),
    }
    paths = {f: request.output_dir / names[f] for f in formats}
    source = request.book.resolve()
    for path in paths.values():
        if path.resolve() == source:
            raise OutputFolderError(
                f"Saving {path.name} would replace the book it was made from.",
                hint="Choose another folder with -o, or rename the book file first.",
            )
    return paths


def check_language(book: Book) -> None:
    language = book.metadata.language
    if language and not language.lower().startswith("en"):
        raise VoiceError(
            f"This book is marked as being in '{language}', but Dogear's voice only speaks "
            "English so far.",
            hint="If the book is really in English, run the command again with --language en.",
        )


def parse_formats(spec: str) -> list[str]:
    """'m4b' or 'm4b,daisy' as a list of formats; 'all' is every one."""
    names = [name.strip().lower() for name in spec.split(",") if name.strip()]
    if names == ["all"]:
        return list(FORMATS)
    unknown = [name for name in names if name not in FORMATS]
    if unknown or not names:
        raise DogearError(
            f"'{unknown[0] if unknown else spec}' isn't a format Dogear makes.",
            hint=f"Use one or more of {', '.join(FORMATS)}, separated by commas, or all.",
        )
    return list(dict.fromkeys(names))


def parse_sections(spec: str) -> set[int]:
    """'3' or '1-3,7' as a set of section numbers."""
    numbers: set[int] = set()
    for part in spec.split(","):
        first, dash, last = part.strip().partition("-")
        try:
            start = int(first)
            end = int(last) if dash else start
        except ValueError:
            raise DogearError(
                f"'{spec}' isn't a list of section numbers.",
                hint="Use numbers from `dogear outline`, such as 3 or 1-3,7.",
            ) from None
        if end < start:
            raise DogearError(
                f"'{part.strip()}' counts backwards.",
                hint=f"Write the lower number first: {end}-{start}.",
            )
        numbers.update(range(start, end + 1))
    return numbers


def _chosen(
    narrations: list[SectionNarration], wanted: set[int] | None, total: int
) -> list[SectionNarration]:
    if wanted is None:
        return narrations
    outside = sorted(n for n in wanted if not 1 <= n <= total)
    if outside:
        raise DogearError(
            f"There is no section {outside[0]}; this book has {total}.",
            hint="Run `dogear outline` to see the section numbers.",
        )
    chosen = [n for n in narrations if n.number in wanted]
    if not chosen:
        raise DogearError(
            "Nothing in the chosen sections is read aloud.",
            hint="Pick other sections from `dogear outline`.",
        )
    return chosen


def _formats(config: Config) -> list[str]:
    formats = config["output"]["formats"]
    unknown = [f for f in formats if f not in FORMATS]
    if unknown or not formats:
        raise DogearError(
            f"output.formats is {formats}; each entry must be one of: {', '.join(FORMATS)}.",
            hint='For example: formats = ["m4b", "daisy"].',
        )
    return formats


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"
