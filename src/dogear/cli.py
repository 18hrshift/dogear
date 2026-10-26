"""The `dogear` command.

Output is written to be read by a screen reader as well as seen: plain sentences and
numbered lists, no tables, colors, or animations. Progress and errors go to stderr.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dogear import __version__
from dogear.config import Config, load_config
from dogear.document import (
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    PageMarker,
    Paragraph,
    SceneBreak,
    Section,
    Table,
    block_text,
)
from dogear.errors import DogearError
from dogear.extract import extract_book
from dogear.ocr import default_output_path, ocr_pdf
from dogear.speech.normalize import SpeechRules, normalize_for_speech
from dogear.speech.sentences import SentenceRules, split_sentences

KIND_NAMES = {"front": "front matter", "body": "main text", "back": "back matter"}
PROGRESS_EVERY = 10  # pages between OCR progress lines
BOOK_HELP = "the book file: EPUB, PDF, MOBI, or AZW3"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        config = load_config(args.config)
        return args.run(args, config)
    except DogearError as e:
        print(f"Error: {e.message}", file=sys.stderr)
        if e.hint:
            print(f"What to do: {e.hint}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="settings file (TOML) to use")
    common.add_argument("-v", "--verbose", action="store_true", help="explain each step")

    # --config and -v live on each command only: an argparse parent shared with the main
    # parser would reset them to None after the command name.
    parser = argparse.ArgumentParser(
        prog="dogear", description="Turn books into navigable audiobooks."
    )
    parser.add_argument("--version", action="version", version=f"dogear {__version__}")
    commands = parser.add_subparsers(title="commands", required=True, metavar="COMMAND")

    outline = commands.add_parser(
        "outline",
        parents=[common],
        help="list a book's sections",
        description="List a book's title, authors, and sections with word counts and print pages.",
    )
    outline.add_argument("book", type=Path, help=BOOK_HELP)
    outline.set_defaults(run=_outline)

    text = commands.add_parser(
        "text",
        parents=[common],
        help="show the text Dogear found",
        description="Show the text Dogear extracted, to check it before making audio.",
    )
    text.add_argument("book", type=Path, help=BOOK_HELP)
    text.add_argument("--section", type=int, metavar="N", help="only section N (from outline)")
    text.add_argument(
        "--spoken",
        action="store_true",
        help="show each sentence the way the voice will say it",
    )
    text.set_defaults(run=_text)

    ocr = commands.add_parser(
        "ocr",
        parents=[common],
        help="make a scanned PDF readable",
        description="Add a text layer to a scanned PDF so Dogear can read it.",
    )
    ocr.add_argument("pdf", type=Path, help="the scanned PDF")
    ocr.add_argument("-o", "--output", type=Path, help="where to save (default: NAME_ocr.pdf)")
    ocr.add_argument("--language", help="Tesseract language, such as eng or eng+fra")
    ocr.add_argument("--dpi", type=int, help="scan resolution to read pages at")
    ocr.set_defaults(run=_ocr)
    return parser


def _outline(args: argparse.Namespace, config: Config) -> int:
    book = extract_book(args.book, config)
    print(f"Title: {book.metadata.title}")
    if book.metadata.authors:
        print(f"By: {', '.join(book.metadata.authors)}")
    if book.metadata.language:
        print(f"Language: {book.metadata.language}")
    print(
        f"{book.source_format.upper()} file, {_count(len(book.sections), 'section')}, "
        f"{_count(book.word_count(), 'word')}."
    )
    print()
    for number, section in enumerate(book.sections, start=1):
        print(f"{number}. {_describe(section)}")
    return 0


def _describe(section: Section) -> str:
    parts = [f"{section.title}: {KIND_NAMES[section.kind]}", _count(section.word_count(), "word")]
    pages = section.page_labels()
    if len(pages) == 1:
        parts.append(f"print page {pages[0]}")
    elif pages:
        parts.append(f"print pages {pages[0]} to {pages[-1]}")
    for kind, name in [(Image, "image"), (Footnote, "note"), (Table, "table")]:
        count = sum(isinstance(b, kind) for b in section.blocks)
        if count:
            parts.append(_count(count, name))
    return ", ".join(parts) + "."


def _text(args: argparse.Namespace, config: Config) -> int:
    book = extract_book(args.book, config)
    sections = _chosen_sections(book, args.section)
    say = _speaker(config, book) if args.spoken else None
    for number, section in sections:
        print(f"Section {number}: {section.title}")
        print()
        for block in section.blocks:
            for line in _block_lines(block, say):
                print(line)
        print()
    return 0


def _chosen_sections(book: Book, wanted: int | None) -> list[tuple[int, Section]]:
    numbered = list(enumerate(book.sections, start=1))
    if wanted is None:
        return numbered
    if not 1 <= wanted <= len(numbered):
        raise DogearError(
            f"There is no section {wanted}; this book has {len(numbered)}.",
            hint="Run `dogear outline` to see the section numbers.",
        )
    return [numbered[wanted - 1]]


def _speaker(config: Config, book: Book):
    speech, sentences = SpeechRules.from_config(config), SentenceRules.from_config(config)

    def say(text: str, lang: str | None) -> list[str]:
        language = lang or book.metadata.language
        return [normalize_for_speech(s, speech, language) for s in split_sentences(text, sentences)]

    return say


def _block_lines(block, say) -> list[str]:
    def show(text: str, lang: str | None = None, prefix: str = "") -> list[str]:
        if say is None:
            return [prefix + text]
        return [prefix + s for s in say(text, lang)]

    match block:
        case PageMarker(label=label):
            return [f"[Print page {label}]"]
        case SceneBreak():
            return ["[Scene break]", ""]
        case Heading() | Paragraph():
            return show(block.text, block.lang) + [""]
        case ListBlock(items=items):
            return [line for item in items for line in show(item, block.lang, "- ")] + [""]
        case Footnote(label=label, text=text):
            # The note id is a file path plus an anchor: noise when read aloud.
            return show(text, block.lang, f"Note {label}: " if label else "Note: ") + [""]
        case Image(alt=alt, caption=caption):
            described = alt if alt else ("no description" if alt is None else "decorative")
            return [f"Image: {described}." + (f" Caption: {caption}" if caption else ""), ""]
        case Table():
            return [f"Table: {block_text(block)}", ""]
    raise TypeError(f"not a block: {block!r}")


def _ocr(args: argparse.Namespace, config: Config) -> int:
    if args.language:
        config["ocr"]["language"] = args.language
    if args.dpi:
        config["ocr"]["dpi"] = args.dpi
    output = args.output or default_output_path(args.pdf)

    def progress(done: int, total: int) -> None:
        if done % PROGRESS_EVERY == 0 or done == total:
            print(f"OCR: page {done} of {total} done.", file=sys.stderr)

    pages = ocr_pdf(args.pdf, output, config, progress)
    print(f"Saved {_count(pages, 'page')} with a text layer to {output}")
    return 0


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"
