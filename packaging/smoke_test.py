"""Try a built Dogear offline, with nothing to lean on but what it carries.

    uv run python packaging/smoke_test.py PATH/TO/dogear

The program runs with an empty home folder, so no voice or speech cache from earlier
can be used; a PATH with nothing on it, so only the bundled ffmpeg and espeak-ng can be
found; and web proxies pointed at a closed port, so any download fails at once. Then it
runs dogear --version, voices, say, and make (the first section of the test book, as an
M4B). It passes only if each step works and no voice file was downloaded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = next((ROOT / "tests" / "fixtures").glob("*.epub"))
CLOSED_PORT = "http://127.0.0.1:9"
# What Windows programs need from the environment to start at all.
WINDOWS_KEEP = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS")
MODEL_SUFFIXES = (".onnx", ".bin", ".whl", ".cfg")


class Failed(Exception):
    pass


def check(passed: bool, problem: str) -> None:
    if not passed:
        raise Failed(problem)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: smoke_test.py PATH/TO/dogear", file=sys.stderr)
        return 2
    program = Path(args[0]).resolve()
    with tempfile.TemporaryDirectory(prefix="dogear-smoke-") as scratch:
        try:
            smoke_test(program, Path(scratch))
        except Failed as e:
            print(f"Failed: {e}", file=sys.stderr)
            return 1
    print("Every step passed.")
    return 0


def smoke_test(program: Path, scratch: Path) -> None:
    home, out = scratch / "home", scratch / "out"
    env = offline_environment(home, scratch / "empty-path", scratch / "tmp")
    for name in ("ffmpeg", "ffprobe", "espeak-ng"):
        check(not shutil.which(name, path=env["PATH"]), f"{name} is on the test's PATH")

    version = run(program, ["--version"], env)
    check(version.startswith("dogear "), version)
    voices = run(program, ["voices"], env)
    check("This is the one Dogear uses now." in voices, voices)
    hello = out / "hello.wav"
    run(program, ["say", "Hello there.", "-o", str(hello)], env)
    check(hello.is_file() and hello.stat().st_size > 10_000, "say made no audio")
    made = run(
        program, ["make", str(BOOK), "--sections", "1", "--format", "m4b", "-o", str(out)], env
    )
    books = list(out.glob("*.m4b"))
    check(len(books) == 1, f"make saved no M4B:\n{made}")
    with books[0].open("rb") as f:
        check(f.read(8)[4:] == b"ftyp", f"{books[0].name} isn't an MP4 file")
    downloaded = [p for p in home.rglob("*") if p.suffix in MODEL_SUFFIXES]
    check(not downloaded, f"voice files were written outside the bundle: {downloaded}")


def offline_environment(home: Path, empty: Path, tmp: Path) -> dict[str, str]:
    for folder in (home, empty, tmp):
        folder.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": str(empty),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "NO_PROXY": "",
    }
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env[name] = CLOSED_PORT
    if os.name == "nt":
        env.update({k: os.environ[k] for k in WINDOWS_KEEP if k in os.environ})
    return env


def run(program: Path, args: list[str], env: dict[str, str]) -> str:
    print(f"Running: dogear {' '.join(args)}", flush=True)
    result = subprocess.run(
        [str(program), *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    output = result.stdout + result.stderr
    check(result.returncode == 0, f"dogear {args[0]} failed:\n{output}")
    return output


if __name__ == "__main__":
    raise SystemExit(main())
