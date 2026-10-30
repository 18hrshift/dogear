"""Making a book: `dogear make` in a child process, with its progress lines kept as they
come. Its `Saved:` lines say what it made; `Error:` and `What to do:` say why it failed."""

from __future__ import annotations

import shutil
from pathlib import Path

from dogear.web.books import MADE, ZIPS, BookRecord, BookStore, Output
from dogear.web.child import Stopper, child_command, read_lines, start_lines
from dogear.web.reading import problem_from_output
from dogear.web.settings import WebSettings

INTERRUPTED = 130  # `dogear` stopped by Ctrl+C, or by the server asking it to stop


def make_book(store: BookStore, settings: WebSettings, book_id: str, stopper: Stopper) -> None:
    """Make the chosen outputs. Leaves the book "done", "failed", or "stopped"."""
    record = store.get(book_id)
    if record is None or record.choices is None:
        return
    folder = store.folder(book_id)
    shutil.rmtree(folder / ZIPS, ignore_errors=True)  # zips of an earlier make are stale
    store.update(book_id, state="making", lines=[], lines_dropped=0, error="", hint="", outputs=[])
    command = child_command(make_args(record, folder), settings.config_file)
    try:
        process = start_lines(command)
    except OSError as e:
        store.update(
            book_id,
            state="failed",
            error=f"Dogear couldn't start making the book: {e}.",
            hint="Check that Dogear is installed properly, then choose Start again.",
        )
        return
    stopper.attach(process)
    saved: list[str] = []
    problem: list[str] = []
    try:
        assert process.stdout is not None
        for line in read_lines(process.stdout):
            if line.startswith("Saved: "):
                saved.append(line.removeprefix("Saved: "))
            elif line.startswith(("Error: ", "What to do: ")):
                problem.append(line)
            elif line.strip() and not stopper.requested.is_set():
                # After a stop, what's left is `dogear`'s goodbye, written for a terminal.
                store.add_line(book_id, line)
        returncode = process.wait()
    finally:
        stopper.detach()
    if stopper.requested.is_set() or returncode == INTERRUPTED:
        store.update(book_id, state="stopped", error="", hint="")
    elif returncode != 0:
        found = problem_from_output("\n".join(problem))
        store.update(book_id, state="failed", error=found.error, hint=found.hint)
    else:
        outputs = saved_outputs(record, folder, saved)
        if outputs is None:
            store.update(
                book_id,
                state="failed",
                error="Dogear finished, but didn't say where it saved the book.",
                hint="This is a bug in Dogear. Please report it.",
            )
        else:
            store.update(book_id, state="done", outputs=outputs)


def make_args(record: BookRecord, folder: Path) -> list[str]:
    """`dogear make`'s arguments for the book's choices."""
    choices = record.choices
    assert choices is not None
    args = [
        "make",
        str(folder / record.source_name),
        "-o",
        str(folder / MADE),
        "--format",
        ",".join(choices.formats),
        "--voice",
        choices.voice,
        "--speed",
        f"{choices.speed:g}",
    ]
    every = record.summary is not None and len(choices.sections) == len(record.summary.sections)
    if not every:
        args += ["--sections", section_spec(choices.sections)]
    if choices.as_english:
        args += ["--language", "en"]
    return args


def section_spec(numbers: tuple[int, ...]) -> str:
    """(1, 2, 3, 7) as '1-3,7', the way `dogear make --sections` takes them."""
    runs: list[list[int]] = []
    for n in sorted(set(numbers)):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def saved_outputs(record: BookRecord, folder: Path, saved: list[str]) -> list[Output] | None:
    """What `dogear make` saved, paired with the formats it was asked for (it saves them
    in make.FORMATS order). None unless every one is in the book's `made` folder."""
    assert record.choices is not None
    formats = record.choices.formats
    if len(saved) != len(formats):
        return None
    made = (folder / MADE).resolve()
    outputs = []
    for format_name, path_text in zip(formats, saved, strict=True):
        path = Path(path_text).resolve()
        if not path.is_relative_to(made) or not path.exists():
            return None
        outputs.append(
            Output(format=format_name, path=path.relative_to(folder.resolve()).as_posix())
        )
    return outputs
