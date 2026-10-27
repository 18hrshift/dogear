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
from dogear.errors import DogearError, VoiceError
from dogear.extract import extract_book
from dogear.narration import SectionNarration, narrate_book
from dogear.output import build_m4b, build_mp3_folder, normalize_chapters
from dogear.output.ffmpeg import check_ffmpeg
from dogear.output.filenames import safe_filename
from dogear.paths import cache_dir
from dogear.render import render_book
from dogear.render.progress import Progress, Report
from dogear.voice import make_engine

FORMATS = ("m4b", "mp3")


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
    narrations = _chosen(narrate_book(book, config), request.sections, len(book.sections))
    progress = Progress(
        total_words=sum(n.words() for n in narrations),
        total_sections=len(narrations),
        every_seconds=config["render"]["progress_every_seconds"],
        report=report,
    )
    report(
        f"Making an audiobook of {book.metadata.title}: {_count(len(narrations), 'section')}, "
        f"about {_count(progress.total_words, 'word')}, voice {config['voice']['voice']}."
    )
    engine = make_engine(config, report)
    work_root = cache_dir(config) / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    saved = []
    with tempfile.TemporaryDirectory(dir=work_root) as work:
        chapters = render_book(narrations, engine, config, Path(work), report, progress)
        report(progress.summary())
        report("Evening out the volume across chapters.")
        chapters = normalize_chapters(chapters, Path(work), config)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        title = book.metadata.title
        if "m4b" in formats:
            report("Building the M4B audiobook file.")
            path = request.output_dir / safe_filename(title, ".m4b", fallback=request.book.stem)
            build_m4b(chapters, book.metadata, path, config, normalized=True)
            saved.append(path)
        if "mp3" in formats:
            report("Building the MP3 folder.")
            name = safe_filename(f"{title} MP3", "", fallback=f"{request.book.stem} MP3")
            folder = request.output_dir / name
            build_mp3_folder(chapters, book.metadata, folder, config, normalized=True)
            saved.append(folder)
    return saved


def check_language(book: Book) -> None:
    language = book.metadata.language
    if language and not language.lower().startswith("en"):
        raise VoiceError(
            f"This book is marked as being in '{language}', but Dogear's voice only speaks "
            "English so far.",
            hint="If the book is really in English, run the command again with --language en.",
        )


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
            hint='For example: formats = ["m4b", "mp3"].',
        )
    return formats


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"
