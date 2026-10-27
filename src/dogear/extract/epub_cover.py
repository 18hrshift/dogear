"""Find an EPUB's cover image.

Places are tried in this order, and the first usable image wins:
  1. The EPUB 3 manifest item with `properties="cover-image"`.
  2. The manifest item an EPUB 2 `<meta name="cover" content="...">` names (by id, or by
     href, which some books use instead).
  3. The first image on the cover page that the landmarks or the EPUB 2 guide point to.

Only JPEG and PNG are kept, which every audiobook player shows. The type comes from the
image's first bytes, not from what the book declares. A cover that is missing, too large
(over `epub.max_member_mb`, like any other file in the book), encrypted, or in another
format is skipped with an info message: a bad cover never stops a book being read.
Images are read in memory and never written to disk.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from dogear.document import Cover
from dogear.errors import ExtractionError
from dogear.extract.epub_nav import Navigation
from dogear.extract.epub_package import XHTML_MEDIA_TYPE, EpubArchive, Package
from dogear.extract.xhtml import resolve_href

log = logging.getLogger(__name__)

_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def read_cover(
    archive: EpubArchive, package: Package, nav: Navigation, encrypted: frozenset[str]
) -> Cover | None:
    """The book's cover image, or None (with an info message) if it has no usable one."""
    tried: set[str] = set()
    for path in _candidates(archive, package, nav):
        if path in tried:
            continue
        tried.add(path)
        cover = _load(archive, path, encrypted)
        if cover is not None:
            return cover
    if not tried:
        log.info("No cover image found in %s.", archive.name)
    return None


def _image_type(data: bytes) -> str | None:
    """The media type of a JPEG or PNG image, judged from its first bytes, else None."""
    return next((kind for magic, kind in _SIGNATURES if data.startswith(magic)), None)


def _candidates(archive: EpubArchive, package: Package, nav: Navigation) -> Iterator[str]:
    """Archive paths that may hold the cover image, best first.

    Lazy, so cover pages are read only when the package names no usable cover image.
    """
    for item in package.manifest.values():
        if "cover-image" in item.properties and item.path is not None:
            yield item.path
    if package.cover_id:
        item = package.manifest.get(package.cover_id) or next(
            (i for i in package.manifest.values() if i.href == package.cover_id), None
        )
        if item is not None and item.path is not None:
            yield item.path
        else:
            log.info(
                "The cover named in %s (%r) isn't in the book's list of files.",
                archive.name,
                package.cover_id,
            )
    pages = [path for path, tokens in nav.landmarks.items() if "cover" in tokens]
    pages += [path for kind, path in package.guide if kind == "cover"]
    for page in dict.fromkeys(pages):
        image = _image_on_page(archive, package, page)
        if image is not None:
            yield image


def _image_on_page(archive: EpubArchive, package: Package, page: str) -> str | None:
    """Archive path of the first image on a cover page, or of the page if it is an image."""
    item = next((i for i in package.manifest.values() if i.path == page), None)
    if item is not None and item.media_type.startswith("image/"):
        return page
    if item is not None and item.media_type != XHTML_MEDIA_TYPE:
        return None
    if not archive.has(page):
        log.info("The cover page %s is missing from %s.", page, archive.name)
        return None
    try:
        root = archive.parse(page)
    except ExtractionError as e:
        log.info("Skipped the cover page: %s", e.message)
        return None
    for el in root.iter("{*}img", "{*}image"):  # <image> is SVG's
        src = el.get("src") or el.get(XLINK_HREF) or el.get("href")
        target = resolve_href(page, src) if src else None
        if target is not None:
            return target[0]
    return None


def _load(archive: EpubArchive, path: str, encrypted: frozenset[str]) -> Cover | None:
    if path in encrypted:
        log.info("Skipped the cover image %s: it is encrypted.", path)
        return None
    if not archive.has(path):
        log.info("Skipped the cover image %s: it is missing from %s.", path, archive.name)
        return None
    try:
        data = archive.read(path)  # bounded by epub.max_member_mb
    except ExtractionError as e:
        log.info("Skipped the cover image: %s", e.message)
        return None
    media_type = _image_type(data)
    if media_type is None:
        log.info(
            "Skipped the cover image %s: it isn't a JPEG or PNG image, the formats "
            "audiobook players show.",
            path,
        )
        return None
    return Cover(data=data, media_type=media_type)
