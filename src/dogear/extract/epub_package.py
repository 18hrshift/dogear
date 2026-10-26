"""Open an EPUB archive and read its package: metadata, manifest, and reading order."""

from __future__ import annotations

import logging
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from lxml import etree

from dogear.document import Metadata
from dogear.errors import ExtractionError
from dogear.extract.safe_xml import parse_xml
from dogear.extract.xhtml import plain_text, resolve_href

log = logging.getLogger(__name__)

CONTAINER_PATH = "META-INF/container.xml"
ENCRYPTION_PATH = "META-INF/encryption.xml"
DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_MEDIA_TYPE = "application/oebps-package+xml"
XHTML_MEDIA_TYPE = "application/xhtml+xml"
NCX_MEDIA_TYPE = "application/x-dtbncx+xml"

DAMAGED_HINT = (
    "The file may be damaged or only partly downloaded. Download it again, or open it in "
    "Calibre and convert it to EPUB, which often repairs it."
)


class EpubArchive:
    """Read-only access to the files inside an EPUB. Nothing is unpacked to disk.

    No file is read past `max_member_bytes`, so a tiny archive that unpacks to gigabytes
    (a zip bomb) fails with an error instead of exhausting memory.
    """

    def __init__(self, path: Path, *, max_member_bytes: int) -> None:
        try:
            self._zip = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise ExtractionError(
                f"{path.name} can't be opened as an EPUB because it isn't a ZIP archive.",
                hint=DAMAGED_HINT,
            ) from None
        self.name = path.name
        self._members = frozenset(self._zip.namelist())
        self._max_bytes = max_member_bytes

    def __enter__(self) -> EpubArchive:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._zip.close()

    def has(self, member: str) -> bool:
        return member in self._members

    def read(self, member: str) -> bytes:
        if member not in self._members:
            raise ExtractionError(f"{member} is missing from {self.name}.", hint=DAMAGED_HINT)
        if self._zip.getinfo(member).file_size > self._max_bytes:
            raise self._too_large(member)
        try:
            with self._zip.open(member) as f:
                # The size in the archive's header is the file's own claim, so don't trust
                # it: read at most one byte past the limit. Data is inflated in small
                # chunks, so memory stays bounded however far the member would expand.
                data = f.read(self._max_bytes + 1)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as e:
            raise ExtractionError(
                f"{member} in {self.name} can't be read ({e}).", hint=DAMAGED_HINT
            ) from None
        if len(data) > self._max_bytes:
            raise self._too_large(member)
        return data

    def _too_large(self, member: str) -> ExtractionError:
        limit_mb = self._max_bytes / (1024 * 1024)
        return ExtractionError(
            f"{member} in {self.name} unpacks to more than {limit_mb:g} MB, far more than "
            "a book's text needs, so Dogear stopped reading it.",
            hint=(
                "The file may be damaged or built to exhaust memory (a 'zip bomb'). If it's "
                "a genuine book, raise epub.max_member_mb in your config file."
            ),
        )

    def parse(self, member: str) -> etree._Element:
        return parse_xml(self.read(member), f"{member} in {self.name}", DAMAGED_HINT)


@dataclass(frozen=True)
class ManifestItem:
    id: str
    href: str
    path: str | None  # archive path; None when the href leaves the book
    media_type: str
    properties: frozenset[str]


@dataclass(frozen=True)
class SpineRef:
    idref: str
    linear: bool


@dataclass
class Package:
    path: str  # archive path of the OPF file
    metadata: Metadata
    manifest: dict[str, ManifestItem]
    spine: list[SpineRef]
    nav_path: str | None  # EPUB 3 navigation document
    ncx_path: str | None  # EPUB 2 table of contents


