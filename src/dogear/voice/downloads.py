"""Download voice model files once, each checked against a pinned SHA-256.

A file is written under a temporary name and renamed only after its checksum matches, so
an interrupted or tampered download never looks complete.
"""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dogear.config import Config
from dogear.errors import DownloadError

Report = Callable[[str], None]

_CHUNK = 1 << 20
_REPORT_FROM = 50 << 20  # files at least this big get progress lines...
_REPORT_EVERY = 0.25  # ...at each quarter
ISSUES_URL = "https://github.com/18hrshift/dogear/issues"


@dataclass(frozen=True)
class RemoteFile:
    url: str
    sha256: str
    size: int  # bytes, as published; used for messages and as an upper bound
    path: Path  # where the file lives once downloaded


def ensure_files(files: list[RemoteFile], config: Config, report: Report) -> None:
    """Download whichever of `files` aren't on disk yet."""
    missing = [f for f in files if not f.path.is_file()]
    if not missing:
        return
    total = sum(f.size for f in missing)
    report(f"Downloading voice files, {megabytes(total)} in all. This only happens once.")
    for remote in missing:
        download(remote, config["models"]["download_timeout_seconds"], report)
    report("Voice files downloaded.")


def download(remote: RemoteFile, timeout: float, report: Report) -> None:
    name = remote.path.name
    remote.path.parent.mkdir(parents=True, exist_ok=True)
    partial = remote.path.with_name(name + ".part")
    try:
        digest = _fetch(remote, partial, timeout, report)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        partial.unlink(missing_ok=True)
        reason = getattr(e, "reason", None) or e
        raise DownloadError(
            f"Couldn't download {name}: {reason}.",
            hint="Check the internet connection, then run the same command again.",
        ) from None
    except DownloadError:
        partial.unlink(missing_ok=True)
        raise
    if digest != remote.sha256:
        partial.unlink(missing_ok=True)
        raise DownloadError(
            f"The downloaded {name} doesn't match its expected checksum, so it wasn't used.",
            hint=f"Run the command again. If it keeps happening, please report it at {ISSUES_URL}.",
        )
    os.replace(partial, remote.path)


def _fetch(remote: RemoteFile, partial: Path, timeout: float, report: Report) -> str:
    digest = hashlib.sha256()
    received, next_mark = 0, _REPORT_EVERY
    with urllib.request.urlopen(remote.url, timeout=timeout) as response, partial.open("wb") as out:
        while chunk := response.read(_CHUNK):
            received += len(chunk)
            if received > remote.size:
                raise DownloadError(
                    f"{remote.path.name} is bigger than expected, so the download was stopped.",
                    hint=f"Please report this at {ISSUES_URL}.",
                )
            out.write(chunk)
            digest.update(chunk)
            if remote.size >= _REPORT_FROM and received >= next_mark * remote.size:
                report(f"{remote.path.name}: {round(next_mark * 100)}% downloaded.")
                next_mark += _REPORT_EVERY
    return digest.hexdigest()


def megabytes(size: int) -> str:
    return f"{max(1, round(size / 1_000_000))} MB"
