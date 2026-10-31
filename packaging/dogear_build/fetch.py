"""Download a pinned source archive once, checked against its SHA-256.

Uses Dogear's own downloader, which writes under a temporary name and renames only after
the checksum matches, so a cached archive is always a checked one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dogear.errors import DownloadError
from dogear.voice.downloads import RemoteFile, download
from dogear_build.pins import Source

Report = Callable[[str], None]
TIMEOUT_SECONDS = 60


def fetch(source: Source, downloads: Path, report: Report) -> Path:
    """The archive for `source` in `downloads`, downloading it first if needed."""
    path = downloads / source.archive_name
    if path.is_file():
        return path
    report(f"Downloading {source.name} {source.version}.")
    error: DownloadError | None = None
    for url in (source.url, *source.mirrors):
        try:
            download(RemoteFile(url, source.sha256, source.size, path), TIMEOUT_SECONDS, report)
            return path
        except DownloadError as e:
            report(f"{url} failed: {e.message}")
            error = e
    assert error is not None
    raise error
