"""Receiving a book file: streamed to disk, with the size limit enforced as it arrives.

The upload form has one field, `book`. Its file is written to the web folder's
`incoming` folder under a random name and only moved into a book's folder once it is
complete and allowed. Content-Length isn't trusted: bytes are counted as they come.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import python_multipart
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header
from starlette.requests import ClientDisconnect, Request

from dogear.extract import EXTRACTORS

FIELD = "book"
# Room for the form's own boundaries and headers on top of the file.
FORM_OVERHEAD_BYTES = 64 * 1024
NOT_A_FORM = "The upload wasn't a form Dogear understands. Try again."
ACCEPT = ",".join(sorted(EXTRACTORS))  # ".azw,.azw3,.epub,.mobi,.pdf", for <input accept>


class UploadError(Exception):
    """An upload Dogear won't take. `message` is shown by the file field."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class Upload:
    original_name: str  # as the browser sent it, for showing only
    extension: str  # lower case, one Dogear reads
    path: Path  # the complete file, in the incoming folder


async def receive_book(request: Request, incoming: Path, max_bytes: int) -> Upload:
    content_type, params = parse_options_header(request.headers.get("content-type", ""))
    if content_type != b"multipart/form-data" or b"boundary" not in params:
        raise UploadError("Choose a book file, then choose Upload the book.")
    incoming.mkdir(parents=True, exist_ok=True)
    reader = _BookPart(incoming, max_bytes)
    parser = python_multipart.MultipartParser(params[b"boundary"], reader.callbacks())
    received = 0
    problem = ""
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_bytes + FORM_OVERHEAD_BYTES:
                reader.too_big = True
            if problem or reader.too_big:
                # The rest is read and dropped, so the browser gets the page that says
                # what's wrong instead of a broken connection.
                continue
            try:
                parser.write(chunk)
            except (FormParserError, _PartError) as e:
                problem = str(e) if isinstance(e, _PartError) else NOT_A_FORM
        if not problem and not reader.too_big:
            try:
                parser.finalize()
            except FormParserError:
                problem = NOT_A_FORM
    except ClientDisconnect:
        problem = "The upload stopped before the whole file arrived. Try again."
    finally:
        reader.close()
    if problem or reader.too_big:
        reader.discard()
        raise UploadError(problem, 400) if problem else UploadError(_too_big(max_bytes), 413)
    return reader.result()


def check_name(name: str) -> str:
    """The file's extension, if Dogear reads that kind of book."""
    extension = os.path.splitext(name)[1].lower()
    if not name:
        raise UploadError("Choose a book file to upload.")
    if extension not in EXTRACTORS:
        raise UploadError(
            f"Dogear can't read {extension or 'files without an extension'} files. "
            "Choose an EPUB, PDF, MOBI, or AZW3 file."
        )
    return extension


def display_name(sent: bytes) -> str:
    """The file's name as the browser sent it, without any folders, and with the quote
    marks browsers write as %22 put back. Used only for showing."""
    name = sent.decode("utf-8", errors="replace").replace("%22", '"')
    name = "".join(c for c in name if c.isprintable())
    return os.path.basename(name.replace("\\", "/"))


class _PartError(Exception):
    pass


class _BookPart:
    """Callbacks for python-multipart that write the `book` field's data to a file."""

    def __init__(self, incoming: Path, max_bytes: int) -> None:
        self._incoming = incoming
        self._max = max_bytes
        self._header_name = b""
        self._header_value = b""
        self._disposition = b""
        self._writing = False
        self._file = None
        self._path: Path | None = None
        self._size = 0
        self._name = ""
        self._extension = ""
        self._done = False
        self.too_big = False

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value_data,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
        }

    def _part_begin(self) -> None:
        self._disposition = b""
        self._writing = False

    # python-multipart bounds each header's size and count.
    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def _header_value_data(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _header_end(self) -> None:
        if self._header_name.lower() == b"content-disposition":
            self._disposition = self._header_value
        self._header_name = b""
        self._header_value = b""

    def _headers_finished(self) -> None:
        _, options = parse_options_header(self._disposition)
        if options.get(b"name") != FIELD.encode() or b"filename" not in options:
            return  # not the book: ignored
        if self._done:
            raise _PartError("Upload one book at a time.")
        self._name = display_name(options[b"filename"])
        if not self._name:
            raise _PartError("Choose a book file to upload.")
        try:
            self._extension = check_name(self._name)
        except UploadError as e:
            raise _PartError(e.message) from None
        self._path = self._incoming / f"{secrets.token_hex(8)}.partial"
        self._file = open(self._path, "xb")  # noqa: SIM115 (closed in close())
        self._writing = True

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._writing or self._file is None:
            return
        self._size += end - start
        if self._size > self._max:
            self.too_big = True
            self._writing = False
            return
        self._file.write(data[start:end])

    def _part_end(self) -> None:
        if self._writing:
            self._done = True
        self._writing = False

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def discard(self) -> None:
        self.close()
        if self._path is not None:
            self._path.unlink(missing_ok=True)

    def result(self) -> Upload:
        if not self._done or self._path is None:
            self.discard()
            raise UploadError("Choose a book file to upload.")
        if self._size == 0:
            self.discard()
            raise UploadError(f"{self._name} is empty. Choose another file.")
        return Upload(original_name=self._name, extension=self._extension, path=self._path)


def _too_big(max_bytes: int) -> str:
    return (
        f"That file is bigger than {max_bytes // (1024 * 1024):,} MB, the most this page "
        "takes. To make it anyway, use the dogear make command, or raise web.max_upload_mb "
        "in your config file."
    )
