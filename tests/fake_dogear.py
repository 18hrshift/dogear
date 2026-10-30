"""A stand-in for the `dogear` command, run by the web page's tests as its child process.

What it does depends on the first word of the book file:

    ok          outline lists three sections; make prints progress and saves what it's asked
    unreadable  outline fails with `Error:` and `What to do:` lines
    fail        make fails with `Error:` and `What to do:` lines
    slow        make prints a line, then waits (for a test to stop it)
    slowread    outline waits (for a test to stop it), then lists three sections
    crash       make fails with a traceback and no `Error:` line

When DOGEAR_FAKE_LOG names a file, each run adds its arguments to it as a JSON list.
When DOGEAR_FAKE_PIDS names a file, each run adds its process id to it, on a line.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dogear.web.server_watch import stop_with_server_when_asked

TITLE = "Fake Book"
SECTIONS = ["Title Page", "One", "Two"]


def main(argv: list[str]) -> int:
    stop_with_server_when_asked()  # as the real `dogear` does
    log = os.environ.get("DOGEAR_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as file:
            file.write(json.dumps(argv) + "\n")
    pids = os.environ.get("DOGEAR_FAKE_PIDS")
    if pids:
        with open(pids, "a", encoding="utf-8") as file:
            file.write(f"{os.getpid()}\n")
    command, book = argv[0], Path(argv[1])
    behaviour = book.read_text(encoding="utf-8").split()[0]
    if command == "outline":
        if behaviour == "unreadable":
            return fail()
        if behaviour == "slowread":
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("Stopped.", file=sys.stderr)
                return 130
        print(json.dumps(summary()))
        return 0
    if behaviour == "fail":
        return fail()
    return make(argv, behaviour)


def fail() -> int:
    print("Error: This book is locked with DRM.", file=sys.stderr)
    print("What to do: Use a copy without DRM.", file=sys.stderr)
    return 1


def summary() -> dict:
    return {
        "title": TITLE,
        "authors": ["Ann Author"],
        "language": "en",
        "source_format": "epub",
        "words": 300,
        "sections": [
            {
                "number": n,
                "title": title,
                "kind": "front" if n == 1 else "body",
                "words": 100,
                "first_page": None if n == 1 else str(n),
                "last_page": None if n == 1 else str(n + 1),
                "images": 0,
                "notes": 1 if n == 2 else 0,
                "tables": 0,
            }
            for n, title in enumerate(SECTIONS, start=1)
        ],
    }


def make(argv: list[str], behaviour: str) -> int:
    out = Path(argv[argv.index("-o") + 1])
    formats = argv[argv.index("--format") + 1].split(",")
    print(f"Making an audiobook of {TITLE}: 3 sections, about 300 words.", file=sys.stderr)
    sys.stderr.flush()
    if behaviour == "crash":
        raise RuntimeError("a bug")
    if behaviour == "slow":
        try:
            time.sleep(60)
        except KeyboardInterrupt:  # the goodbye `dogear make` gives in a terminal
            print("Stopped.", file=sys.stderr)
            print(
                "Sentences spoken so far are saved. Run the same command again to continue.",
                file=sys.stderr,
            )
            return 130
    for n, title in enumerate(SECTIONS, start=1):
        print(f"Section {n} of 3 done: {title}.", file=sys.stderr)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("m4b", "mp3", "epub", "daisy"):
        if name in formats:
            print(f"Saved: {save(out, name)}")
    return 0


def save(out: Path, name: str) -> Path:
    if name == "m4b":
        path = out / f"{TITLE}.m4b"
        path.write_bytes(b"m4b" * 1000)
    elif name == "epub":
        path = out / f"{TITLE} talking book.epub"
        path.write_bytes(b"epub" * 1000)
    else:
        path = out / f"{TITLE} {name.upper()}"
        path.mkdir(exist_ok=True)
        (path / "01 One.mp3").write_bytes(b"one" * 1000)
        (path / "02 Two.mp3").write_bytes(b"two" * 1000)
    return path


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