def find_package_path(archive: EpubArchive) -> str:
    """Archive path of the OPF package file named in META-INF/container.xml."""
    if not archive.has(CONTAINER_PATH):
        raise ExtractionError(
            f"{archive.name} has no {CONTAINER_PATH}, so Dogear can't find the book inside it.",
            hint=DAMAGED_HINT,
        )
    rootfiles = archive.parse(CONTAINER_PATH).findall(".//{*}rootfile")
    preferred = [r for r in rootfiles if r.get("media-type") == OPF_MEDIA_TYPE]
    full_path = next((r.get("full-path") for r in preferred + rootfiles), None)
    target = resolve_href("", full_path) if full_path else None
    if target is None or not archive.has(target[0]):
        named = f" ({full_path})" if full_path else ""
        raise ExtractionError(
            f"The package file{named} that lists the contents of {archive.name} is missing.",
            hint=DAMAGED_HINT,
        )
    return target[0]


def read_encrypted_paths(archive: EpubArchive) -> frozenset[str]:
    """Archive paths that META-INF/encryption.xml says are encrypted or obfuscated."""
    if not archive.has(ENCRYPTION_PATH):
        return frozenset()
    paths = set()
    for ref in archive.parse(ENCRYPTION_PATH).iter("{*}CipherReference"):
        target = resolve_href("", ref.get("URI") or "")
        if target is not None:
            paths.add(target[0])
    return frozenset(paths)


def read_package(archive: EpubArchive, opf_path: str, fallback_title: str) -> Package:
    root = archive.parse(opf_path)
    manifest = _manifest(root, opf_path)
    spine_el = root.find("{*}spine")
    if spine_el is None:
        raise ExtractionError(
            f"{opf_path} in {archive.name} has no reading order (spine).", hint=DAMAGED_HINT
        )
    return Package(
        path=opf_path,
        metadata=_metadata(root, fallback_title),
        manifest=manifest,
        spine=_spine(spine_el),
        nav_path=next((i.path for i in manifest.values() if "nav" in i.properties), None),
        ncx_path=_ncx_path(spine_el, manifest),
    )


def _metadata(root: etree._Element, fallback_title: str) -> Metadata:
    meta = root.find("{*}metadata")
    if meta is None:
        log.warning("The book has no metadata section; using the file name as its title.")
        return Metadata(title=fallback_title)

    def texts(name: str) -> list[str]:
        values = (plain_text(el) for el in meta.iter(f"{{{DC_NS}}}{name}"))
        return [v for v in values if v]

    def first(name: str) -> str | None:
        return next(iter(texts(name)), None)

    return Metadata(
        title=first("title") or fallback_title,
        authors=texts("creator"),
        language=first("language"),
        identifier=_identifier(root, meta),
        publisher=first("publisher"),
    )


def _identifier(root: etree._Element, meta: etree._Element) -> str | None:
    """The dc:identifier named by package@unique-identifier, else the first one."""
    found = [(el.get("id"), plain_text(el)) for el in meta.iter(f"{{{DC_NS}}}identifier")]
    found = [(id_, text) for id_, text in found if text]
    unique_id = root.get("unique-identifier")
    named = next((text for id_, text in found if unique_id and id_ == unique_id), None)
    return named or next((text for _, text in found), None)


def _manifest(root: etree._Element, opf_path: str) -> dict[str, ManifestItem]:
    items = {}
    for el in root.iterfind("{*}manifest/{*}item"):
        item_id, href = el.get("id"), el.get("href")
        if not item_id or not href:
            log.warning("Ignored a manifest entry in %s with no id or href.", opf_path)
            continue
        target = resolve_href(opf_path, href)
        items[item_id] = ManifestItem(
            id=item_id,
            href=href,
            path=target[0] if target else None,
            media_type=(el.get("media-type") or "").strip().lower(),
            properties=frozenset((el.get("properties") or "").split()),
        )
    return items


def _spine(spine_el: etree._Element) -> list[SpineRef]:
    return [
        SpineRef(
            idref=el.get("idref") or "",
            linear=(el.get("linear") or "yes").strip().lower() != "no",
        )
        for el in spine_el.iterfind("{*}itemref")
    ]


def _ncx_path(spine_el: etree._Element, manifest: dict[str, ManifestItem]) -> str | None:
    named = manifest.get(spine_el.get("toc") or "")
    if named is not None:
        return named.path
    return next((i.path for i in manifest.values() if i.media_type == NCX_MEDIA_TYPE), None)
